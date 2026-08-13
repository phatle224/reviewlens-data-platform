from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.ingestion.reconciliation import (
    DatasetReconciliationInput,
    ReconciliationCode,
    ReconciliationInputError,
    reconcile_snapshot,
)


def _baseline(dataset_name: str, *, replay: bool = False) -> DatasetReconciliationInput:
    return DatasetReconciliationInput(
        dataset_name=dataset_name,
        source_observed_rows=13,
        source_new_rows=10,
        source_replay_rows=1,
        source_duplicate_rows=1,
        source_rejected_rows=1,
        source_parse_failed_rows=0,
        local_source_sha256="a" * 64,
        r2_source_sha256="a" * 64,
        local_raw_rows=10,
        local_raw_size_bytes=1_024,
        local_raw_sha256="b" * 64,
        r2_raw_size_bytes=1_024,
        r2_raw_sha256="b" * 64,
        copy_rows_loaded=0 if replay else 10,
        copy_replay=replay,
        bronze_batch_rows=10,
        bronze_distinct_record_hashes=10,
    )


def _nine_inputs(*, replay: bool = False) -> tuple[DatasetReconciliationInput, ...]:
    return tuple(
        _baseline(dataset.dataset_name, replay=replay) for dataset in load_olist_contract().datasets
    )


def test_all_nine_datasets_reconcile_for_initial_and_replay_copy() -> None:
    initial = reconcile_snapshot(_nine_inputs())
    replay = reconcile_snapshot(_nine_inputs(replay=True))

    assert initial.reconciled and initial.issue_count == 0
    assert replay.reconciled and replay.issue_count == 0
    assert len(initial.dataset_results) == 9


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda item: replace(item, source_observed_rows=14),
            ReconciliationCode.SOURCE_DISPOSITION_MISMATCH,
        ),
        (
            lambda item: replace(item, r2_source_sha256="c" * 64),
            ReconciliationCode.SOURCE_ARCHIVE_HASH_MISMATCH,
        ),
        (lambda item: replace(item, local_raw_rows=9), ReconciliationCode.RAW_ROW_MISMATCH),
        (
            lambda item: replace(item, r2_raw_size_bytes=1_023),
            ReconciliationCode.RAW_R2_BYTES_MISMATCH,
        ),
        (
            lambda item: replace(item, r2_raw_sha256="c" * 64),
            ReconciliationCode.RAW_R2_HASH_MISMATCH,
        ),
        (lambda item: replace(item, copy_rows_loaded=9), ReconciliationCode.COPY_ROW_MISMATCH),
        (
            lambda item: replace(item, bronze_batch_rows=9),
            ReconciliationCode.BRONZE_ROW_MISMATCH,
        ),
        (
            lambda item: replace(item, bronze_distinct_record_hashes=9),
            ReconciliationCode.BRONZE_DUPLICATE_EFFECT,
        ),
    ],
)
def test_reconciliation_reports_stable_metadata_only_issue_codes(
    mutation: Callable[[DatasetReconciliationInput], DatasetReconciliationInput],
    expected: ReconciliationCode,
) -> None:
    inputs = list(_nine_inputs())
    inputs[0] = mutation(inputs[0])

    report = reconcile_snapshot(tuple(inputs))
    mutated_result = next(
        result for result in report.dataset_results if result.dataset_name == inputs[0].dataset_name
    )

    assert not report.reconciled
    assert expected in mutated_result.issues
    assert "seeded-private-review-canary" not in repr(report).lower()


def test_reconciliation_requires_exact_nine_dataset_set() -> None:
    missing = reconcile_snapshot(_nine_inputs()[:-1])
    duplicated = reconcile_snapshot((*_nine_inputs()[:-1], _nine_inputs()[0]))

    assert missing.snapshot_issues == (ReconciliationCode.DATASET_SET_MISMATCH,)
    assert duplicated.snapshot_issues == (ReconciliationCode.DATASET_SET_MISMATCH,)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda item: replace(item, source_observed_rows=-1),
        lambda item: replace(item, local_source_sha256="seeded-private-review-canary"),
    ],
)
def test_invalid_reconciliation_input_is_sanitized(
    mutation: Callable[[DatasetReconciliationInput], DatasetReconciliationInput],
) -> None:
    inputs = list(_nine_inputs())
    inputs[0] = mutation(inputs[0])

    with pytest.raises(ReconciliationInputError) as captured:
        reconcile_snapshot(tuple(inputs))

    assert str(captured.value) == "RECONCILIATION_INPUT_INVALID"
    assert "seeded-private-review-canary" not in str(captured.value)
