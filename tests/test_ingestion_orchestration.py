from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from reviewlens.ingestion.bronze import BronzeLoadStatus
from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.ingestion.identity import (
    attempt_id,
    dataset_run_id,
    ingestion_batch_id,
    source_object_id,
)
from reviewlens.ingestion.orchestration import (
    AirflowIngestionTaskError,
    AirflowTaskRouter,
    ArtifactContext,
    BronzeDatasetResult,
    BronzeIngestionResult,
    DatasetUploadContext,
    DatasetValidationContext,
    LocalAirflowIngestionRunner,
    UploadedIngestionContext,
    ValidatedIngestionContext,
)
from reviewlens.synthetic.generator import generate_fixture

SOURCE_RELEASE_ID = f"olist_{'0' * 64}"
BATCH_ID = ingestion_batch_id(source_release_id=SOURCE_RELEASE_ID)
INSTANT = datetime(2026, 8, 5, tzinfo=UTC)


def _validated_context() -> ValidatedIngestionContext:
    contract = load_olist_contract()
    datasets = []
    for ordinal, dataset in enumerate(contract.datasets, start=1):
        source_sha256 = f"{ordinal:x}" * 64
        current_object_id = source_object_id(
            source_release_id=SOURCE_RELEASE_ID,
            file_name=dataset.file_name,
            source_object_sha256=source_sha256,
        )
        current_run_id = dataset_run_id(
            ingestion_batch_id=BATCH_ID,
            source_object_id=current_object_id,
            dataset_name=dataset.dataset_name,
            contract_version=contract.contract_version,
        )
        datasets.append(
            DatasetValidationContext(
                dataset_name=dataset.dataset_name,
                file_name=dataset.file_name,
                source_sha256=source_sha256,
                source_size_bytes=100 + ordinal,
                source_rows=10,
                source_object_id=current_object_id,
                dataset_run_id=current_run_id,
                attempt_id=attempt_id(dataset_run_id=current_run_id, attempt_number=1),
            )
        )
    return ValidatedIngestionContext(
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        source_snapshot_date=date(2026, 8, 5),
        ingested_at=INSTANT,
        attempt_number=1,
        trace_id="m2-ingestion:synthetic",
        datasets=tuple(datasets),
    )


def _uploaded_context() -> UploadedIngestionContext:
    validated = _validated_context()
    datasets = tuple(
        DatasetUploadContext(
            validation=item,
            observed_rows=10,
            new_rows=10,
            replay_rows=0,
            duplicate_rows=0,
            rejected_rows=0,
            parse_failed_rows=0,
            raw_artifact=ArtifactContext(
                object_key=(
                    f"raw/{item.dataset_name}/source_release_id={SOURCE_RELEASE_ID}/"
                    f"batch_id={BATCH_ID}/part-00000.parquet"
                ),
                manifest_key=(
                    f"raw/{item.dataset_name}/source_release_id={SOURCE_RELEASE_ID}/"
                    f"batch_id={BATCH_ID}/part-00000.parquet.manifest.json"
                ),
                row_count=10,
                size_bytes=1_024,
                sha256="a" * 64,
                replayed=False,
            ),
            quarantine_artifacts=(),
        )
        for item in validated.datasets
    )
    return UploadedIngestionContext(
        validation=validated,
        source_objects_uploaded=10,
        source_objects_replayed=0,
        source_objects_verified=10,
        datasets=datasets,
    )


def _bronze_result() -> BronzeIngestionResult:
    return BronzeIngestionResult(
        source_release_id=SOURCE_RELEASE_ID,
        ingestion_batch_id=BATCH_ID,
        reconciled=True,
        issue_count=0,
        datasets=tuple(
            BronzeDatasetResult(
                dataset_name=dataset.dataset_name,
                copy_status=BronzeLoadStatus.LOADED,
                query_id=f"query-{ordinal}",
                rows_loaded=10,
                bronze_rows=10,
                distinct_record_hashes=10,
            )
            for ordinal, dataset in enumerate(load_olist_contract().datasets, start=1)
        ),
    )


@dataclass
class FakeRunner:
    validate_calls: int = 0
    upload_calls: int = 0
    copy_calls: int = 0

    def validate_source(self) -> ValidatedIngestionContext:
        self.validate_calls += 1
        return _validated_context()

    def upload_to_r2(self, context: ValidatedIngestionContext) -> UploadedIngestionContext:
        assert context == _validated_context()
        self.upload_calls += 1
        return _uploaded_context()

    def copy_to_bronze(self, context: UploadedIngestionContext) -> BronzeIngestionResult:
        assert context == _uploaded_context()
        self.copy_calls += 1
        return _bronze_result()


