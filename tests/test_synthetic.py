from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from reviewlens.synthetic.generator import REQUIRED_FILES, generate_fixture


def _directory_hashes(path: Path) -> dict[str, str]:
    return {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(path.iterdir())
        if item.is_file()
    }


def test_generator_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_fixture(first)
    generate_fixture(second)
    assert _directory_hashes(first) == _directory_hashes(second)


def test_fixture_has_required_sources_and_manifest(tmp_path: Path) -> None:
    manifest = generate_fixture(tmp_path)
    assert {item["filename"] for item in manifest["files"]} == set(REQUIRED_FILES)
    assert manifest["data_class"] == "synthetic"
    for filename in REQUIRED_FILES:
        lines = (tmp_path / filename).read_text(encoding="utf-8").splitlines()
        assert lines
        assert all(json.loads(line) for line in lines)


def test_generator_refuses_real_source_directory() -> None:
    with pytest.raises(ValueError, match="real Yelp source directory"):
        generate_fixture(Path("Yelp-JSON/synthetic-output"))


def test_fixture_content_is_explicitly_synthetic(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    content = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.json"))
    assert "synthetic_" in content
    assert "reviewlens-generator" in content
