"""Create and validate immutable source-derived local image metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from reviewlens.config import project_root

MANIFEST_PATH = Path("deploy/artifacts.lock.json")
INPUT_FILES = (
    Path("Dockerfile.app"),
    Path("Dockerfile.airflow"),
    Path("compose.yaml"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("README.md"),
    Path("deploy/airflow-entrypoint.sh"),
    Path("deploy/chroma-security-policy.json"),
)
INPUT_DIRECTORIES = (Path("src"), Path("config"), Path("airflow/dags"))


def source_files(root: Path) -> tuple[Path, ...]:
    selected = list(INPUT_FILES)
    for directory in INPUT_DIRECTORIES:
        selected.extend(
            path.relative_to(root)
            for path in (root / directory).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        )
    return tuple(sorted(selected, key=lambda path: path.as_posix()))


def source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for relative in source_files(root):
        payload = (root / relative).read_bytes()
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def expected_manifest(root: Path) -> dict[str, Any]:
    digest = source_digest(root)
    tag = f"local-sha256-{digest[:16]}"
    return {
        "schema_version": 1,
        "deployment_scope": "local-demo-only",
        "source_sha256": digest,
        "artifact_tag": tag,
        "images": {
            "app": f"reviewlens/app:{tag}",
            "airflow": f"reviewlens/airflow:{tag}",
        },
    }


def write_manifest(root: Path) -> Path:
    target = root / MANIFEST_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(expected_manifest(root), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def load_manifest(root: Path) -> dict[str, Any]:
    payload = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("artifact metadata must be a JSON object")
    return cast(dict[str, Any], payload)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Manage immutable local container metadata")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    action.add_argument("--print-tag", action="store_true")
    parser.add_argument("--root", type=Path, default=project_root())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    expected = expected_manifest(root)
    if args.write:
        print(write_manifest(root))
        return
    if args.print_tag:
        manifest = load_manifest(root)
        if manifest != expected:
            raise SystemExit("artifact metadata is stale; run reviewlens-artifacts --write")
        print(manifest["artifact_tag"])
        return
    if load_manifest(root) != expected:
        raise SystemExit("artifact metadata is stale; run reviewlens-artifacts --write")
    print("ReviewLens artifact metadata: PASS")


if __name__ == "__main__":
    main()
