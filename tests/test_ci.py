from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
import yaml  # type: ignore[import-untyped]

from reviewlens.ci import policy


def _workflow() -> dict[str, object]:
    loaded = yaml.load(
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,  # noqa: S506 - scalar-only loader avoids YAML 1.1 booleans
    )
    assert isinstance(loaded, dict)
    return cast(dict[str, object], loaded)


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _sequence(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast(list[object], value)


def test_ci_workflow_has_least_privilege_and_safe_triggers() -> None:
    workflow = _workflow()
    triggers = _mapping(workflow["on"])

    assert set(triggers) == {"push", "pull_request", "workflow_dispatch"}
    assert "pull_request_target" not in triggers
    assert _mapping(workflow["permissions"]) == {"contents": "read"}

    concurrency = _mapping(workflow["concurrency"])
    assert concurrency["cancel-in-progress"] == "true"

    jobs = _mapping(workflow["jobs"])
    job = _mapping(jobs["foundation-gates"])
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["timeout-minutes"] == "30"


def test_ci_workflow_pins_bootstrap_and_runs_all_m1_gates() -> None:
    workflow = _workflow()
    job = _mapping(_mapping(workflow["jobs"])["foundation-gates"])
    steps = [_mapping(item) for item in _sequence(job["steps"])]
    uses = [str(step["uses"]) for step in steps if "uses" in step]

    assert "actions/checkout@v7" in uses
    setup_uv = next(item for item in uses if item.startswith("astral-sh/setup-uv@"))
    assert re.fullmatch(r"astral-sh/setup-uv@[0-9a-f]{40}", setup_uv)
    assert uses.count("aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25") == 2

    checkout = next(step for step in steps if step.get("uses") == "actions/checkout@v7")
    assert _mapping(checkout["with"])["persist-credentials"] == "false"
    uv_step = next(step for step in steps if step.get("uses") == setup_uv)
    assert _mapping(uv_step["with"])["version"] == "0.11.32"
    assert _mapping(uv_step["with"])["enable-cache"] == "true"

    commands = "\n".join(str(step["run"]) for step in steps if "run" in step)
    required_commands = (
        "uv sync --locked --group airflow --group dbt",
        "ruff format --check src tests airflow",
        "ruff check airflow --select AIR301,AIR302,AIR303",
        "mypy src tests",
        "pytest",
        "--cov=reviewlens --cov-branch",
        "dbt --no-use-colors --warn-error parse",
        "--no-introspect",
        "reviewlens-policy --root .",
        "uv export --locked --all-groups --all-extras --no-emit-project",
        "pip-audit",
        "--strict --require-hashes --disable-pip",
        "validate_project_status.py",
        "reviewlens-artifacts --check",
        "docker compose config --quiet",
        "docker compose build app airflow",
        'uv "reviewlens/app:${REVIEWLENS_ARTIFACT_TAG}" pip check',
        'python "reviewlens/airflow:${REVIEWLENS_ARTIFACT_TAG}" -m pip check',
        "uv cache prune --ci",
    )
    assert all(command in commands for command in required_commands)


def test_ci_workflow_cannot_use_live_credentials_or_silence_failures() -> None:
    workflow_text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    forbidden = (
        "secrets.",
        "REVIEWLENS_RUN_LIVE",
        "pull_request_target",
        "continue-on-error",
        "|| true",
        "0.0." + "0.0",
        "duckdb",
        "ignore-vuln",
        "--no-hashes",
    )
    assert not any(value.lower() in workflow_text.lower() for value in forbidden)


@pytest.mark.parametrize(
    ("relative_path", "expected_rule"),
    [
        (".env", "environment-file"),
        ("secrets/runtime.p8", "private-key-file"),
        ("archive/manifest.txt", "private-generated-directory"),
        ("olist_order_reviews_dataset.csv", "olist-source-file"),
        ("exports/orders.parquet", "row-level-data-artifact"),
        ("Dockerfile", "unreviewed-container-artifact"),
        ("nested/compose.yaml", "unreviewed-container-artifact"),
    ],
)
def test_repository_policy_blocks_forbidden_paths(
    tmp_path: Path,
    relative_path: str,
    expected_rule: str,
) -> None:
    candidate = tmp_path / relative_path
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("synthetic canary", encoding="utf-8")

    findings = policy.scan_repository_paths(tmp_path, [relative_path])

    assert expected_rule in {finding.rule for finding in findings}


@pytest.mark.parametrize(
    ("payload_factory", "expected_rule"),
    [
        (lambda: b"sk-or-v1-" + b"A" * 32, "openrouter-token"),
        (lambda: b"-----BEGIN " + b"PRIVATE KEY-----", "private-key-material"),
        (lambda: b"APP_AUTH_" + b"TOKEN=local-canary-value-123", "credential-assignment"),
    ],
)
def test_repository_policy_blocks_secret_content_without_echoing_it(
    tmp_path: Path,
    payload_factory: Callable[[], bytes],
    expected_rule: str,
) -> None:
    payload = payload_factory()
    candidate = tmp_path / "candidate.txt"
    candidate.write_bytes(payload)

    findings = policy.scan_repository_paths(tmp_path, [candidate.name])
    rendered = "\n".join(f"{item.path}: {item.rule}" for item in findings)

    assert expected_rule in {finding.rule for finding in findings}
    assert payload.decode() not in rendered


def test_placeholder_cannot_hide_later_credential_assignment(tmp_path: Path) -> None:
    payload = b"APP_AUTH_" + b"TOKEN=example-value\nAPP_AUTH_" + b"TOKEN=real-canary-123"
    candidate = tmp_path / "candidate.txt"
    candidate.write_bytes(payload)

    findings = policy.scan_repository_paths(tmp_path, [candidate.name])

    assert "credential-assignment" in {finding.rule for finding in findings}


def test_repository_policy_allows_only_explicit_synthetic_row_fixtures(tmp_path: Path) -> None:
    relative_path = "tests/fixtures/synthetic/olist_orders_dataset.csv"
    candidate = tmp_path / relative_path
    candidate.parent.mkdir(parents=True)
    candidate.write_text("order_id\nsynthetic_order_1\n", encoding="utf-8")

    assert policy.scan_repository_paths(tmp_path, [relative_path]) == ()


@pytest.mark.parametrize("relative_path", ["Dockerfile.app", "Dockerfile.airflow", "compose.yaml"])
def test_repository_policy_allows_reviewed_root_container_files(
    tmp_path: Path, relative_path: str
) -> None:
    candidate = tmp_path / relative_path
    candidate.write_text("synthetic container contract", encoding="utf-8")

    assert policy.scan_repository_paths(tmp_path, [relative_path]) == ()


def test_repository_policy_rejects_unsafe_relative_path(tmp_path: Path) -> None:
    findings = policy.scan_repository_paths(tmp_path, ["../escape.txt"])
    assert findings == (policy.PolicyFinding("../escape.txt", "unsafe-path"),)


def test_policy_cli_returns_nonzero_for_deliberate_failing_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = b"sk-or-v1-" + b"B" * 32
    (tmp_path / "candidate.txt").write_bytes(canary)

    def fake_git_visible_paths(root: Path) -> tuple[str, ...]:
        assert root == tmp_path
        return ("candidate.txt",)

    monkeypatch.setattr(policy, "git_visible_paths", fake_git_visible_paths)
    with pytest.raises(SystemExit, match="1"):
        policy.main(["--root", str(tmp_path)])

    output = capsys.readouterr().out
    assert "candidate.txt: openrouter-token" in output
    assert canary.decode() not in output


def test_current_git_visible_repository_passes_policy() -> None:
    root = Path.cwd()
    findings = policy.scan_repository_paths(root, policy.git_visible_paths(root))
    assert findings == ()
