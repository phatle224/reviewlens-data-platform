"""Immutable source-object upload with replay, conflict and checksum verification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from pydantic import ValidationError

from reviewlens.ingestion.preflight import UploadPreflightDecision
from reviewlens.ingestion.source import (
    CanonicalSourceManifest,
    DiscoveredFile,
    DiscoveredSnapshot,
    SourceDiscoveryError,
    classify_source_release,
)
from reviewlens.providers.r2 import R2Client, R2ObjectAlreadyExistsError, R2ObjectMetadata


class SourceUploadCode(StrEnum):
    PREFLIGHT_REQUIRED = "SOURCE_UPLOAD_PREFLIGHT_REQUIRED"
    INPUT_MISMATCH = "SOURCE_UPLOAD_INPUT_MISMATCH"
    OBJECT_CONFLICT = "SOURCE_UPLOAD_OBJECT_CONFLICT"
    INTEGRITY_FAILED = "SOURCE_UPLOAD_INTEGRITY_FAILED"
    MANIFEST_CONFLICT = "SOURCE_UPLOAD_MANIFEST_CONFLICT"


class SourceUploadError(RuntimeError):
    """Sanitized upload failure that never exposes local paths or object bodies."""

    def __init__(self, code: SourceUploadCode, *, file_name: str | None = None) -> None:
        self.code = code
        self.file_name = file_name
        context = f":{file_name}" if file_name else ""
        super().__init__(f"{code.value}{context}")


@dataclass(frozen=True, slots=True)
class SourceUploadReport:
    source_release_id: str
    uploaded_objects: int
    replayed_objects: int
    verified_objects: int
    manifest_key: str


def upload_immutable_source_snapshot(
    *,
    client: R2Client,
    snapshot: DiscoveredSnapshot,
    manifest: CanonicalSourceManifest,
    preflight: UploadPreflightDecision,
) -> SourceUploadReport:
    """Upload nine source files and write the manifest last as the commit marker."""

    try:
        authorization_id = preflight.require_approved()
    except RuntimeError:
        raise SourceUploadError(SourceUploadCode.PREFLIGHT_REQUIRED) from None
    if preflight.source_release_id != manifest.source_release_id:
        raise SourceUploadError(SourceUploadCode.INPUT_MISMATCH)
    manifest_files = {item.file_name: item for item in manifest.files}
    snapshot_files = {item.file_name: item for item in snapshot.files}
    if set(manifest_files) != set(snapshot_files):
        raise SourceUploadError(SourceUploadCode.INPUT_MISMATCH)

    uploaded = replayed = 0
    for file_name in sorted(snapshot_files):
        source_file = snapshot_files[file_name]
        canonical_file = manifest_files[file_name]
        if (
            canonical_file.bytes != source_file.bytes
            or canonical_file.sha256 != source_file.sha256
            or canonical_file.dataset_name != source_file.dataset_name
        ):
            raise SourceUploadError(SourceUploadCode.INPUT_MISMATCH, file_name=file_name)
        disposition = _ensure_file(
            client=client,
            source_file=source_file,
            source_release_id=manifest.source_release_id,
            authorization_id=authorization_id,
        )
        if disposition == "uploaded":
            uploaded += 1
        else:
            replayed += 1

    manifest_key = f"manifests/source_release_id={manifest.source_release_id}/manifest.json"
    manifest_disposition = _ensure_manifest(
        client=client,
        key=manifest_key,
        manifest=manifest,
        authorization_id=authorization_id,
    )
    if manifest_disposition == "uploaded":
        uploaded += 1
    else:
        replayed += 1
    return SourceUploadReport(
        source_release_id=manifest.source_release_id,
        uploaded_objects=uploaded,
        replayed_objects=replayed,
        verified_objects=len(snapshot_files) + 1,
        manifest_key=manifest_key,
    )


def _ensure_file(
    *,
    client: R2Client,
    source_file: DiscoveredFile,
    source_release_id: str,
    authorization_id: str,
) -> str:
    key = f"source/olist/{source_release_id}/{source_file.file_name}"
    expected_metadata = {
        "authorization-id": authorization_id,
        "data-class": source_file.data_class,
        "immutable": "true",
        "sha256": source_file.sha256,
        "source-release-id": source_release_id,
    }
    if _exists(client, key, file_name=source_file.file_name):
        _verify_object(
            client=client,
            key=key,
            expected_bytes=source_file.bytes,
            expected_sha256=source_file.sha256,
            expected_metadata=expected_metadata,
            file_name=source_file.file_name,
        )
        return "replayed"
    try:
        client.put_file_create_only(
            key,
            source_file.path,
            content_type="text/csv; charset=utf-8",
            metadata=expected_metadata,
        )
        disposition = "uploaded"
    except R2ObjectAlreadyExistsError:
        disposition = "replayed"
    _verify_object(
        client=client,
        key=key,
        expected_bytes=source_file.bytes,
        expected_sha256=source_file.sha256,
        expected_metadata=expected_metadata,
        file_name=source_file.file_name,
    )
    return disposition


def _ensure_manifest(
    *,
    client: R2Client,
    key: str,
    manifest: CanonicalSourceManifest,
    authorization_id: str,
) -> str:
    body = manifest.to_json().encode("utf-8")
    checksum = hashlib.sha256(body).hexdigest()
    metadata = {
        "authorization-id": authorization_id,
        "data-class": "source-metadata",
        "immutable": "true",
        "sha256": checksum,
        "source-release-id": manifest.source_release_id,
    }
    if _exists(client, key):
        _verify_existing_manifest(
            client=client,
            key=key,
            candidate=manifest,
            authorization_id=authorization_id,
        )
        return "replayed"
    try:
        client.put_bytes_create_only(
            key,
            body,
            content_type="application/json",
            metadata=metadata,
        )
        disposition = "uploaded"
    except R2ObjectAlreadyExistsError:
        disposition = "replayed"
    if disposition == "replayed":
        _verify_existing_manifest(
            client=client,
            key=key,
            candidate=manifest,
            authorization_id=authorization_id,
        )
    else:
        _verify_object(
            client=client,
            key=key,
            expected_bytes=len(body),
            expected_sha256=checksum,
            expected_metadata=metadata,
        )
    return disposition


def _verify_existing_manifest(
    *,
    client: R2Client,
    key: str,
    candidate: CanonicalSourceManifest,
    authorization_id: str,
) -> None:
    try:
        body = client.get_bytes(key)
        existing = CanonicalSourceManifest.model_validate_json(body)
        classify_source_release(existing, candidate)
        metadata = client.head(key)
    except (
        OSError,
        UnicodeDecodeError,
        ValidationError,
        SourceDiscoveryError,
        ClientError,
        KeyError,
    ):
        raise SourceUploadError(SourceUploadCode.MANIFEST_CONFLICT) from None
    checksum = hashlib.sha256(body).hexdigest()
    if (
        metadata.size != len(body)
        or metadata.metadata.get("sha256") != checksum
        or metadata.metadata.get("source-release-id") != candidate.source_release_id
        or metadata.metadata.get("authorization-id") != authorization_id
        or metadata.metadata.get("immutable") != "true"
    ):
        raise SourceUploadError(SourceUploadCode.MANIFEST_CONFLICT)


def _verify_object(
    *,
    client: R2Client,
    key: str,
    expected_bytes: int,
    expected_sha256: str,
    expected_metadata: dict[str, str],
    file_name: str | None = None,
) -> None:
    try:
        head: R2ObjectMetadata = client.head(key)
        observed_sha256, observed_bytes = client.download_sha256(key)
    except (OSError, ClientError, KeyError):
        raise SourceUploadError(SourceUploadCode.INTEGRITY_FAILED, file_name=file_name) from None
    if (
        head.size != expected_bytes
        or observed_bytes != expected_bytes
        or observed_sha256 != expected_sha256
        or any(head.metadata.get(name) != value for name, value in expected_metadata.items())
    ):
        raise SourceUploadError(SourceUploadCode.OBJECT_CONFLICT, file_name=file_name)


def _exists(client: R2Client, key: str, *, file_name: str | None = None) -> bool:
    try:
        return client.exists(key)
    except ClientError:
        raise SourceUploadError(SourceUploadCode.INTEGRITY_FAILED, file_name=file_name) from None
