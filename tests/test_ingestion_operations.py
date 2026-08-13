from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.observability.ingestion import (
    DatasetIngestionMetrics,
    IngestionAlertCode,
    IngestionOperationsSnapshot,
    build_ingestion_metrics_payload,
    evaluate_ingestion_alerts,
    write_ingestion_operations_artifacts,
)


def _snapshot(**overrides: object) -> IngestionOperationsSnapshot:
    payload: dict[str, object] = {
        "source_release_id": f"olist_{'a' * 64}",
        "ingestion_batch_id": f"batch_{'b' * 64}",
        "run_state": "RECONCILED",
        "task_error_count": 0,
        "replayed_object_count": 10,
        "warehouse_suspended": True,
        "datasets": [
            {
                "dataset_name": dataset.dataset_name,
                "source_rows": 10,
                "accepted_rows": 10,
                "quarantined_rows": 0,
                "parse_failed_rows": 0,
                "bronze_rows": 10,
                "duration_seconds": 0.5,
            }
            for dataset in load_olist_contract().datasets
        ],
    }
    payload.update(overrides)
    return IngestionOperationsSnapshot.model_validate(payload)


def test_healthy_snapshot_has_no_alert_and_metrics_are_metadata_only() -> None:
    snapshot = _snapshot()

    alerts = evaluate_ingestion_alerts(snapshot)
    payload = build_ingestion_metrics_payload(snapshot).decode("utf-8")

    assert alerts == ()
    assert 'dataset="orders"' in payload
    assert 'outcome="bronze"' in payload
    assert "reviewlens_ingestion_reconciled 1.0" in payload
    assert "reviewlens_ingestion_warehouse_suspended 1.0" in payload
    assert snapshot.source_release_id not in payload
    assert snapshot.ingestion_batch_id not in payload
    assert "review_comment_message" not in payload


def test_alerts_cover_reconciliation_quarantine_error_and_cleanup() -> None:
    datasets = [item.model_dump() for item in _snapshot().datasets]
    datasets[0].update(
        source_rows=10,
        accepted_rows=8,
        quarantined_rows=2,
        bronze_rows=7,
    )
    snapshot = _snapshot(
        run_state="FAILED",
        task_error_count=1,
        warehouse_suspended=False,
        datasets=datasets,
    )

    assert evaluate_ingestion_alerts(snapshot, quarantine_rate_threshold=0.01) == (
        IngestionAlertCode.RECONCILIATION_FAILED,
        IngestionAlertCode.QUARANTINE_RATE_HIGH,
        IngestionAlertCode.TASK_ERRORS_PRESENT,
        IngestionAlertCode.WAREHOUSE_CLEANUP_REQUIRED,
    )
    payload = build_ingestion_metrics_payload(snapshot).decode("utf-8")
    assert "reviewlens_ingestion_reconciled 0.0" in payload
    assert "reviewlens_ingestion_task_errors 1.0" in payload


def test_metrics_contract_rejects_unexplained_rows_or_dataset_drift() -> None:
    with pytest.raises(ValidationError):
        DatasetIngestionMetrics(
            dataset_name="orders",
            source_rows=10,
            accepted_rows=9,
            quarantined_rows=0,
            parse_failed_rows=0,
            bronze_rows=9,
            duration_seconds=1,
        )

    datasets = [item.model_dump() for item in _snapshot().datasets]
    datasets[-1] = datasets[0]
    with pytest.raises(ValidationError):
        _snapshot(datasets=datasets)

    with pytest.raises(ValueError, match="between zero and one"):
        evaluate_ingestion_alerts(_snapshot(), quarantine_rate_threshold=1.01)


def test_operations_artifacts_are_atomic_bounded_and_identifier_free(tmp_path: Path) -> None:
    snapshot = _snapshot()

    metrics_path, alerts_path = write_ingestion_operations_artifacts(
        snapshot,
        output_root=tmp_path,
    )
    first_metrics = metrics_path.read_bytes()
    first_alerts = alerts_path.read_bytes()
    write_ingestion_operations_artifacts(snapshot, output_root=tmp_path)

    assert metrics_path.read_bytes() == first_metrics
    assert alerts_path.read_bytes() == first_alerts
    assert json.loads(first_alerts) == {
        "schema_version": "reviewlens-ingestion-alerts-v1",
        "alerts": [],
    }
    combined = first_metrics + first_alerts
    assert snapshot.source_release_id.encode() not in combined
    assert snapshot.ingestion_batch_id.encode() not in combined
    assert not tuple((tmp_path / "operations").glob("tmp*"))


def test_operations_artifact_writer_rejects_symlink_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this host")

    with pytest.raises(ValueError, match="must not be a symlink"):
        write_ingestion_operations_artifacts(_snapshot(), output_root=alias)


def test_m2_operations_runbook_covers_private_replay_and_recovery() -> None:
    runbook = Path("docs/runbooks/M2_INGESTION_OPERATIONS.md").read_text(encoding="utf-8")

    for required in (
        "REVIEWLENS_ENABLE_OLIST_PIPELINE=1",
        "REVIEWLENS_BACKFILL_ATTEMPT_NUMBER=2",
        "airflow dags trigger olist_pipeline",
        "INGESTION_RECONCILIATION_FAILED",
        "INGESTION_QUARANTINE_RATE_HIGH",
        "INGESTION_TASK_ERRORS_PRESENT",
        "INGESTION_WAREHOUSE_CLEANUP_REQUIRED",
        "docker compose down",
    ):
        assert required in runbook
    normalized = " ".join(runbook.lower().split())
    assert "không xóa hoặc overwrite" in normalized
    assert "không đưa raw data" in normalized
