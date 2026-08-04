"""Secret-safe Cloudflare R2 adapter using its S3-compatible API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.parse import quote

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from reviewlens.config import R2Config


class _StreamingBody(Protocol):
    def read(self) -> bytes: ...


class _S3Client(Protocol):
    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def list_objects_v2(self, **kwargs: Any) -> dict[str, Any]: ...

    def delete_object(self, **kwargs: Any) -> dict[str, Any]: ...

    def list_buckets(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class R2ObjectMetadata:
    key: str
    size: int
    etag: str
    metadata: dict[str, str]


class R2Client:
    """Minimal bucket-scoped operations needed by ingestion and smoke tests."""

    def __init__(self, *, bucket: str, endpoint: str, client: _S3Client) -> None:
        self.bucket = bucket
        self.endpoint = endpoint.rstrip("/")
        self._client = client

    @classmethod
    def from_config(cls, config: R2Config) -> R2Client:
        config.require_live_credentials()
        if (
            config.endpoint is None
            or config.access_key_id is None
            or config.secret_access_key is None
        ):
            raise ValueError("R2 endpoint and credentials must be configured")
        client = boto3.client(
            "s3",
            endpoint_url=config.endpoint,
            aws_access_key_id=config.access_key_id.get_secret_value(),
            aws_secret_access_key=config.secret_access_key.get_secret_value(),
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )
        return cls(bucket=config.bucket, endpoint=config.endpoint, client=cast(_S3Client, client))

    def put_bytes(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> R2ObjectMetadata:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata=metadata or {},
        )
        return self.head(key)

    def head(self, key: str) -> R2ObjectMetadata:
        response = self._client.head_object(Bucket=self.bucket, Key=key)
        return R2ObjectMetadata(
            key=key,
            size=int(response["ContentLength"]),
            etag=str(response.get("ETag", "")).strip('"'),
            metadata={str(k): str(v) for k, v in response.get("Metadata", {}).items()},
        )

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        body = cast(_StreamingBody, response["Body"])
        return body.read()

    def list_keys(self, prefix: str) -> tuple[str, ...]:
        response = self._client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        return tuple(str(item["Key"]) for item in response.get("Contents", []))

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True

    def account_level_bucket_listing_is_denied(self) -> bool:
        """Prove the application credential cannot enumerate account buckets."""

        try:
            self._client.list_buckets()
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"401", "403", "AccessDenied", "Unauthorized"}:
                return True
            raise
        return False

    def anonymous_object_url(self, key: str) -> str:
        encoded_key = quote(key, safe="/")
        return f"{self.endpoint}/{quote(self.bucket, safe='')}/{encoded_key}"
