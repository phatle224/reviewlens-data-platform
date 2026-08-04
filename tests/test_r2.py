from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from reviewlens.providers.r2 import R2Client


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
