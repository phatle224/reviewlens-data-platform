from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from reviewlens.config import load_settings
from reviewlens.providers.r2 import (
    R2AccessPolicyError,
    R2Client,
    R2RuntimePurpose,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.objects[str(kwargs["Key"])] = (bytes(kwargs["Body"]), dict(kwargs["Metadata"]))
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        key = str(kwargs["Key"])
        if key not in self.objects:
            raise _client_error("404", "HeadObject")
        body, metadata = self.objects[key]
        return {
            "ContentLength": len(body),
            "ETag": f'"{hashlib.md5(body, usedforsecurity=False).hexdigest()}"',
            "Metadata": metadata,
        }

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
        raise _client_error("AccessDenied", "ListBuckets")


def _client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "synthetic error"}}, operation)


def test_r2_adapter_round_trip_and_scope_denial() -> None:
    fake = FakeS3Client()
    client = R2Client(
        bucket="reviewlens-data-dev",
        endpoint="https://synthetic.r2.cloudflarestorage.com",
        client=fake,
    )
    key = "manifests/_smoke/synthetic.json"
    body = b'{"data_class":"synthetic"}\n'

    metadata = client.put_bytes(
        key,
        body,
        content_type="application/json",
        metadata={"data-class": "synthetic"},
    )

    assert metadata.size == len(body)
    assert metadata.metadata == {"data-class": "synthetic"}
    assert client.get_bytes(key) == body
    assert client.list_keys("manifests/_smoke/") == (key,)
    assert client.exists(key)
    assert client.account_level_bucket_listing_is_denied()

    client.delete(key)
    assert not client.exists(key)


def test_r2_anonymous_url_uses_path_style_and_escaping() -> None:
    client = R2Client(
        bucket="reviewlens-data-dev",
        endpoint="https://synthetic.r2.cloudflarestorage.com/",
        client=FakeS3Client(),
    )
    assert client.anonymous_object_url("manifests/_smoke/file name.json") == (
        "https://synthetic.r2.cloudflarestorage.com/"
        "reviewlens-data-dev/manifests/_smoke/file%20name.json"
    )


def test_r2_lifecycle_contract_is_smoke_only() -> None:
    payload = json.loads(Path("infra/cloudflare_r2/lifecycle.json").read_text(encoding="utf-8"))
    assert payload == {
        "Rules": [
            {
                "ID": "expire-reviewlens-smoke-objects",
                "Status": "Enabled",
                "Filter": {"Prefix": "manifests/_smoke/"},
                "Expiration": {"Days": 1},
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
            }
        ]
    }


def test_r2_runtime_identities_use_dedicated_credentials_and_stage_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_settings(environ={}, env_file=tmp_path / ".env")
    credentials = {
        "R2_ACCOUNT_ID": "seeded-account",
        "R2_INGEST_ACCESS_KEY_ID": "seeded-ingest-access",
        "R2_INGEST_SECRET_ACCESS_KEY": "seeded-ingest-secret",
        "R2_STAGE_ACCESS_KEY_ID": "seeded-stage-access",
        "R2_STAGE_SECRET_ACCESS_KEY": "seeded-stage-secret",
    }
    calls: list[dict[str, Any]] = []
    fakes: list[FakeS3Client] = []

    def fake_boto3_client(_service: str, **kwargs: Any) -> FakeS3Client:
        calls.append(kwargs)
        fake = FakeS3Client()
        fakes.append(fake)
        return fake

    monkeypatch.setattr("reviewlens.providers.r2.boto3.client", fake_boto3_client)
    ingestion = R2Client.from_runtime_identity(
        settings.r2,
        settings.identities,
        R2RuntimePurpose.INGESTION,
        credential_values=credentials,
    )
    stage = R2Client.from_runtime_identity(
        settings.r2,
        settings.identities,
        R2RuntimePurpose.SNOWFLAKE_STAGE,
        credential_values=credentials,
    )

    ingestion.put_bytes("manifests/_smoke/runtime.json", b"synthetic")
    assert calls[0]["aws_access_key_id"] == "seeded-ingest-access"
    assert calls[0]["aws_secret_access_key"] == "seeded-ingest-secret"
    assert calls[1]["aws_access_key_id"] == "seeded-stage-access"
    assert calls[1]["aws_secret_access_key"] == "seeded-stage-secret"
    assert all(
        call["endpoint_url"] == "https://seeded-account.r2.cloudflarestorage.com" for call in calls
    )
    with pytest.raises(R2AccessPolicyError, match="read-only"):
        stage.put_bytes("manifests/_smoke/forbidden.json", b"synthetic")
    with pytest.raises(R2AccessPolicyError, match="read-only"):
        stage.delete("manifests/_smoke/forbidden.json")
    assert not fakes[1].objects


def test_r2_runtime_identity_missing_credentials_fails_without_value_leak(
    tmp_path: Path,
) -> None:
    settings = load_settings(environ={}, env_file=tmp_path / ".env")
    with pytest.raises(ValueError) as captured:
        R2Client.from_runtime_identity(
            settings.r2,
            settings.identities,
            R2RuntimePurpose.SNOWFLAKE_STAGE,
            credential_values={"R2_ACCOUNT_ID": "seeded-account"},
        )

    message = str(captured.value)
    assert "R2_STAGE_ACCESS_KEY_ID" in message
    assert "R2_STAGE_SECRET_ACCESS_KEY" in message
    assert "seeded-account" not in message
