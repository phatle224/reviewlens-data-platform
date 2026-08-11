from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from reviewlens.ingestion.contracts import (
    EXPECTED_OLIST_DATASETS,
    EXPECTED_OLIST_FILES,
    DataClass,
    IdentitySemantics,
    LogicalType,
    SourceContractError,
    load_olist_contract,
    parse_source_contract,
)
from reviewlens.ingestion.source import (
    COMPLETION_MANIFEST_NAME,
    CanonicalSourceManifest,
    SourceDiscoveryCode,
    SourceDiscoveryError,
    SourceReleaseDisposition,
    build_canonical_manifest,
    classify_source_release,
    discover_source_snapshot,
)
from reviewlens.synthetic.generator import generate_fixture


def _manifest_path(root: Path) -> Path:
    return root / COMPLETION_MANIFEST_NAME


def _read_manifest(root: Path) -> dict[str, Any]:
    value = json.loads(_manifest_path(root).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_manifest(root: Path, value: dict[str, Any]) -> None:
    _manifest_path(root).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _refresh_manifest_file(root: Path, file_name: str) -> None:
    manifest = _read_manifest(root)
    body = (root / file_name).read_bytes()
    entry = next(item for item in manifest["files"] if item["filename"] == file_name)
    entry["bytes"] = len(body)
    entry["sha256"] = hashlib.sha256(body).hexdigest()
    _write_manifest(root, manifest)


def _discover_generated(root: Path) -> Any:
    generate_fixture(root)
    return discover_source_snapshot(root)


def _leave_directory_missing(_root: Path) -> None:
    return


def _remove_completion_manifest(root: Path) -> None:
    generate_fixture(root)
    _manifest_path(root).unlink()


def _remove_required_file(root: Path) -> None:
    generate_fixture(root)
    (root / "olist_customers_dataset.csv").unlink()


def _add_extra_entry(root: Path) -> None:
    generate_fixture(root)
    (root / "unexpected.txt").write_text("x", encoding="utf-8")


def _canonical(root: Path, *, day: int = 5, hour: int = 12) -> CanonicalSourceManifest:
    return build_canonical_manifest(
        discover_source_snapshot(root),
        source_snapshot_date=date(2026, 8, day),
        created_at=datetime(2026, 8, 12, hour, tzinfo=UTC),
    )


def test_olist_contract_is_exact_typed_and_privacy_classified() -> None:
    contract = load_olist_contract()

    assert contract.contract_version == "olist-source-v1"
    assert contract.manifest_version == "olist-manifest-v1"
    assert contract.license_id == "CC-BY-NC-SA-4.0"
    assert set(contract.required_file_names) == EXPECTED_OLIST_FILES
    assert {item.dataset_name for item in contract.datasets} == EXPECTED_OLIST_DATASETS
    assert len(contract.datasets) == 9
    assert all(item.required for item in contract.datasets)

    reviews = contract.by_file_name["olist_order_reviews_dataset.csv"]
    assert reviews.data_class is DataClass.RESTRICTED
    assert reviews.identity_fields == ("review_id", "order_id")
    assert reviews.identity_semantics is IdentitySemantics.UNIQUE
    assert reviews.columns[2].logical_type is LogicalType.INTEGER
    assert reviews.columns[3].nullable is True
    assert reviews.columns[4].nullable is True

    geolocation = contract.by_file_name["olist_geolocation_dataset.csv"]
    assert geolocation.identity_semantics is IdentitySemantics.OCCURRENCE
    products = contract.by_file_name["olist_products_dataset.csv"]
    assert "product_name_lenght" in products.expected_header
    assert "product_name_length" not in products.expected_header


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"seeded_secret": "do-not-leak"}),
        lambda value: value["datasets"].pop(),
        lambda value: value["datasets"][1].update({"file_name": value["datasets"][0]["file_name"]}),
        lambda value: value["datasets"][0]["columns"][0].update({"logical_type": "binary"}),
        lambda value: value["datasets"][0].update({"identity_fields": ["missing_column"]}),
        lambda value: value["datasets"][0].update({"required": False}),
        lambda value: value.update({"license_id": "MIT"}),
    ],
)
def test_contract_mutations_fail_closed_without_payload_leak(mutation: Any) -> None:
    payload = copy.deepcopy(load_olist_contract().model_dump(mode="json"))
    mutation(payload)

    with pytest.raises(SourceContractError) as captured:
        parse_source_contract(payload)

    assert str(captured.value) == "SOURCE_CONTRACT_INVALID"
    assert "do-not-leak" not in str(captured.value)


