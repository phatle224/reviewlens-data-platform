import shutil
import subprocess
from pathlib import Path


def test_repository_bootstrap_and_review_contract() -> None:
    required = (
        Path("README.md"),
        Path("CONTRIBUTING.md"),
        Path(".github/CODEOWNERS"),
        Path(".github/pull_request_template.md"),
        Path(".github/ISSUE_TEMPLATE/config.yml"),
        Path(".github/ISSUE_TEMPLATE/feature.yml"),
        Path(".github/ISSUE_TEMPLATE/bug.yml"),
    )
    assert all(path.is_file() for path in required)

    readme = Path("README.md").read_text(encoding="utf-8")
    assert "uv sync --locked" in readme
    assert "synthetic" in readme.lower()
    assert ".env" in readme

    pull_request = Path(".github/pull_request_template.md").read_text(encoding="utf-8")
    for expected in ("Implementation item", "Requirement", "Verification", "Risk"):
        assert expected in pull_request

    codeowners = Path(".github/CODEOWNERS").read_text(encoding="utf-8")
    assert "@phatle224" in codeowners
    assert "your-github-username" not in codeowners


def test_private_key_formats_and_env_are_ignored() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert {".env", "*.pem", "*.key", "*.p8"}.issubset(gitignore)


def test_olist_source_and_attribution_contract_is_publication_safe() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert {"archive/", "olist_dataset/"}.issubset(gitignore)

    attribution = Path("docs/DATA_ATTRIBUTION.md").read_text(encoding="utf-8")
    for expected in (
        "Brazilian E-Commerce Public Dataset by Olist",
        "CC BY-NC-SA 4.0",
        "NonCommercial",
        "ShareAlike",
        "No endorsement",
    ):
        assert expected.lower() in attribution.lower()

    git_executable = shutil.which("git")
    assert git_executable is not None
    tracked = subprocess.run(  # noqa: S603 - resolved local Git executable
        [git_executable, "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert not any(path.startswith(("archive/", "olist_dataset/")) for path in tracked)
    assert not any(path.endswith("_dataset.csv") for path in tracked)


def test_active_operational_docs_use_olist_not_legacy_source_contract() -> None:
    active_contracts = (
        Path("README.md"),
        Path("config/config.toml"),
        Path("docs/reviewlens_rag_recommendation.md"),
        Path("docs/phases/M0/M0_SOURCE_PROFILE.md"),
        Path("docs/phases/M0/M0_PRODUCT_DATA_BASELINE.md"),
        Path("docs/phases/M0/M0_SECURITY_PRIVACY.md"),
    )
    for path in active_contracts:
        content = path.read_text(encoding="utf-8").lower()
        assert "olist" in content
        assert "yelp" not in content
