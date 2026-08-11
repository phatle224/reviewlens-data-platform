"""Fail-closed local discovery and canonical Olist source-release manifests."""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from reviewlens.ingestion.contracts import SourceContract, load_olist_contract

COMPLETION_MANIFEST_NAME = "manifest.json"
MAX_COMPLETION_MANIFEST_BYTES = 1_048_576
MAX_HEADER_BYTES = 65_536
HASH_CHUNK_BYTES = 1_048_576
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class SourceDiscoveryCode(StrEnum):
    SOURCE_DIRECTORY_MISSING = "SOURCE_DIRECTORY_MISSING"
    SOURCE_DIRECTORY_INVALID = "SOURCE_DIRECTORY_INVALID"
    UNSAFE_SOURCE_ENTRY = "UNSAFE_SOURCE_ENTRY"
    COMPLETION_MANIFEST_MISSING = "COMPLETION_MANIFEST_MISSING"
    COMPLETION_MANIFEST_INVALID = "COMPLETION_MANIFEST_INVALID"
    MISSING_REQUIRED_FILE = "MISSING_REQUIRED_FILE"
    EXTRA_SOURCE_ENTRY = "EXTRA_SOURCE_ENTRY"
    DUPLICATE_MANIFEST_FILE = "DUPLICATE_MANIFEST_FILE"
    MANIFEST_FILE_SET_MISMATCH = "MANIFEST_FILE_SET_MISMATCH"
    FILE_SIZE_MISMATCH = "FILE_SIZE_MISMATCH"
    FILE_CHECKSUM_MISMATCH = "FILE_CHECKSUM_MISMATCH"
    HEADER_INVALID = "HEADER_INVALID"
    HEADER_MISMATCH = "HEADER_MISMATCH"
    SOURCE_RELEASE_CONFLICT = "SOURCE_RELEASE_CONFLICT"


class SourceDiscoveryError(RuntimeError):
    """Stable, row-safe discovery failure."""

    def __init__(self, code: SourceDiscoveryCode, *, file_name: str | None = None) -> None:
        self.code = code
        self.file_name = file_name
        context = f":{file_name}" if file_name else ""
        super().__init__(f"{code.value}{context}")


class CompletionFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str = Field(pattern=r"^[a-z0-9_]+\.csv$")
    rows: int = Field(ge=0)
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=_SHA256_PATTERN)


class CompletionManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    manifest_version: str
    contract_version: str
    data_class: str
    source: str
    source_contract: str
    seed: int | None = None
    files: tuple[CompletionFile, ...]

    @model_validator(mode="after")
    def validate_unique_files(self) -> CompletionManifest:
        names = [item.filename for item in self.files]
        if len(names) != len(set(names)):
            raise ValueError("completion manifest filenames must be unique")
        return self


class DiscoveredFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_name: str
    file_name: str
    path: Path = Field(exclude=True, repr=False)
    required: bool
    bytes: int
    sha256: str = Field(pattern=_SHA256_PATTERN)
    expected_header: tuple[str, ...]
    observed_rows: int = Field(ge=0)
    data_class: str
    license_id: str


class DiscoveredSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    root: Path = Field(exclude=True, repr=False)
    contract_version: str
    manifest_version: str
    source_name: str
    files: tuple[DiscoveredFile, ...]


class CanonicalManifestFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    file_name: str
    dataset_name: str
    required: bool
    bytes: int
    sha256: str = Field(pattern=_SHA256_PATTERN)
    expected_header: tuple[str, ...]
    observed_rows: int = Field(ge=0)
    data_class: str
    license_id: str


class CanonicalSourceManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_name: str
    source_snapshot_date: date
    source_release_id: str = Field(pattern=r"^olist_[0-9a-f]{64}$")
    contract_version: str
    manifest_version: str
    created_at: datetime
    files: tuple[CanonicalManifestFile, ...]

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    def to_json(self) -> str:
        return (
            json.dumps(
                self.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )


class SourceReleaseDisposition(StrEnum):
    REPLAY = "REPLAY"
    NEW_CANDIDATE = "NEW_CANDIDATE"


def discover_source_snapshot(
    source_directory: Path,
    *,
    contract: SourceContract | None = None,
) -> DiscoveredSnapshot:
    """Validate an exact local snapshot without returning row content or provider data."""

    source_contract = contract or load_olist_contract()
    if not source_directory.exists():
        raise SourceDiscoveryError(SourceDiscoveryCode.SOURCE_DIRECTORY_MISSING)
    if not source_directory.is_dir() or source_directory.is_symlink():
        raise SourceDiscoveryError(SourceDiscoveryCode.SOURCE_DIRECTORY_INVALID)

    try:
        entries = tuple(source_directory.iterdir())
    except OSError:
        raise SourceDiscoveryError(SourceDiscoveryCode.SOURCE_DIRECTORY_INVALID) from None
    if any(entry.is_symlink() for entry in entries):
        raise SourceDiscoveryError(SourceDiscoveryCode.UNSAFE_SOURCE_ENTRY)

    entry_names = {entry.name for entry in entries}
    expected_file_names = set(source_contract.required_file_names)
    if COMPLETION_MANIFEST_NAME not in entry_names:
        raise SourceDiscoveryError(SourceDiscoveryCode.COMPLETION_MANIFEST_MISSING)
    missing = expected_file_names - entry_names
    if missing:
        raise SourceDiscoveryError(
            SourceDiscoveryCode.MISSING_REQUIRED_FILE,
            file_name=sorted(missing)[0],
        )
    allowed_entries = expected_file_names | {COMPLETION_MANIFEST_NAME}
    if entry_names != allowed_entries:
        raise SourceDiscoveryError(SourceDiscoveryCode.EXTRA_SOURCE_ENTRY)

    completion = _read_completion_manifest(
        source_directory / COMPLETION_MANIFEST_NAME,
        contract=source_contract,
    )
    completion_by_name = {item.filename: item for item in completion.files}
    if set(completion_by_name) != expected_file_names:
        raise SourceDiscoveryError(SourceDiscoveryCode.MANIFEST_FILE_SET_MISMATCH)

    discovered: list[DiscoveredFile] = []
    for file_name in source_contract.required_file_names:
        dataset = source_contract.by_file_name[file_name]
        declared = completion_by_name[file_name]
        path = source_directory / file_name
        if not path.is_file() or path.is_symlink():
            raise SourceDiscoveryError(
                SourceDiscoveryCode.UNSAFE_SOURCE_ENTRY,
                file_name=file_name,
            )
        observed_bytes = path.stat().st_size
        if observed_bytes != declared.bytes:
            raise SourceDiscoveryError(
                SourceDiscoveryCode.FILE_SIZE_MISMATCH,
                file_name=file_name,
            )
        observed_sha256 = _sha256_file(path)
        if not hmac.compare_digest(observed_sha256, declared.sha256):
            raise SourceDiscoveryError(
                SourceDiscoveryCode.FILE_CHECKSUM_MISMATCH,
                file_name=file_name,
            )
        observed_header = _read_header(path, file_name=file_name)
        if observed_header != dataset.expected_header:
            raise SourceDiscoveryError(
                SourceDiscoveryCode.HEADER_MISMATCH,
                file_name=file_name,
            )
        discovered.append(
            DiscoveredFile(
                dataset_name=dataset.dataset_name,
                file_name=file_name,
                path=path.resolve(),
                required=dataset.required,
                bytes=observed_bytes,
                sha256=observed_sha256,
                expected_header=dataset.expected_header,
                observed_rows=declared.rows,
                data_class=dataset.data_class.value,
                license_id=source_contract.license_id,
            )
        )

    return DiscoveredSnapshot(
        root=source_directory.resolve(),
        contract_version=source_contract.contract_version,
        manifest_version=source_contract.manifest_version,
        source_name=source_contract.source_name,
        files=tuple(discovered),
    )


def build_canonical_manifest(
    snapshot: DiscoveredSnapshot,
    *,
    source_snapshot_date: date,
    created_at: datetime,
) -> CanonicalSourceManifest:
    """Build a path-free manifest whose release ID hashes content identity only."""

    identity_files = [
        {"file_name": item.file_name, "bytes": item.bytes, "sha256": item.sha256}
        for item in sorted(snapshot.files, key=lambda value: value.file_name)
    ]
    identity_payload = json.dumps(
        identity_files,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    source_release_id = f"olist_{hashlib.sha256(identity_payload).hexdigest()}"
    canonical_files = tuple(
        CanonicalManifestFile(
            file_name=item.file_name,
            dataset_name=item.dataset_name,
            required=item.required,
            bytes=item.bytes,
            sha256=item.sha256,
            expected_header=item.expected_header,
            observed_rows=item.observed_rows,
            data_class=item.data_class,
            license_id=item.license_id,
        )
        for item in sorted(snapshot.files, key=lambda value: value.file_name)
    )
    return CanonicalSourceManifest(
        source_name=snapshot.source_name,
        source_snapshot_date=source_snapshot_date,
        source_release_id=source_release_id,
        contract_version=snapshot.contract_version,
        manifest_version=snapshot.manifest_version,
        created_at=created_at,
        files=canonical_files,
    )


def classify_source_release(
    existing: CanonicalSourceManifest,
    candidate: CanonicalSourceManifest,
) -> SourceReleaseDisposition:
    """Classify replay/new content and fail closed on same-ID stable metadata drift."""

    if existing.source_release_id != candidate.source_release_id:
        return SourceReleaseDisposition.NEW_CANDIDATE
    ignored = {"source_snapshot_date", "created_at"}
    existing_stable = existing.model_dump(mode="json", exclude=ignored)
    candidate_stable = candidate.model_dump(mode="json", exclude=ignored)
    if existing_stable != candidate_stable:
        raise SourceDiscoveryError(SourceDiscoveryCode.SOURCE_RELEASE_CONFLICT)
    return SourceReleaseDisposition.REPLAY


def _read_completion_manifest(path: Path, *, contract: SourceContract) -> CompletionManifest:
    try:
        if path.stat().st_size > MAX_COMPLETION_MANIFEST_BYTES:
            raise SourceDiscoveryError(SourceDiscoveryCode.COMPLETION_MANIFEST_INVALID)
        payload = json.loads(path.read_bytes())
        if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
            raise SourceDiscoveryError(SourceDiscoveryCode.COMPLETION_MANIFEST_INVALID)
        names = [item.get("filename") for item in payload["files"] if isinstance(item, dict)]
        if len(names) != len(payload["files"]):
            raise SourceDiscoveryError(SourceDiscoveryCode.COMPLETION_MANIFEST_INVALID)
        if len(names) != len(set(names)):
            raise SourceDiscoveryError(SourceDiscoveryCode.DUPLICATE_MANIFEST_FILE)
        completion = CompletionManifest.model_validate(payload)
    except SourceDiscoveryError:
        raise
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValidationError, ValueError):
        raise SourceDiscoveryError(SourceDiscoveryCode.COMPLETION_MANIFEST_INVALID) from None
    if (
        completion.contract_version != contract.contract_version
        or completion.manifest_version != contract.manifest_version
        or completion.source_contract != contract.source_contract
    ):
        raise SourceDiscoveryError(SourceDiscoveryCode.COMPLETION_MANIFEST_INVALID)
    return completion


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
    except OSError:
        raise SourceDiscoveryError(SourceDiscoveryCode.SOURCE_DIRECTORY_INVALID) from None
    return digest.hexdigest()


def _read_header(path: Path, *, file_name: str) -> tuple[str, ...]:
    try:
        with path.open("rb") as handle:
            prefix = handle.read(MAX_HEADER_BYTES + 1)
        newline_index = prefix.find(b"\n")
        if newline_index < 0 or newline_index > MAX_HEADER_BYTES:
            raise SourceDiscoveryError(SourceDiscoveryCode.HEADER_INVALID, file_name=file_name)
        first_line = prefix[:newline_index].rstrip(b"\r")
        decoded = first_line.decode("utf-8-sig")
        parsed = next(csv.reader([decoded]))
    except SourceDiscoveryError:
        raise
    except (OSError, UnicodeDecodeError, csv.Error, IndexError, StopIteration):
        raise SourceDiscoveryError(
            SourceDiscoveryCode.HEADER_INVALID, file_name=file_name
        ) from None
    return tuple(parsed)
