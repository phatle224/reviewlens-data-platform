"""Fail-closed secret, data-leak, and pre-container repository policy checks."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from reviewlens.synthetic.generator import REQUIRED_FILES

_MAX_SCANNED_BYTES = 5 * 1024 * 1024
_FORBIDDEN_TOP_LEVEL = frozenset(
    {
        "archive",
        "artifacts",
        "chroma_data",
        "data",
        "manifests",
        "olist_dataset",
        "quarantine",
    }
)
_FORBIDDEN_KEY_SUFFIXES = frozenset({".key", ".p8", ".pem"})
_FORBIDDEN_ROW_ARTIFACT_SUFFIXES = frozenset(
    {".csv", ".feather", ".jsonl", ".ndjson", ".npy", ".npz", ".parquet"}
)
_COMPOSE_FILE_NAMES = frozenset(
    {"compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"}
)
_REVIEWED_CONTAINER_FILES = frozenset({"Dockerfile.app", "Dockerfile.airflow", "compose.yaml"})
_CHROMA_SECURITY_POLICY = Path("deploy/chroma-security-policy.json")
_CHROMA_ADVISORY_ID = "GHSA-f4j7-r4q5-qw2c"
_CHROMA_CVE = "CVE-2026-45829"
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    (
        "private-key-material",
        re.compile(rb"-----BEGIN (?:ENCRYPTED |RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    ("openrouter-token", re.compile(rb"\bsk-or-v1-[A-Za-z0-9_-]{24,}\b")),
    ("github-token", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("aws-access-key", re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "credential-assignment",
        re.compile(
            rb"(?im)^[ \t]*(?:export[ \t]+)?(?:"
            rb"APP_AUTH_TOKEN|CHROMA_AUTH_TOKEN|OPENROUTER_API_KEY|SNOWFLAKE_PASSWORD|"
            rb"R2_[A-Z0-9_]*(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY)|"
            rb"SNOWFLAKE_[A-Z0-9_]*PRIVATE_KEY_PASSPHRASE"
            rb")[ \t]*=[ \t]*['\"]?(?P<value>[^\s'\"#][^\r\n]*)$"
        ),
    ),
    (
        "powershell-credential-assignment",
        re.compile(
            rb"(?im)^[ \t]*\$env:(?:APP_AUTH_TOKEN|CHROMA_AUTH_TOKEN|OPENROUTER_API_KEY|"
            rb"SNOWFLAKE_PASSWORD|R2_[A-Z0-9_]*(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY)|"
            rb"SNOWFLAKE_[A-Z0-9_]*PRIVATE_KEY_PASSPHRASE"
            rb")[ \t]*=[ \t]*['\"](?P<value>[^'\"\r\n]+)['\"][ \t]*$"
        ),
    ),
)


@dataclass(frozen=True, order=True, slots=True)
class PolicyFinding:
    path: str
    rule: str


def _dependency_names(project: dict[str, object]) -> frozenset[str]:
    specifications: list[str] = []
    project_table = project.get("project")
    if isinstance(project_table, dict):
        dependencies = project_table.get("dependencies", [])
        if isinstance(dependencies, list):
            specifications.extend(item for item in dependencies if isinstance(item, str))
        optional = project_table.get("optional-dependencies", {})
        if isinstance(optional, dict):
            for group in optional.values():
                if isinstance(group, list):
                    specifications.extend(item for item in group if isinstance(item, str))
    groups = project.get("dependency-groups", {})
    if isinstance(groups, dict):
        for group in groups.values():
            if isinstance(group, list):
                specifications.extend(item for item in group if isinstance(item, str))
    names = {
        match.group(0).lower().replace("_", "-")
        for specification in specifications
        if (match := re.match(r"[A-Za-z0-9_.-]+", specification)) is not None
    }
    return frozenset(names)


def chroma_security_findings(root: Path) -> tuple[PolicyFinding, ...]:
    """Fail closed while the reviewed Chroma release range has no patch."""

    root = root.resolve()
    relative = _CHROMA_SECURITY_POLICY.as_posix()
    target = root / _CHROMA_SECURITY_POLICY
    if not target.is_file():
        return (PolicyFinding(relative, "chroma-security-policy-missing"),)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return (PolicyFinding(relative, "chroma-security-policy-invalid"),)
    if not isinstance(payload, dict):
        return (PolicyFinding(relative, "chroma-security-policy-invalid"),)
    advisory = payload.get("advisory")
    sources = payload.get("sources")
    valid = (
        payload.get("schema_version") == 1
        and payload.get("component") == "chromadb"
        and payload.get("status") == "blocked"
        and payload.get("compose_service_allowed") is False
        and payload.get("latest_observed_version") == "1.5.9"
        and payload.get("last_reviewed_at") == "2026-08-11"
        and isinstance(advisory, dict)
        and advisory.get("id") == _CHROMA_ADVISORY_ID
        and advisory.get("cve") == _CHROMA_CVE
        and advisory.get("severity") == "critical"
        and advisory.get("affected_versions") == ">=1.0.0,<=1.5.9"
        and advisory.get("patched_versions") == []
        and isinstance(sources, list)
        and f"https://github.com/advisories/{_CHROMA_ADVISORY_ID}" in sources
        and "https://pypi.org/project/chromadb/" in sources
        and "https://github.com/chroma-core/chroma/releases" in sources
    )
    if not valid:
        return (PolicyFinding(relative, "chroma-security-policy-invalid"),)

    findings: set[PolicyFinding] = set()
    compose_path = root / "compose.yaml"
    if compose_path.is_file() and re.search(
        r"(?m)^  chroma:\s*(?:#.*)?$", compose_path.read_text(encoding="utf-8")
    ):
        findings.add(PolicyFinding("compose.yaml", "blocked-chroma-service"))
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.is_file():
        try:
            project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            findings.add(PolicyFinding("pyproject.toml", "project-metadata-invalid"))
        else:
            if "chromadb" in _dependency_names(project):
                findings.add(PolicyFinding("pyproject.toml", "blocked-chroma-dependency"))
    lock_path = root / "uv.lock"
    if lock_path.is_file() and re.search(
        r'(?m)^name = "chromadb"$', lock_path.read_text(encoding="utf-8")
    ):
        findings.add(PolicyFinding("uv.lock", "blocked-chroma-lock-entry"))
    return tuple(sorted(findings))


def _normalized_path(path: str | Path) -> PurePosixPath:
    return PurePosixPath(str(path).replace("\\", "/").removeprefix("./"))


def _is_synthetic_fixture(path: PurePosixPath) -> bool:
    return path.parts[:3] == ("tests", "fixtures", "synthetic")


def _path_findings(path: PurePosixPath) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    path_text = path.as_posix()
    name_lower = path.name.lower()
    suffix_lower = path.suffix.lower()

    if path.parts and path.parts[0].lower() in _FORBIDDEN_TOP_LEVEL:
        findings.append(PolicyFinding(path_text, "private-generated-directory"))
    if name_lower.startswith(".env") and name_lower != ".env.example":
        findings.append(PolicyFinding(path_text, "environment-file"))
    if suffix_lower in _FORBIDDEN_KEY_SUFFIXES:
        findings.append(PolicyFinding(path_text, "private-key-file"))
    if suffix_lower in _FORBIDDEN_ROW_ARTIFACT_SUFFIXES and not _is_synthetic_fixture(path):
        findings.append(PolicyFinding(path_text, "row-level-data-artifact"))
    if path.name in REQUIRED_FILES and not _is_synthetic_fixture(path):
        findings.append(PolicyFinding(path_text, "olist-source-file"))
    is_container_file = name_lower.startswith("dockerfile") or name_lower in _COMPOSE_FILE_NAMES
    if is_container_file and path_text not in _REVIEWED_CONTAINER_FILES:
        findings.append(PolicyFinding(path_text, "unreviewed-container-artifact"))
    return findings


def _looks_like_placeholder(value: bytes) -> bool:
    normalized = value.decode("utf-8", errors="ignore").strip().strip("'\"").lower()
    markers = (
        "change-me",
        "example",
        "giá_trị_",
        "placeholder",
        "replace-me",
        "synthetic",
        "your-",
        "your_",
    )
    return normalized.startswith("<") or normalized.startswith(markers)


def _content_findings(path: PurePosixPath, payload: bytes) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    for rule, pattern in _SECRET_PATTERNS:
        matches = tuple(pattern.finditer(payload))
        if not matches:
            continue
        if rule.endswith("credential-assignment") and all(
            _looks_like_placeholder(match.group("value")) for match in matches
        ):
            continue
        findings.append(PolicyFinding(path.as_posix(), rule))
    return findings


def scan_repository_paths(
    root: Path,
    paths: Iterable[str | Path],
) -> tuple[PolicyFinding, ...]:
    """Scan explicit Git-visible paths without returning file contents."""

    resolved_root = root.resolve()
    findings: set[PolicyFinding] = set()
    for raw_path in paths:
        relative = _normalized_path(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            findings.add(PolicyFinding(relative.as_posix(), "unsafe-path"))
            continue
        findings.update(_path_findings(relative))
        candidate_path = resolved_root / Path(*relative.parts)
        if candidate_path.is_symlink():
            findings.add(PolicyFinding(relative.as_posix(), "symbolic-link"))
            continue
        candidate = candidate_path.resolve()
        if not candidate.is_relative_to(resolved_root):
            findings.add(PolicyFinding(relative.as_posix(), "path-escapes-repository"))
            continue
        if not candidate.is_file():
            continue
        if candidate.stat().st_size > _MAX_SCANNED_BYTES:
            findings.add(PolicyFinding(relative.as_posix(), "oversized-git-artifact"))
            continue
        findings.update(_content_findings(relative, candidate.read_bytes()))
    return tuple(sorted(findings))


def git_visible_paths(root: Path) -> tuple[str, ...]:
    """Return tracked and untracked, non-ignored paths from the selected repository."""

    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("git executable is required for repository policy checks")
    result = subprocess.run(  # noqa: S603 - resolved local Git executable
        [git_executable, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return tuple(path.decode("utf-8") for path in result.stdout.split(b"\0") if path)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Scan Git-visible files for ReviewLens secret/data/container policy violations"
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    findings = tuple(
        sorted(
            {
                *scan_repository_paths(args.root, git_visible_paths(args.root)),
                *chroma_security_findings(args.root),
            }
        )
    )
    if findings:
        print(f"ReviewLens repository policy: FAIL ({len(findings)} finding(s))")
        for finding in findings:
            print(f"- {finding.path}: {finding.rule}")
        raise SystemExit(1)
    print("ReviewLens repository policy: PASS (0 findings)")