def test_complete_synthetic_snapshot_is_discovered_in_canonical_order(tmp_path: Path) -> None:
    snapshot = _discover_generated(tmp_path)

    assert len(snapshot.files) == 9
    assert tuple(item.file_name for item in snapshot.files) == tuple(sorted(EXPECTED_OLIST_FILES))
    assert snapshot.contract_version == "olist-source-v1"
    assert snapshot.manifest_version == "olist-manifest-v1"
    assert all(item.path.parent == tmp_path.resolve() for item in snapshot.files)
    dumped = snapshot.model_dump(mode="json")
    assert "root" not in dumped
    assert all("path" not in item for item in dumped["files"])


def test_completion_manifest_file_order_does_not_change_discovery(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    manifest = _read_manifest(tmp_path)
    manifest["files"].reverse()
    _write_manifest(tmp_path, manifest)

    snapshot = discover_source_snapshot(tmp_path)

    assert tuple(item.file_name for item in snapshot.files) == tuple(sorted(EXPECTED_OLIST_FILES))


@pytest.mark.parametrize(
    ("arrange", "expected_code"),
    [
        (_leave_directory_missing, SourceDiscoveryCode.SOURCE_DIRECTORY_MISSING),
        (_remove_completion_manifest, SourceDiscoveryCode.COMPLETION_MANIFEST_MISSING),
        (_remove_required_file, SourceDiscoveryCode.MISSING_REQUIRED_FILE),
        (_add_extra_entry, SourceDiscoveryCode.EXTRA_SOURCE_ENTRY),
    ],
)
def test_source_directory_shape_failures_are_deterministic(
    tmp_path: Path,
    arrange: Callable[[Path], None],
    expected_code: SourceDiscoveryCode,
) -> None:
    root = tmp_path / "snapshot"
    arrange(root)

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(root)

    assert captured.value.code is expected_code


def test_source_root_must_be_a_directory(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.write_text("not-a-directory", encoding="utf-8")

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(root)

    assert captured.value.code is SourceDiscoveryCode.SOURCE_DIRECTORY_INVALID


def test_malformed_completion_manifest_is_rejected(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    _manifest_path(tmp_path).write_text("{malformed", encoding="utf-8")

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(tmp_path)

    assert captured.value.code is SourceDiscoveryCode.COMPLETION_MANIFEST_INVALID


def test_completion_manifest_contract_version_must_match(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    manifest = _read_manifest(tmp_path)
    manifest["contract_version"] = "olist-source-v0"
    _write_manifest(tmp_path, manifest)

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(tmp_path)

    assert captured.value.code is SourceDiscoveryCode.COMPLETION_MANIFEST_INVALID


def test_duplicate_completion_manifest_file_is_rejected(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    manifest = _read_manifest(tmp_path)
    manifest["files"].append(copy.deepcopy(manifest["files"][0]))
    _write_manifest(tmp_path, manifest)

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(tmp_path)

    assert captured.value.code is SourceDiscoveryCode.DUPLICATE_MANIFEST_FILE


def test_completion_manifest_file_set_must_match_contract(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    manifest = _read_manifest(tmp_path)
    manifest["files"].pop()
    _write_manifest(tmp_path, manifest)

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(tmp_path)

    assert captured.value.code is SourceDiscoveryCode.MANIFEST_FILE_SET_MISMATCH


def test_changed_file_size_is_rejected_before_hash_or_header(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    target = tmp_path / "olist_customers_dataset.csv"
    target.write_bytes(target.read_bytes() + b"x")

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(tmp_path)

    assert captured.value.code is SourceDiscoveryCode.FILE_SIZE_MISMATCH
    assert captured.value.file_name == target.name


def test_same_size_checksum_change_is_rejected(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    target = tmp_path / "olist_customers_dataset.csv"
    body = target.read_bytes()
    target.write_bytes(body.replace(b"synthetic_", b"synthetix_", 1))
    assert target.stat().st_size == len(body)

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(tmp_path)

    assert captured.value.code is SourceDiscoveryCode.FILE_CHECKSUM_MISMATCH


def test_header_mismatch_is_rejected_after_integrity_refresh(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    file_name = "olist_customers_dataset.csv"
    target = tmp_path / file_name
    body = target.read_text(encoding="utf-8")
    target.write_text(body.replace("customer_id", "customer_key", 1), encoding="utf-8")
    _refresh_manifest_file(tmp_path, file_name)

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(tmp_path)

    assert captured.value.code is SourceDiscoveryCode.HEADER_MISMATCH


def test_invalid_utf8_header_is_rejected_without_content_leak(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    file_name = "olist_customers_dataset.csv"
    target = tmp_path / file_name
    body = target.read_bytes()
    seeded_canary = b"seeded-private-row-canary"
    target.write_bytes(b"\xff" + body[1:] + seeded_canary)
    _refresh_manifest_file(tmp_path, file_name)

    with pytest.raises(SourceDiscoveryError) as captured:
        discover_source_snapshot(tmp_path)

    assert captured.value.code is SourceDiscoveryCode.HEADER_INVALID
    assert seeded_canary.decode() not in str(captured.value)
    assert str(tmp_path.resolve()) not in str(captured.value)


def test_canonical_manifest_is_path_free_sorted_and_complete(tmp_path: Path) -> None:
    _discover_generated(tmp_path)
    manifest = _canonical(tmp_path)
    serialized = manifest.to_json()

    assert manifest.source_name == "olist"
    assert manifest.source_snapshot_date == date(2026, 8, 5)
    assert manifest.source_release_id.startswith("olist_")
    assert len(manifest.source_release_id) == 70
    assert len(manifest.files) == 9
    assert tuple(item.file_name for item in manifest.files) == tuple(sorted(EXPECTED_OLIST_FILES))
    assert all(item.license_id == "CC-BY-NC-SA-4.0" for item in manifest.files)
    assert str(tmp_path.resolve()) not in serialized
    assert "seeded-private-row-canary" not in serialized
    assert serialized == manifest.to_json()


def test_source_release_id_ignores_path_order_and_runtime_fields(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    generate_fixture(first_root)
    generate_fixture(second_root)
    first_snapshot = discover_source_snapshot(first_root)
    second_snapshot = discover_source_snapshot(second_root).model_copy(
        update={"files": tuple(reversed(discover_source_snapshot(second_root).files))}
    )

    first = build_canonical_manifest(
        first_snapshot,
        source_snapshot_date=date(2026, 8, 5),
        created_at=datetime(2026, 8, 12, 1, tzinfo=UTC),
    )
    second = build_canonical_manifest(
        second_snapshot,
        source_snapshot_date=date(2030, 1, 1),
        created_at=datetime(2030, 1, 1, 1, tzinfo=UTC),
    )

    assert first.source_release_id == second.source_release_id
    assert classify_source_release(first, second) is SourceReleaseDisposition.REPLAY


def test_same_filename_with_changed_bytes_is_new_candidate(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    generate_fixture(first_root)
    generate_fixture(second_root)
    file_name = "olist_customers_dataset.csv"
    target = second_root / file_name
    target.write_bytes(target.read_bytes().replace(b"synthetic_", b"synthetix_", 1))
    _refresh_manifest_file(second_root, file_name)

    first = _canonical(first_root)
    second = _canonical(second_root)

    assert first.source_release_id != second.source_release_id
    assert classify_source_release(first, second) is SourceReleaseDisposition.NEW_CANDIDATE


def test_same_release_id_with_stable_metadata_drift_is_conflict(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    existing = _canonical(tmp_path)
    conflicting = existing.model_copy(update={"manifest_version": "olist-manifest-v2"})

    with pytest.raises(SourceDiscoveryError) as captured:
        classify_source_release(existing, conflicting)

    assert captured.value.code is SourceDiscoveryCode.SOURCE_RELEASE_CONFLICT


def test_canonical_manifest_requires_timezone_aware_created_at(tmp_path: Path) -> None:
    snapshot = _discover_generated(tmp_path)

    with pytest.raises(ValidationError, match="timezone-aware"):
        build_canonical_manifest(
            snapshot,
            source_snapshot_date=date(2026, 8, 5),
            created_at=datetime(2026, 8, 12, 12),
        )


def test_runtime_time_change_is_replay_not_conflict(tmp_path: Path) -> None:
    generate_fixture(tmp_path)
    existing = _canonical(tmp_path)
    replay = existing.model_copy(
        update={
            "source_snapshot_date": existing.source_snapshot_date + timedelta(days=1),
            "created_at": existing.created_at + timedelta(hours=5),
        }
    )

    assert classify_source_release(existing, replay) is SourceReleaseDisposition.REPLAY


def test_ingestion_source_module_has_no_provider_or_environment_access() -> None:
    source = Path("src/reviewlens/ingestion/source.py").read_text(encoding="utf-8")

    assert "reviewlens.providers" not in source
    assert "load_environment_values" not in source
    assert "dotenv" not in source
    assert "boto3" not in source
    assert "snowflake.connector" not in source