@dataclass
class RecoveringRunner(FakeRunner):
    fail_upload_once: bool = True

    def upload_to_r2(self, context: ValidatedIngestionContext) -> UploadedIngestionContext:
        self.upload_calls += 1
        if self.fail_upload_once:
            self.fail_upload_once = False
            raise RuntimeError("seeded-private-review-canary")
        assert context == _validated_context()
        return _uploaded_context()


def test_airflow_router_runs_typed_three_task_handoff_and_replays_stably() -> None:
    runner = FakeRunner()
    router = AirflowTaskRouter(runner)

    validated = router.execute("validate_source")
    uploaded = router.execute("upload_to_r2", validated)
    copied = router.execute("copy_to_bronze", uploaded)
    replayed_upload = router.execute("upload_to_r2", validated)
    replayed_copy = router.execute("copy_to_bronze", replayed_upload)

    assert copied == replayed_copy
    assert (runner.validate_calls, runner.upload_calls, runner.copy_calls) == (1, 2, 2)
    assert copied["reconciled"] is True
    assert len(copied["datasets"]) == 9
    assert "review_comment_message" not in repr((validated, uploaded, copied))


def test_failed_upload_is_sanitized_and_retry_resumes_before_copy() -> None:
    runner = RecoveringRunner()
    router = AirflowTaskRouter(runner)
    validated = router.execute("validate_source")

    with pytest.raises(AirflowIngestionTaskError) as captured:
        router.execute("upload_to_r2", validated)

    assert str(captured.value) == "AIRFLOW_INGESTION_TASK_FAILED"
    assert "seeded-private-review-canary" not in str(captured.value)
    assert runner.copy_calls == 0

    uploaded = router.execute("upload_to_r2", validated)
    copied = router.execute("copy_to_bronze", uploaded)
    assert copied["reconciled"] is True
    assert (runner.upload_calls, runner.copy_calls) == (2, 1)


@pytest.mark.parametrize(
    ("task_name", "payload"),
    [
        ("validate_source", {}),
        ("upload_to_r2", None),
        ("copy_to_bronze", None),
        ("unknown_task", None),
        ("upload_to_r2", {"seeded-private-review-canary": "value"}),
    ],
)
def test_airflow_router_rejects_invalid_handoffs_with_sanitized_error(
    task_name: str,
    payload: dict[str, Any] | None,
) -> None:
    router = AirflowTaskRouter(FakeRunner())

    with pytest.raises(AirflowIngestionTaskError) as captured:
        router.execute(task_name, payload)

    assert str(captured.value) == "AIRFLOW_INGESTION_TASK_FAILED"
    assert "seeded-private-review-canary" not in str(captured.value)


def test_context_contract_rejects_duplicate_or_missing_dataset() -> None:
    context = _validated_context()
    invalid = context.model_dump()
    invalid["datasets"] = list(invalid["datasets"])
    invalid["datasets"][-1] = invalid["datasets"][0]

    with pytest.raises(ValueError):
        ValidatedIngestionContext.model_validate(invalid)


def test_runtime_constructor_fails_closed_without_explicit_olist_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REVIEWLENS_ENABLE_OLIST_PIPELINE", raising=False)
    monkeypatch.setenv("REVIEWLENS_SOURCE_DIR", "seeded-private-review-canary")
    monkeypatch.setenv("REVIEWLENS_OUTPUT_DIR", "ignored-output")

    with pytest.raises(AirflowIngestionTaskError) as captured:
        LocalAirflowIngestionRunner.from_environment()

    assert "seeded-private-review-canary" not in str(captured.value)


def test_runtime_validation_is_deterministic_and_provider_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "fixture"
    generate_fixture(source, seed=20260814)
    output = tmp_path / "private-output"
    monkeypatch.setenv("REVIEWLENS_ENABLE_OLIST_PIPELINE", "1")
    monkeypatch.setenv("REVIEWLENS_SOURCE_DIR", str(source))
    monkeypatch.setenv("REVIEWLENS_OUTPUT_DIR", str(output))
    runner = LocalAirflowIngestionRunner.from_environment()

    first = runner.validate_source()
    second = runner.validate_source()

    assert first == second
    assert len(first.datasets) == 9
    assert first.source_release_id.startswith("olist_")
    assert not output.exists()
    assert str(tmp_path) not in repr(first)
