"""Fail-closed license, privacy and approved-snapshot gate for real Olist upload."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from reviewlens.config import AppSettings, DataMode
from reviewlens.ingestion.contracts import EXPECTED_OLIST_FILES, load_olist_contract
from reviewlens.ingestion.source import CanonicalSourceManifest


class PreflightCode(StrEnum):
    DATA_MODE_NOT_OLIST = "DATA_MODE_NOT_OLIST"
    PRIVATE_DESTINATION_REQUIRED = "PRIVATE_DESTINATION_REQUIRED"
    LICENSE_CONTRACT_INVALID = "LICENSE_CONTRACT_INVALID"
    SOURCE_SNAPSHOT_MISMATCH = "SOURCE_SNAPSHOT_MISMATCH"
    ATTRIBUTION_INCOMPLETE = "ATTRIBUTION_INCOMPLETE"
    PRIVACY_EVIDENCE_INCOMPLETE = "PRIVACY_EVIDENCE_INCOMPLETE"


class UploadPreflightDenied(RuntimeError):
    code = "OLIST_UPLOAD_PREFLIGHT_DENIED"

    def __init__(self) -> None:
        super().__init__(self.code)


class ApprovedSnapshotFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    file_name: str
    rows: int = Field(ge=0)
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApprovedSourceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_version: str = Field(pattern=r"^olist-approved-snapshot-v[1-9][0-9]*$")
    source_name: str
    source_snapshot_date: date
    files: tuple[ApprovedSnapshotFile, ...]

    @model_validator(mode="after")
    def validate_exact_source(self) -> ApprovedSourceSnapshot:
        names = [item.file_name for item in self.files]
        if self.source_name != "olist" or set(names) != EXPECTED_OLIST_FILES:
            raise ValueError("approved snapshot must contain exact Olist source")
        if len(names) != len(set(names)):
            raise ValueError("approved snapshot filenames must be unique")
        return self


class PrivacyPreflightEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str
    raw_data_outside_git: bool
    private_processing_only: bool
    external_ai_transfer_disabled: bool
    public_row_level_evidence_disabled: bool
    restricted_reviews_classified: bool
    source_privacy_scan_passed: bool
    non_commercial_confirmed: bool
    share_alike_confirmed: bool
    change_notice_confirmed: bool
    no_endorsement_confirmed: bool

    @property
    def complete(self) -> bool:
        values = self.model_dump(exclude={"policy_version"}).values()
        return self.policy_version == "m0-security-privacy-v1" and all(values)


class UploadPreflightDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approved: bool
    source_release_id: str
    approved_snapshot_version: str
    passed_checks: tuple[str, ...]
    denial_codes: tuple[PreflightCode, ...]
    authorization_id: str | None = None

    def require_approved(self) -> str:
        if not self.approved or self.authorization_id is None:
            raise UploadPreflightDenied()
        return self.authorization_id


@lru_cache(maxsize=1)
def load_approved_olist_snapshot() -> ApprovedSourceSnapshot:
    resource = files("reviewlens.ingestion").joinpath("approved_olist_snapshot.json")
    try:
        return ApprovedSourceSnapshot.model_validate_json(resource.read_bytes())
    except (OSError, ValidationError, ValueError):
        raise UploadPreflightDenied() from None


def run_upload_preflight(
    *,
    settings: AppSettings,
    manifest: CanonicalSourceManifest,
    privacy_evidence: PrivacyPreflightEvidence,
    attribution_text: str,
    approved_snapshot: ApprovedSourceSnapshot | None = None,
) -> UploadPreflightDecision:
    """Evaluate metadata only; this function performs no provider or source-row access."""

    approved = approved_snapshot or load_approved_olist_snapshot()
    passed: list[str] = []
    denied: list[PreflightCode] = []

    if settings.data_mode is DataMode.OLIST:
        passed.append("data_mode_olist")
    else:
        denied.append(PreflightCode.DATA_MODE_NOT_OLIST)

    if settings.r2.enabled and not settings.r2.public_access:
        passed.append("private_r2_destination")
    else:
        denied.append(PreflightCode.PRIVATE_DESTINATION_REQUIRED)

    license_config = settings.license
    if (
        license_config.license_id == "CC-BY-NC-SA-4.0"
        and not license_config.commercial_use_allowed
        and license_config.attribution_required
        and license_config.share_alike_required
        and license_config.status == "active"
    ):
        passed.append("license_contract")
    else:
        denied.append(PreflightCode.LICENSE_CONTRACT_INVALID)

    if _manifest_matches_approved(manifest, approved):
        passed.append("approved_source_snapshot")
    else:
        denied.append(PreflightCode.SOURCE_SNAPSHOT_MISMATCH)

    if _attribution_complete(attribution_text):
        passed.append("attribution_and_notices")
    else:
        denied.append(PreflightCode.ATTRIBUTION_INCOMPLETE)

    if privacy_evidence.complete:
        passed.append("privacy_and_dlp_boundary")
    else:
        denied.append(PreflightCode.PRIVACY_EVIDENCE_INCOMPLETE)

    authorization_id = None
    if not denied:
        authorization_id = _authorization_id(
            source_release_id=manifest.source_release_id,
            snapshot_version=approved.snapshot_version,
            policy_version=privacy_evidence.policy_version,
        )
    return UploadPreflightDecision(
        approved=not denied,
        source_release_id=manifest.source_release_id,
        approved_snapshot_version=approved.snapshot_version,
        passed_checks=tuple(passed),
        denial_codes=tuple(denied),
        authorization_id=authorization_id,
    )


def approved_source_release_id(snapshot: ApprovedSourceSnapshot) -> str:
    identity = [
        {"bytes": item.bytes, "file_name": item.file_name, "sha256": item.sha256}
        for item in sorted(snapshot.files, key=lambda value: value.file_name)
    ]
    payload = json.dumps(identity, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"olist_{hashlib.sha256(payload.encode('ascii')).hexdigest()}"


def _manifest_matches_approved(
    manifest: CanonicalSourceManifest,
    approved: ApprovedSourceSnapshot,
) -> bool:
    contract = load_olist_contract()
    expected = {item.file_name: item for item in approved.files}
    actual = {item.file_name: item for item in manifest.files}
    if (
        manifest.source_name != approved.source_name
        or manifest.source_snapshot_date != approved.source_snapshot_date
        or manifest.source_release_id != approved_source_release_id(approved)
        or manifest.contract_version != contract.contract_version
        or manifest.manifest_version != contract.manifest_version
        or set(actual) != set(expected)
    ):
        return False
    for file_name, expected_file in expected.items():
        actual_file = actual[file_name]
        dataset = contract.by_file_name[file_name]
        if (
            actual_file.dataset_name != dataset.dataset_name
            or actual_file.required is not True
            or actual_file.bytes != expected_file.bytes
            or actual_file.sha256 != expected_file.sha256
            or actual_file.observed_rows != expected_file.rows
            or actual_file.expected_header != dataset.expected_header
            or actual_file.data_class != dataset.data_class.value
            or actual_file.license_id != contract.license_id
        ):
            return False
    return True


def _attribution_complete(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    required = (
        "brazilian e-commerce public dataset by olist",
        "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
        "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "noncommercial",
        "sharealike",
        "indication of changes",
        "does not sponsor, approve or endorse reviewlens",
    )
    return all(token in normalized for token in required)


def _authorization_id(
    *,
    source_release_id: str,
    snapshot_version: str,
    policy_version: str,
) -> str:
    payload: dict[str, Any] = {
        "policy_version": policy_version,
        "snapshot_version": snapshot_version,
        "source_release_id": source_release_id,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")
    return f"uploadauth_{hashlib.sha256(encoded).hexdigest()}"
