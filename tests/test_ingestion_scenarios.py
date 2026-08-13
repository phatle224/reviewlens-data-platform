from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Barrier

import pytest

from reviewlens.clock import FrozenClock
from reviewlens.ingestion.audit import (
    IngestionLease,
    IngestionLeaseUnavailable,
    InMemoryIngestionAuditRepository,
)
from reviewlens.ingestion.orchestration import LocalAirflowIngestionRunner
from reviewlens.ingestion.source import (
    SourceDiscoveryCode,
    SourceDiscoveryError,
    SourceReleaseDisposition,
    build_canonical_manifest,
    classify_source_release,
    discover_source_snapshot,
)
from reviewlens.synthetic.generator import generate_fixture


def _manifest(source: Path):  # type: ignore[no-untyped-def]
    return build_canonical_manifest(
        discover_source_snapshot(source),
        source_snapshot_date=date(2026, 8, 5),
        created_at=datetime(2026, 8, 5, tzinfo=UTC),
    )


@pytest.mark.parametrize("failure", ["late", "duplicate_manifest"])
def test_late_or_ambiguous_source_is_blocked_before_provider_access(
    tmp_path: Path,
    failure: str,
) -> None:
    source = tmp_path / failure
    generate_fixture(source, seed=20260814)
    if failure == "late":
        (source / "manifest.json").unlink()
        expected = SourceDiscoveryCode.COMPLETION_MANIFEST_MISSING
    else:
        manifest_path = source / "manifest.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["files"].append(payload["files"][0])
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        expected = SourceDiscoveryCode.DUPLICATE_MANIFEST_FILE

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(source)

    assert captured.value.code is expected
    assert str(tmp_path) not in str(captured.value)


def test_same_filenames_with_changed_bytes_create_a_new_release(tmp_path: Path) -> None:
    first = tmp_path / "first"
    changed = tmp_path / "changed"
    generate_fixture(first, seed=20260814)
    generate_fixture(changed, seed=20260815)

    first_manifest = _manifest(first)
    changed_manifest = _manifest(changed)

    assert first_manifest.source_release_id != changed_manifest.source_release_id
    assert (
        classify_source_release(first_manifest, changed_manifest)
        is SourceReleaseDisposition.NEW_CANDIDATE
    )


def test_backfill_changes_attempt_only_and_preserves_lineage(tmp_path: Path) -> None:
    source = tmp_path / "fixture"
    generate_fixture(source, seed=20260814)

    normal = LocalAirflowIngestionRunner(
        source_root=source,
        output_root=tmp_path / "normal",
        attempt_number=1,
    ).validate_source()
    backfill = LocalAirflowIngestionRunner(
        source_root=source,
        output_root=tmp_path / "backfill",
        attempt_number=2,
    ).validate_source()

    assert normal.source_release_id == backfill.source_release_id
    assert normal.ingestion_batch_id == backfill.ingestion_batch_id
    assert [item.dataset_run_id for item in normal.datasets] == [
        item.dataset_run_id for item in backfill.datasets
    ]
    assert [item.attempt_id for item in normal.datasets] != [
        item.attempt_id for item in backfill.datasets
    ]


def test_concurrent_same_dataset_run_allows_exactly_one_owner() -> None:
    repository = InMemoryIngestionAuditRepository(
        clock=FrozenClock(datetime(2026, 8, 14, tzinfo=UTC))
    )
    barrier = Barrier(2)

    def claim(owner: str) -> IngestionLease | str:
        barrier.wait()
        try:
            return repository.claim(
                source_release_id=f"olist_{'a' * 64}",
                ingestion_batch_id=f"batch_{'b' * 64}",
                dataset_run_id=f"dsrun_{'c' * 64}",
                owner=owner,
                trace_id="m2-concurrency",
            )
        except IngestionLeaseUnavailable as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(claim, ("airflow.worker.one", "airflow.worker.two")))

    leases = [item for item in outcomes if isinstance(item, IngestionLease)]
    failures = [item for item in outcomes if isinstance(item, str)]
    assert len(leases) == 1
    assert failures == ["INGESTION_LEASE_UNAVAILABLE"]
    assert len(repository.state_events) == 1
