"""Secret-safe Cloudflare R2 adapter using its S3-compatible API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, cast
from urllib.parse import quote

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from reviewlens.config import IdentityConfig, R2Config


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


class R2RuntimePurpose(StrEnum):
    """Dedicated credential boundary for each R2 runtime consumer."""

    INGESTION = "ingestion"
    SNOWFLAKE_STAGE = "snowflake_stage"


class R2AccessPolicyError(PermissionError):
    """Raised before a read-only adapter can issue a mutating R2 request."""


class R2Client:
    """Minimal bucket-scoped operations needed by ingestion and smoke tests."""

    def __init__(
        self,
        *,
        bucket: str,
        endpoint: str,
        client: _S3Client,
        writable: bool = True,
    ) -> None:
        self.bucket = bucket
        self.endpoint = endpoint.rstrip("/")
        self._client = client
        self._writable = writable

    @classmethod
    def from_config(cls, config: R2Config) -> R2Client:
        """Build the owner/bootstrap adapter used only by explicit live tests."""

        config.require_live_credentials()
        if (
            config.endpoint is None
            or config.access_key_id is None
            or config.secret_access_key is None
        ):
            raise ValueError("R2 endpoint and credentials must be configured")
        return cls._from_credentials(
            config=config,
            endpoint=config.endpoint,
            access_key_id=config.access_key_id.get_secret_value(),
            secret_access_key=config.secret_access_key.get_secret_value(),
            writable=True,
        )

    @classmethod
    def from_runtime_identity(
        cls,
        config: R2Config,
        identities: IdentityConfig,
        purpose: R2RuntimePurpose,
        *,
        credential_values: Mapping[str, str],
    ) -> R2Client:
        """Build a bucket-scoped runtime adapter without using bootstrap secrets."""

        account_id = config.account_id or credential_values.get("R2_ACCOUNT_ID")
        if not account_id:
            raise ValueError("R2 runtime access requires R2_ACCOUNT_ID")
        if purpose is R2RuntimePurpose.INGESTION:
            access_env = identities.r2_ingest_access_key_env
            secret_env = identities.r2_ingest_secret_key_env
            writable = True
        else:
            access_env = identities.r2_stage_access_key_env
            secret_env = identities.r2_stage_secret_key_env
            writable = False
        access_key_id = credential_values.get(access_env)
        secret_access_key = credential_values.get(secret_env)
        if not access_key_id or not secret_access_key:
            raise ValueError(f"R2 {purpose.value} access requires {access_env} and {secret_env}")
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        return cls._from_credentials(
            config=config,
            endpoint=endpoint,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            writable=writable,
        )

    @classmethod
    def _from_credentials(
        cls,
        *,
        config: R2Config,
        endpoint: str,
        access_key_id: str,
        secret_access_key: str,
        writable: bool,
    ) -> R2Client:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )
        return cls(
            bucket=config.bucket,
            endpoint=endpoint,
            client=cast(_S3Client, client),
            writable=writable,
        )

    def put_bytes(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> R2ObjectMetadata:
        if not self._writable:
            raise R2AccessPolicyError("R2 snowflake_stage identity is read-only")
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
        if not self._writable:
            raise R2AccessPolicyError("R2 snowflake_stage identity is read-only")
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
