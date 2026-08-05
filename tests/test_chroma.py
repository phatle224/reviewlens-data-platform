from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from reviewlens.config import ChromaConfig, load_settings
from reviewlens.providers.chroma import (
    AUTHORITATIVE_RAG_SOURCE,
    ChromaProviderError,
    ChromaVectorRecord,
    ChromaVectorStore,
    versioned_collection_name,
)
from reviewlens.providers.openrouter import AIDataClass


class FakeCollection:
    def __init__(self) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []
        self.query_result: dict[str, Any] = {"ids": [[]], "distances": [[]], "metadatas": [[]]}
        self.raise_on_upsert = False

    def upsert(self, **kwargs: Any) -> None:
        if self.raise_on_upsert:
            raise RuntimeError("seeded vector secret")
        self.upserts.append(kwargs)

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.queries.append(kwargs)
        return self.query_result


class FakeChromaBackend:
    def __init__(self, collection: FakeCollection | None = None) -> None:
        self.collection = collection or FakeCollection()
        self.collection_calls: list[dict[str, Any]] = []
        self.raise_on_collection = False

    def get_or_create_collection(self, **kwargs: Any) -> FakeCollection:
        if self.raise_on_collection:
            raise RuntimeError("seeded collection secret")
        self.collection_calls.append(kwargs)
        return self.collection


def _config(tmp_path: Path) -> ChromaConfig:
    return load_settings(environ={}, env_file=tmp_path / ".env").chroma


def _record(
    *,
    chunk_id: str = "chunk-001",
    index_version: str = "v1",
    embedding: tuple[float, ...] = (0.1, 0.2),
) -> ChromaVectorRecord:
    return ChromaVectorRecord(
        chunk_id=chunk_id,
        embedding=embedding,
        data_release_id="release-001",
        index_version=index_version,
        content_sha256=hashlib.sha256(b"synthetic serving-safe text").hexdigest(),
        policy_version="synthetic-v1",
        data_class=AIDataClass.SYNTHETIC,
    )


def test_chroma_upsert_is_versioned_and_does_not_store_authoritative_text(tmp_path: Path) -> None:
    backend = FakeChromaBackend()
    store = ChromaVectorStore(_config(tmp_path), backend=backend)

    store.upsert(index_version="v1", records=(_record(),))

    assert backend.collection_calls == [
        {
            "name": "reviewlens_rag_v1",
            "metadata": {
                "index_version": "v1",
                "source_table": AUTHORITATIVE_RAG_SOURCE,
            },
            "embedding_function": None,
        }
    ]
    upsert = backend.collection.upserts[0]
    assert upsert["ids"] == ["chunk-001"]
    assert upsert["embeddings"] == [[0.1, 0.2]]
    assert "documents" not in upsert
    assert upsert["metadatas"][0]["source_table"] == AUTHORITATIVE_RAG_SOURCE
    assert upsert["metadatas"][0]["data_release_id"] == "release-001"


def test_chroma_query_returns_only_ids_and_distances_after_authority_check(
    tmp_path: Path,
) -> None:
    collection = FakeCollection()
    collection.query_result = {
        "ids": [["chunk-001"]],
        "distances": [[0.125]],
        "metadatas": [
            [
                {
                    "source_table": AUTHORITATIVE_RAG_SOURCE,
                    "data_release_id": "release-001",
                    "index_version": "v1",
                }
            ]
        ],
    }
    store = ChromaVectorStore(_config(tmp_path), backend=FakeChromaBackend(collection))

    matches = store.query(
        index_version="v1",
        data_release_id="release-001",
        query_embedding=(0.2, 0.4),
        limit=5,
    )

    assert matches[0].chunk_id == "chunk-001"
    assert matches[0].distance == 0.125
    assert collection.queries[0] == {
        "query_embeddings": [[0.2, 0.4]],
        "n_results": 5,
        "where": {
            "$and": [
                {"data_release_id": "release-001"},
                {"index_version": "v1"},
                {"source_table": AUTHORITATIVE_RAG_SOURCE},
            ]
        },
        "include": ["metadatas", "distances"],
    }


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "source_table": "BRONZE.REVIEW_RAW",
            "data_release_id": "release-001",
            "index_version": "v1",
        },
        {
            "source_table": AUTHORITATIVE_RAG_SOURCE,
            "data_release_id": "other",
            "index_version": "v1",
        },
        {
            "source_table": AUTHORITATIVE_RAG_SOURCE,
            "data_release_id": "release-001",
            "index_version": "v2",
        },
    ],
)
def test_chroma_query_fails_closed_on_non_authoritative_metadata(
    metadata: dict[str, str],
    tmp_path: Path,
) -> None:
    collection = FakeCollection()
    collection.query_result = {
        "ids": [["chunk-secret"]],
        "distances": [[0.1]],
        "metadatas": [[metadata]],
    }
    store = ChromaVectorStore(_config(tmp_path), backend=FakeChromaBackend(collection))

    with pytest.raises(ChromaProviderError, match="authority metadata was invalid"):
        store.query(
            index_version="v1",
            data_release_id="release-001",
            query_embedding=(0.1,),
            limit=1,
        )


