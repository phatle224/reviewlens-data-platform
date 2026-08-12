from __future__ import annotations

import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from reviewlens.config import AppSettings, DataMode
from reviewlens.ingestion.contracts import load_olist_contract
from reviewlens.ingestion.preflight import (
    PreflightCode,
    PrivacyPreflightEvidence,
    UploadPreflightDenied,
    approved_source_release_id,
    load_approved_olist_snapshot,
    run_upload_preflight,
)
from reviewlens.ingestion.source import CanonicalManifestFile, CanonicalSourceManifest


def _settings() -> AppSettings:
    with Path("config/config.toml").open("rb") as handle:
        payload = tomllib.load(handle)
    payload["data_mode"] = "olist"
    return AppSettings.model_validate(payload)


def _approved_manifest() -> CanonicalSourceManifest:
    approved = load_approved_olist_snapshot()
    contract = load_olist_contract()
    files = tuple(
        CanonicalManifestFile(
            file_name=item.file_name,
            dataset_name=contract.by_file_name[item.file_name].dataset_name,
            required=True,
            bytes=item.bytes,
            sha256=item.sha256,
            expected_header=contract.by_file_name[item.file_name].expected_header,
            observed_rows=item.rows,
            data_class=contract.by_file_name[item.file_name].data_class.value,
            license_id=contract.license_id,
        )
        for item in sorted(approved.files, key=lambda value: value.file_name)
    )
    return CanonicalSourceManifest(
        source_name=approved.source_name,
        source_snapshot_date=approved.source_snapshot_date,
        source_release_id=approved_source_release_id(approved),
        contract_version=contract.contract_version,
        manifest_version=contract.manifest_version,
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
        files=files,
    )


def _privacy_evidence() -> PrivacyPreflightEvidence:
    return PrivacyPreflightEvidence(
        policy_version="m0-security-privacy-v1",
        raw_data_outside_git=True,
        private_processing_only=True,
        external_ai_transfer_disabled=True,
        public_row_level_evidence_disabled=True,
        restricted_reviews_classified=True,
        source_privacy_scan_passed=True,
        non_commercial_confirmed=True,
        share_alike_confirmed=True,
        change_notice_confirmed=True,
        no_endorsement_confirmed=True,
    )


def _attribution() -> str:
    return Path("docs/DATA_ATTRIBUTION.md").read_text(encoding="utf-8")


def test_complete_metadata_preflight_issues_deterministic_authorization() -> None:
    first = run_upload_preflight(
        settings=_settings(),
        manifest=_approved_manifest(),
        privacy_evidence=_privacy_evidence(),
        attribution_text=_attribution(),
    )
    second = run_upload_preflight(
        settings=_settings(),
        manifest=_approved_manifest().model_copy(
            update={"created_at": datetime(2030, 1, 1, tzinfo=UTC)}
        ),
        privacy_evidence=_privacy_evidence(),
        attribution_text=_attribution(),
    )

    assert first.approved
    assert first.denial_codes == ()
    assert len(first.passed_checks) == 6
    assert first.authorization_id == second.authorization_id
    assert first.require_approved().startswith("uploadauth_")


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("synthetic_mode", PreflightCode.DATA_MODE_NOT_OLIST),
        ("public_r2", PreflightCode.PRIVATE_DESTINATION_REQUIRED),
        ("source_drift", PreflightCode.SOURCE_SNAPSHOT_MISMATCH),
        ("attribution_missing", PreflightCode.ATTRIBUTION_INCOMPLETE),
        ("privacy_incomplete", PreflightCode.PRIVACY_EVIDENCE_INCOMPLETE),
    ],
)
def test_preflight_denies_each_missing_gate(mutation: str, expected_code: PreflightCode) -> None:
    settings = _settings()
    manifest = _approved_manifest()
    evidence = _privacy_evidence()
    attribution = _attribution()
    if mutation == "synthetic_mode":
        settings = settings.model_copy(update={"data_mode": DataMode.SYNTHETIC})
    elif mutation == "public_r2":
        settings = settings.model_copy(
            update={"r2": settings.r2.model_copy(update={"public_access": True})}
        )
    elif mutation == "source_drift":
        manifest = manifest.model_copy(update={"source_release_id": f"olist_{'0' * 64}"})
    elif mutation == "attribution_missing":
        attribution = "Olist"
    else:
        evidence = evidence.model_copy(update={"source_privacy_scan_passed": False})

    decision = run_upload_preflight(
        settings=settings,
        manifest=manifest,
        privacy_evidence=evidence,
        attribution_text=attribution,
    )

    assert not decision.approved
    assert expected_code in decision.denial_codes
    assert decision.authorization_id is None
    with pytest.raises(UploadPreflightDenied, match="OLIST_UPLOAD_PREFLIGHT_DENIED"):
        decision.require_approved()


def test_preflight_decision_and_error_exclude_paths_rows_and_secrets(tmp_path: Path) -> None:
    seeded = "seeded-private-review-and-secret"
    decision = run_upload_preflight(
        settings=_settings().model_copy(update={"data_mode": DataMode.SYNTHETIC}),
        manifest=_approved_manifest(),
        privacy_evidence=_privacy_evidence(),
        attribution_text=f"{_attribution()} {seeded} {tmp_path}",
    )

    serialized = decision.model_dump_json()
    assert seeded not in serialized
    assert str(tmp_path) not in serialized


def test_preflight_module_has_no_provider_environment_or_source_row_access() -> None:
    source = Path("src/reviewlens/ingestion/preflight.py").read_text(encoding="utf-8")

    assert "reviewlens.providers" not in source
    assert "load_settings" not in source
    assert "dotenv" not in source
    assert "boto3" not in source
    assert "snowflake.connector" not in source
    assert "iter_csv_records" not in source
