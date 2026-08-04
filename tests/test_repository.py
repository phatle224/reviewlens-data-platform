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
