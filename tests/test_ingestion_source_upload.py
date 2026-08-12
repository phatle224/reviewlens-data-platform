from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from reviewlens.ingestion.preflight import UploadPreflightDecision
from reviewlens.ingestion.source import build_canonical_manifest, discover_source_snapshot
from reviewlens.ingestion.source_upload import (
    SourceUploadCode,
    SourceUploadError,
    upload_immutable_source_snapshot,
)
from reviewlens.providers.r2 import R2Client
from reviewlens.synthetic.generator import generate_fixture


class ImmutableFakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs["Key"])
        if kwargs.get("IfNoneMatch") == "*" and key in self.objects:
            raise _client_error("PreconditionFailed", "PutObject", status=412)
        source = kwargs["Body"]
        body = source.read() if hasattr(source, "read") else bytes(source)
        self.objects[key] = (body, dict(kwargs.get("Metadata", {})))
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs["Key"])
        if key not in self.objects:
            raise _client_error("404", "HeadObject", status=404)
        body, metadata = self.objects[key]
        return {"ContentLength": len(body), "ETag": '"synthetic"', "Metadata": metadata}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        body, _ = self.objects[str(kwargs["Key"])]
        return {"Body": BytesIO(body)}

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]:
        prefix = str(kwargs["Prefix"])
        return {"Contents": [{"Key": key} for key in self.objects if key.startswith(prefix)]}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.objects.pop(str(kwargs["Key"]), None)
        return {}

    def list_buckets(self, **kwargs: Any) -> dict[str, Any]:
        raise _client_error("AccessDenied", "ListBuckets", status=403)


def _client_error(code: str, operation: str, *, status: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "synthetic"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        operation,
    )


def _candidate(root: Path) -> tuple[Any, Any, UploadPreflightDecision]:
    generate_fixture(root)
    snapshot = discover_source_snapshot(root)
    manifest = build_canonical_manifest(
        snapshot,
        source_snapshot_date=date(2026, 8, 5),
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
    )
    decision = UploadPreflightDecision(
        approved=True,
        source_release_id=manifest.source_release_id,
        approved_snapshot_version="olist-approved-snapshot-v1",
        passed_checks=("synthetic-test-authority",),
        denial_codes=(),
        authorization_id=f"uploadauth_{'a' * 64}",
    )
    return snapshot, manifest, decision


def _client(fake: ImmutableFakeS3) -> R2Client:
    return R2Client(
        bucket="reviewlens-data-dev",
        endpoint="https://synthetic.r2.cloudflarestorage.com",
        client=fake,
    )


def test_source_upload_writes_nine_files_then_commit_manifest_and_replays(tmp_path: Path) -> None:
    snapshot, manifest, decision = _candidate(tmp_path)
    fake = ImmutableFakeS3()
    client = _client(fake)

    first = upload_immutable_source_snapshot(
        client=client,
        snapshot=snapshot,
        manifest=manifest,
        preflight=decision,
    )
    replay_manifest = manifest.model_copy(
        update={"created_at": manifest.created_at + timedelta(hours=1)}
    )
    replay = upload_immutable_source_snapshot(
        client=client,
        snapshot=snapshot,
        manifest=replay_manifest,
        preflight=decision,
    )

    assert first.uploaded_objects == 10
    assert first.replayed_objects == 0
    assert first.verified_objects == 10
    assert replay.uploaded_objects == 0
    assert replay.replayed_objects == 10
    assert len(fake.objects) == 10
    assert first.manifest_key in fake.objects
    assert list(fake.objects)[-1] == first.manifest_key
    for source_file in snapshot.files:
        key = f"source/olist/{manifest.source_release_id}/{source_file.file_name}"
        assert fake.objects[key][0] == source_file.path.read_bytes()


def test_partial_upload_resumes_without_rewriting_existing_objects(tmp_path: Path) -> None:
    snapshot, manifest, decision = _candidate(tmp_path)
    fake = ImmutableFakeS3()
    client = _client(fake)
    upload_immutable_source_snapshot(
        client=client,
        snapshot=snapshot,
        manifest=manifest,
        preflight=decision,
    )
    missing_key = f"source/olist/{manifest.source_release_id}/{snapshot.files[0].file_name}"
    original_existing = dict(fake.objects)
    fake.objects.pop(missing_key)

    report = upload_immutable_source_snapshot(
        client=client,
        snapshot=snapshot,
        manifest=manifest,
        preflight=decision,
    )

    assert report.uploaded_objects == 1
    assert report.replayed_objects == 9
    assert fake.objects[missing_key] == original_existing[missing_key]
    for key, value in original_existing.items():
        if key != missing_key:
            assert fake.objects[key] == value


def test_existing_different_object_is_conflict_and_never_overwritten(tmp_path: Path) -> None:
    snapshot, manifest, decision = _candidate(tmp_path)
    fake = ImmutableFakeS3()
    client = _client(fake)
    source_file = snapshot.files[0]
    key = f"source/olist/{manifest.source_release_id}/{source_file.file_name}"
    seeded = (b"seeded-private-row-canary", {"sha256": "0" * 64})
    fake.objects[key] = seeded

    with pytest.raises(SourceUploadError) as captured:
        upload_immutable_source_snapshot(
            client=client,
            snapshot=snapshot,
            manifest=manifest,
            preflight=decision,
        )

    assert captured.value.code is SourceUploadCode.OBJECT_CONFLICT
    assert fake.objects[key] == seeded
    assert "seeded-private-row-canary" not in str(captured.value)
    assert str(tmp_path) not in str(captured.value)


def test_denied_or_mismatched_preflight_performs_no_write(tmp_path: Path) -> None:
    snapshot, manifest, decision = _candidate(tmp_path)
    fake = ImmutableFakeS3()
    denied = decision.model_copy(update={"approved": False, "authorization_id": None})

    with pytest.raises(SourceUploadError) as denied_error:
        upload_immutable_source_snapshot(
            client=_client(fake),
            snapshot=snapshot,
            manifest=manifest,
            preflight=denied,
        )
    with pytest.raises(SourceUploadError) as mismatch_error:
        upload_immutable_source_snapshot(
            client=_client(fake),
            snapshot=snapshot,
            manifest=manifest,
            preflight=decision.model_copy(update={"source_release_id": f"olist_{'0' * 64}"}),
        )

    assert denied_error.value.code is SourceUploadCode.PREFLIGHT_REQUIRED
    assert mismatch_error.value.code is SourceUploadCode.INPUT_MISMATCH
    assert not fake.objects


def test_manifest_body_or_metadata_drift_is_conflict(tmp_path: Path) -> None:
    snapshot, manifest, decision = _candidate(tmp_path)
    fake = ImmutableFakeS3()
    client = _client(fake)
    report = upload_immutable_source_snapshot(
        client=client,
        snapshot=snapshot,
        manifest=manifest,
        preflight=decision,
    )
    body, metadata = fake.objects[report.manifest_key]
    fake.objects[report.manifest_key] = (body, {**metadata, "sha256": "0" * 64})

    with pytest.raises(SourceUploadError) as captured:
        upload_immutable_source_snapshot(
            client=client,
            snapshot=snapshot,
            manifest=manifest,
            preflight=decision,
        )

    assert captured.value.code is SourceUploadCode.MANIFEST_CONFLICT
    assert hashlib.sha256(fake.objects[report.manifest_key][0]).hexdigest() != "0" * 64
