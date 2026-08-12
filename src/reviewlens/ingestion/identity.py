"""Deterministic, namespaced identifiers for Olist ingestion lineage."""

from __future__ import annotations

import hashlib
import json
import re

from reviewlens.ingestion.contracts import load_olist_contract

IDENTITY_VERSION = "reviewlens-ingestion-id-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_RELEASE_RE = re.compile(r"^olist_[0-9a-f]{64}$")
_CONTRACT_VERSION_RE = re.compile(r"^olist-source-v[1-9][0-9]*$")
_ID_RE_BY_KIND = {
    "source_object": re.compile(r"^srcobj_[0-9a-f]{64}$"),
    "ingestion_batch": re.compile(r"^batch_[0-9a-f]{64}$"),
    "dataset_run": re.compile(r"^dsrun_[0-9a-f]{64}$"),
    "attempt": re.compile(r"^attempt_[0-9a-f]{64}$"),
    "record": re.compile(r"^record_[0-9a-f]{64}$"),
}


class IngestionIdentityError(ValueError):
    """Sanitized identity-contract failure that never echoes caller input."""

    code = "INGESTION_IDENTITY_INVALID"

    def __init__(self) -> None:
        super().__init__(self.code)


def source_object_id(
    *,
    source_release_id: str,
    file_name: str,
    source_object_sha256: str,
) -> str:
    """Identify one immutable source object within a complete source release."""

    contract = load_olist_contract()
    _require(_SOURCE_RELEASE_RE.fullmatch(source_release_id) is not None)
    _require(file_name in contract.required_file_names)
    _require(_SHA256_RE.fullmatch(source_object_sha256) is not None)
    return _digest_id(
        "srcobj",
        "source_object",
        {
            "file_name": file_name,
            "source_object_sha256": source_object_sha256,
            "source_release_id": source_release_id,
        },
    )


def ingestion_batch_id(*, source_release_id: str) -> str:
    """Identify the idempotent ingestion batch for one content release."""

    _require(_SOURCE_RELEASE_RE.fullmatch(source_release_id) is not None)
    return _digest_id(
        "batch",
        "ingestion_batch",
        {"source_release_id": source_release_id},
    )


def dataset_run_id(
    *,
    ingestion_batch_id: str,
    source_object_id: str,
    dataset_name: str,
    contract_version: str,
) -> str:
    """Identify one dataset transformation contract inside an ingestion batch."""

    contract = load_olist_contract()
    _require(_ID_RE_BY_KIND["ingestion_batch"].fullmatch(ingestion_batch_id) is not None)
    _require(_ID_RE_BY_KIND["source_object"].fullmatch(source_object_id) is not None)
    _require(dataset_name in {dataset.dataset_name for dataset in contract.datasets})
    _require(_CONTRACT_VERSION_RE.fullmatch(contract_version) is not None)
    return _digest_id(
        "dsrun",
        "dataset_run",
        {
            "contract_version": contract_version,
            "dataset_name": dataset_name,
            "ingestion_batch_id": ingestion_batch_id,
            "source_object_id": source_object_id,
        },
    )


def attempt_id(*, dataset_run_id: str, attempt_number: int) -> str:
    """Identify a retry attempt; a new positive ordinal creates a new ID."""

    _require(_ID_RE_BY_KIND["dataset_run"].fullmatch(dataset_run_id) is not None)
    _require(
        isinstance(attempt_number, int)
        and not isinstance(attempt_number, bool)
        and 1 <= attempt_number <= 2_147_483_647
    )
    return _digest_id(
        "attempt",
        "attempt",
        {"attempt_number": attempt_number, "dataset_run_id": dataset_run_id},
    )


def record_id(
    *,
    source_object_id: str,
    source_row_number: int,
    byte_start: int,
    byte_end: int,
) -> str:
    """Identify a physical logical CSV record independently of runtime metadata."""

    _require(_ID_RE_BY_KIND["source_object"].fullmatch(source_object_id) is not None)
    _require(
        isinstance(source_row_number, int)
        and not isinstance(source_row_number, bool)
        and source_row_number >= 2
    )
    _require(isinstance(byte_start, int) and not isinstance(byte_start, bool) and byte_start >= 0)
    _require(isinstance(byte_end, int) and not isinstance(byte_end, bool) and byte_end > byte_start)
    return _digest_id(
        "record",
        "record",
        {
            "byte_end": byte_end,
            "byte_start": byte_start,
            "source_object_id": source_object_id,
            "source_row_number": source_row_number,
        },
    )


def _digest_id(prefix: str, kind: str, fields: dict[str, str | int]) -> str:
    payload = json.dumps(
        {"fields": fields, "kind": kind, "version": IDENTITY_VERSION},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()}"


def _require(condition: bool) -> None:
    if not condition:
        raise IngestionIdentityError()
