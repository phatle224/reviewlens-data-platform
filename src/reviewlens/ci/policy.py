"""Fail-closed secret, data-leak, and pre-container repository policy checks."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
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
    findings = scan_repository_paths(args.root, git_visible_paths(args.root))
    if findings:
        print(f"ReviewLens repository policy: FAIL ({len(findings)} finding(s))")
        for finding in findings:
            print(f"- {finding.path}: {finding.rule}")
        raise SystemExit(1)
    print("ReviewLens repository policy: PASS (0 findings)")
