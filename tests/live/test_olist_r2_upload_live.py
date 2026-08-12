from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx
import pytest

from reviewlens.config import DataMode, load_environment_values, load_settings, project_root
from reviewlens.ingestion.contracts import DataClass, load_olist_contract
from reviewlens.ingestion.preflight import (
    PrivacyPreflightEvidence,
    load_approved_olist_snapshot,
    materialize_approved_completion_manifest,
    run_upload_preflight,
)
from reviewlens.ingestion.source import build_canonical_manifest, discover_source_snapshot
from reviewlens.ingestion.source_upload import upload_immutable_source_snapshot
from reviewlens.ingestion.validation import validate_dataset_file
from reviewlens.providers.r2 import R2Client, R2RuntimePurpose

pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.environ.get("REVIEWLENS_RUN_LIVE_OLIST_R2_UPLOAD") != "1",
    reason="set REVIEWLENS_RUN_LIVE_OLIST_R2_UPLOAD=1 for approved Olist archive upload",
)
def test_approved_olist_snapshot_uploads_immutably_to_private_r2() -> None:
    root = project_root()
    source_directory = root / "archive"
    approved = load_approved_olist_snapshot()
    materialize_approved_completion_manifest(source_directory, approved_snapshot=approved)
    snapshot = discover_source_snapshot(source_directory)
    contract = load_olist_contract()

    reports = [
        validate_dataset_file(
            source.path,
            dataset=contract.by_file_name[source.file_name],
            declared_rows=source.observed_rows,
        )
        for source in snapshot.files
    ]
    assert all(report.valid for report in reports), [
        (report.dataset_name, report.error_counts, report.file_errors)
        for report in reports
        if not report.valid
    ]
    manifest = build_canonical_manifest(
        snapshot,
        source_snapshot_date=approved.source_snapshot_date,
        created_at=datetime.now(UTC),
    )
    settings = load_settings().model_copy(update={"data_mode": DataMode.OLIST})
    evidence = PrivacyPreflightEvidence(
        policy_version="m0-security-privacy-v1",
        raw_data_outside_git=True,
        private_processing_only=True,
        external_ai_transfer_disabled=True,
        public_row_level_evidence_disabled=True,
        restricted_reviews_classified=(
            contract.by_file_name["olist_order_reviews_dataset.csv"].data_class
            is DataClass.RESTRICTED
        ),
        source_privacy_scan_passed=all(report.valid for report in reports),
        non_commercial_confirmed=True,
        share_alike_confirmed=True,
        change_notice_confirmed=True,
        no_endorsement_confirmed=True,
    )
    preflight = run_upload_preflight(
        settings=settings,
        manifest=manifest,
        privacy_evidence=evidence,
        attribution_text=(root / "docs" / "DATA_ATTRIBUTION.md").read_text(encoding="utf-8"),
        approved_snapshot=approved,
    )
    preflight.require_approved()

    credentials = load_environment_values()
    client = R2Client.from_runtime_identity(
        settings.r2,
        settings.identities,
        R2RuntimePurpose.INGESTION,
        credential_values=credentials,
    )
    report = upload_immutable_source_snapshot(
        client=client,
        snapshot=snapshot,
        manifest=manifest,
        preflight=preflight,
    )

    assert report.verified_objects == 10
    assert report.uploaded_objects + report.replayed_objects == 10
    if os.environ.get("REVIEWLENS_EXPECT_R2_REPLAY") == "1":
        assert report.uploaded_objects == 0
        assert report.replayed_objects == 10
    assert client.account_level_bucket_listing_is_denied()
    probe_key = f"source/olist/{manifest.source_release_id}/{snapshot.files[0].file_name}"
    response = httpx.head(
        client.anonymous_object_url(probe_key),
        timeout=10,
        follow_redirects=False,
    )
    assert response.status_code in {400, 401, 403, 404}