def test_chroma_rejects_restricted_records_version_mix_and_dimension_mix(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="synthetic or DLP-approved"):
        ChromaVectorRecord(
            chunk_id="chunk-001",
            embedding=(0.1,),
            data_release_id="release-001",
            index_version="v1",
            content_sha256="0" * 64,
            policy_version="policy-v1",
            data_class=AIDataClass.RESTRICTED,
        )
    store = ChromaVectorStore(_config(tmp_path), backend=FakeChromaBackend())
    with pytest.raises(ValueError, match="target index version"):
        store.upsert(index_version="v1", records=(_record(index_version="v2"),))
    with pytest.raises(ValueError, match="one dimension"):
        store.upsert(
            index_version="v1",
            records=(_record(), _record(chunk_id="chunk-002", embedding=(0.1,))),
        )
    with pytest.raises(ValueError, match="finite"):
        _record(embedding=(float("nan"),))


@pytest.mark.parametrize(
    "prefix,index_version", [("ReviewLens", "v1"), ("reviewlens", "bad/version"), ("a..b", "v1")]
)
def test_chroma_collection_name_rejects_unsafe_parts(prefix: str, index_version: str) -> None:
    with pytest.raises(ValueError, match="unsafe characters"):
        versioned_collection_name(prefix, index_version)


def test_chroma_provider_errors_are_sanitized(tmp_path: Path) -> None:
    backend = FakeChromaBackend()
    backend.collection.raise_on_upsert = True
    store = ChromaVectorStore(_config(tmp_path), backend=backend)
    with pytest.raises(ChromaProviderError) as captured:
        store.upsert(index_version="v1", records=(_record(chunk_id="seeded-chunk-secret"),))
    assert str(captured.value) == "Chroma upsert failed"
    assert "seeded" not in str(captured.value)

    backend.raise_on_collection = True
    with pytest.raises(ChromaProviderError) as captured:
        store.query(
            index_version="v1",
            data_release_id="seeded-release-secret",
            query_embedding=(0.1,),
            limit=1,
        )
    assert str(captured.value) == "Chroma collection access failed"
    assert "seeded" not in str(captured.value)


def test_chroma_from_config_uses_loopback_and_token_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []
    backend = FakeChromaBackend()

    class FakeModule:
        def HttpClient(self, **kwargs: Any) -> FakeChromaBackend:
            calls.append(kwargs)
            return backend

    config = _config(tmp_path).model_copy(update={"auth_token": SecretStr("seeded-token")})
    monkeypatch.setattr(
        "reviewlens.providers.chroma.importlib.import_module", lambda _name: FakeModule()
    )

    store = ChromaVectorStore.from_config(config)
    store.upsert(index_version="v1", records=(_record(),))
    assert calls == [
        {
            "host": "127.0.0.1",
            "port": 8000,
            "ssl": False,
            "headers": {"x-chroma-token": "seeded-token"},
        }
    ]

    with pytest.raises(ValueError, match="CHROMA_AUTH_TOKEN"):
        ChromaVectorStore.from_config(_config(tmp_path))
    remote = config.model_copy(update={"host": "example.com"})
    with pytest.raises(ValueError, match="loopback"):
        ChromaVectorStore.from_config(remote)
