"""Versioned Chroma vector adapter with Snowflake-authority enforcement."""

from __future__ import annotations

import importlib
import ipaddress
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from reviewlens.config import ChromaConfig
from reviewlens.providers.openrouter import AIDataClass

AUTHORITATIVE_RAG_SOURCE = "AI.RAG_DOCUMENT"


class _ChromaCollection(Protocol):
    def upsert(self, **kwargs: Any) -> None: ...

    def query(self, **kwargs: Any) -> Mapping[str, Any]: ...


class _ChromaBackend(Protocol):
    def get_or_create_collection(self, **kwargs: Any) -> _ChromaCollection: ...


class _ChromaModule(Protocol):
    def HttpClient(self, **kwargs: Any) -> _ChromaBackend: ...


class ChromaProviderError(RuntimeError):
    """Sanitized failure that excludes documents, vectors and credentials."""


@dataclass(frozen=True, slots=True)
class ChromaVectorRecord:
    chunk_id: str
    embedding: tuple[float, ...]
    data_release_id: str
    index_version: str
    content_sha256: str
    policy_version: str
    data_class: AIDataClass

    def __post_init__(self) -> None:
        if self.data_class not in {AIDataClass.SYNTHETIC, AIDataClass.DLP_APPROVED}:
            raise ValueError("only synthetic or DLP-approved records may enter Chroma")
        for label, value in (
            ("chunk_id", self.chunk_id),
            ("data_release_id", self.data_release_id),
            ("index_version", self.index_version),
            ("policy_version", self.policy_version),
        ):
            if not value or len(value) > 128:
                raise ValueError(f"Chroma {label} must contain 1 to 128 characters")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", self.chunk_id):
            raise ValueError("Chroma chunk_id contains unsafe characters")
        if not self.embedding:
            raise ValueError("Chroma embedding cannot be empty")
        if not all(math.isfinite(value) for value in self.embedding):
            raise ValueError("Chroma embedding values must be finite")
        if not re.fullmatch(r"[0-9a-f]{64}", self.content_sha256):
            raise ValueError("Chroma content hash must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class ChromaMatch:
    chunk_id: str
    distance: float


_COLLECTION_PART = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")


def versioned_collection_name(prefix: str, index_version: str) -> str:
    """Build a collision-resistant collection name without silent normalization."""

    name = f"{prefix}_rag_{index_version}"
    if not 3 <= len(name) <= 128 or not _COLLECTION_PART.fullmatch(name) or ".." in name:
        raise ValueError("Chroma collection prefix/version contains unsafe characters")
    try:
        ipaddress.ip_address(name)
    except ValueError:
        return name
    raise ValueError("Chroma collection name cannot be an IP address")


class ChromaVectorStore:
    """Stores only embeddings and reference metadata; Snowflake remains authoritative."""

    def __init__(self, config: ChromaConfig, *, backend: _ChromaBackend) -> None:
        self._config = config
        self._backend = backend

    @classmethod
    def from_config(cls, config: ChromaConfig) -> ChromaVectorStore:
        if config.auth_token is None:
            raise ValueError("Chroma live access requires CHROMA_AUTH_TOKEN")
        if config.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("local Chroma must use a loopback host")
        module = cast(_ChromaModule, importlib.import_module("chromadb"))
        try:
            backend = module.HttpClient(
                host=config.host,
                port=config.port,
                ssl=False,
                headers={"x-chroma-token": config.auth_token.get_secret_value()},
            )
        except Exception:
            raise ChromaProviderError("Chroma connection failed") from None
        return cls(config, backend=backend)

    def upsert(self, *, index_version: str, records: Sequence[ChromaVectorRecord]) -> None:
        if not records:
            raise ValueError("Chroma upsert requires at least one record")
        if any(record.index_version != index_version for record in records):
            raise ValueError("Chroma records must match the target index version")
        dimensions = {len(record.embedding) for record in records}
        if len(dimensions) != 1:
            raise ValueError("Chroma batch embeddings must have one dimension")
        collection = self._collection(index_version)
        try:
            collection.upsert(
                ids=[record.chunk_id for record in records],
                embeddings=[list(record.embedding) for record in records],
                metadatas=[self._metadata(record) for record in records],
            )
        except Exception:
            raise ChromaProviderError("Chroma upsert failed") from None

    def query(
        self,
        *,
        index_version: str,
        data_release_id: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> tuple[ChromaMatch, ...]:
        if not query_embedding:
            raise ValueError("Chroma query embedding cannot be empty")
        if not 1 <= limit <= 100:
            raise ValueError("Chroma query limit must be between 1 and 100")
        collection = self._collection(index_version)
        where = {
            "$and": [
                {"data_release_id": data_release_id},
                {"index_version": index_version},
                {"source_table": AUTHORITATIVE_RAG_SOURCE},
            ]
        }
        try:
            result = collection.query(
                query_embeddings=[list(query_embedding)],
                n_results=limit,
                where=where,
                include=["metadatas", "distances"],
            )
            return self._parse_matches(
                result,
                index_version=index_version,
                data_release_id=data_release_id,
            )
        except ChromaProviderError:
            raise
        except Exception:
            raise ChromaProviderError("Chroma query failed") from None

    def _collection(self, index_version: str) -> _ChromaCollection:
        name = versioned_collection_name(self._config.collection_prefix, index_version)
        try:
            return self._backend.get_or_create_collection(
                name=name,
                metadata={
                    "index_version": index_version,
                    "source_table": AUTHORITATIVE_RAG_SOURCE,
                },
                embedding_function=None,
            )
        except Exception:
            raise ChromaProviderError("Chroma collection access failed") from None

    @staticmethod
    def _metadata(record: ChromaVectorRecord) -> dict[str, str]:
        return {
            "source_table": AUTHORITATIVE_RAG_SOURCE,
            "data_release_id": record.data_release_id,
            "index_version": record.index_version,
            "content_sha256": record.content_sha256,
            "policy_version": record.policy_version,
            "data_class": record.data_class.value,
        }

    @staticmethod
    def _parse_matches(
        result: Mapping[str, Any],
        *,
        index_version: str,
        data_release_id: str,
    ) -> tuple[ChromaMatch, ...]:
        ids_batches = result.get("ids")
        distance_batches = result.get("distances")
        metadata_batches = result.get("metadatas")
        if not (
            isinstance(ids_batches, list)
            and len(ids_batches) == 1
            and isinstance(distance_batches, list)
            and len(distance_batches) == 1
            and isinstance(metadata_batches, list)
            and len(metadata_batches) == 1
        ):
            raise ChromaProviderError("Chroma query response was invalid")
        ids = ids_batches[0]
        distances = distance_batches[0]
        metadatas = metadata_batches[0]
        if not (len(ids) == len(distances) == len(metadatas)):
            raise ChromaProviderError("Chroma query response was invalid")
        matches: list[ChromaMatch] = []
        for chunk_id, distance, metadata in zip(ids, distances, metadatas, strict=True):
            if not isinstance(metadata, Mapping) or (
                metadata.get("source_table") != AUTHORITATIVE_RAG_SOURCE
                or metadata.get("index_version") != index_version
                or metadata.get("data_release_id") != data_release_id
            ):
                raise ChromaProviderError("Chroma query authority metadata was invalid")
            matches.append(ChromaMatch(str(chunk_id), float(distance)))
        return tuple(matches)
