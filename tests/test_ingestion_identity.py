from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from reviewlens.ingestion.identity import (
    IngestionIdentityError,
    attempt_id,
    dataset_run_id,
    ingestion_batch_id,
    record_id,
    source_object_id,
)
from reviewlens.ingestion.source import build_canonical_manifest, discover_source_snapshot
from reviewlens.synthetic.generator import generate_fixture

_PREFIX_PATTERNS = {
    "source_object": r"^srcobj_[0-9a-f]{64}$",
    "ingestion_batch": r"^batch_[0-9a-f]{64}$",
    "dataset_run": r"^dsrun_[0-9a-f]{64}$",
    "attempt": r"^attempt_[0-9a-f]{64}$",
    "record": r"^record_[0-9a-f]{64}$",
}


def _source_inputs(root: Path) -> tuple[str, str, str, str]:
    generate_fixture(root)
    snapshot = discover_source_snapshot(root)
    manifest = build_canonical_manifest(
        snapshot,
        source_snapshot_date=date(2026, 8, 5),
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
    )
    source_file = snapshot.files[0]
    return (
        manifest.source_release_id,
        source_file.file_name,
        source_file.dataset_name,
        source_file.sha256,
    )


def _identity_chain(root: Path, *, attempt_number: int = 1) -> dict[str, str]:
    release_id, file_name, dataset_name, checksum = _source_inputs(root)
    object_id = source_object_id(
        source_release_id=release_id,
        file_name=file_name,
        source_object_sha256=checksum,
    )
    batch_id = ingestion_batch_id(source_release_id=release_id)
    run_id = dataset_run_id(
        ingestion_batch_id=batch_id,
        source_object_id=object_id,
        dataset_name=dataset_name,
        contract_version="olist-source-v1",
    )
    return {
        "source_object": object_id,
        "ingestion_batch": batch_id,
        "dataset_run": run_id,
        "attempt": attempt_id(dataset_run_id=run_id, attempt_number=attempt_number),
        "record": record_id(
            source_object_id=object_id,
            source_row_number=2,
            byte_start=101,
            byte_end=202,
        ),
    }


def test_identity_chain_is_deterministic_path_free_and_namespaced(tmp_path: Path) -> None:
    first = _identity_chain(tmp_path / "first")
    second = _identity_chain(tmp_path / "second")

    assert first == second
    for kind, value in first.items():
        assert re.fullmatch(_PREFIX_PATTERNS[kind], value)
        assert str(tmp_path) not in value


def test_retry_changes_only_attempt_identity(tmp_path: Path) -> None:
    first = _identity_chain(tmp_path / "first", attempt_number=1)
    retry = _identity_chain(tmp_path / "second", attempt_number=2)

    assert first["attempt"] != retry["attempt"]
    assert {key: value for key, value in first.items() if key != "attempt"} == {
        key: value for key, value in retry.items() if key != "attempt"
    }


def test_object_run_and_record_dimensions_are_collision_distinct(tmp_path: Path) -> None:
    release_id, file_name, dataset_name, checksum = _source_inputs(tmp_path)
    object_id = source_object_id(
        source_release_id=release_id,
        file_name=file_name,
        source_object_sha256=checksum,
    )
    batch_id = ingestion_batch_id(source_release_id=release_id)
    baseline_run = dataset_run_id(
        ingestion_batch_id=batch_id,
        source_object_id=object_id,
        dataset_name=dataset_name,
        contract_version="olist-source-v1",
    )

    assert baseline_run != dataset_run_id(
        ingestion_batch_id=batch_id,
        source_object_id=object_id,
        dataset_name=dataset_name,
        contract_version="olist-source-v2",
    )
    ids = {
        record_id(
            source_object_id=object_id,
            source_row_number=row_number,
            byte_start=row_number * 100,
            byte_end=row_number * 100 + 50,
        )
        for row_number in range(2, 1_002)
    }
    assert len(ids) == 1_000


@pytest.mark.parametrize(
    "call",
    [
        lambda: ingestion_batch_id(source_release_id="seeded-secret"),
        lambda: source_object_id(
            source_release_id=f"olist_{'0' * 64}",
            file_name="../unsafe.csv",
            source_object_sha256="0" * 64,
        ),
        lambda: dataset_run_id(
            ingestion_batch_id=f"batch_{'0' * 64}",
            source_object_id=f"srcobj_{'0' * 64}",
            dataset_name="unknown",
            contract_version="olist-source-v1",
        ),
        lambda: attempt_id(dataset_run_id=f"dsrun_{'0' * 64}", attempt_number=0),
        lambda: record_id(
            source_object_id=f"srcobj_{'0' * 64}",
            source_row_number=1,
            byte_start=9,
            byte_end=8,
        ),
    ],
)
def test_invalid_identity_inputs_fail_closed_without_echo(call: Callable[[], str]) -> None:
    with pytest.raises(IngestionIdentityError) as captured:
        call()

    assert str(captured.value) == "INGESTION_IDENTITY_INVALID"
    assert "seeded-secret" not in str(captured.value)
