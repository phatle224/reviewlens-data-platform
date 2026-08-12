"""Secret-safe Cloudflare R2 adapter using its S3-compatible API."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import quote

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from reviewlens.config import IdentityConfig, R2Config


class _StreamingBody(Protocol):
    def read(self, amount: int | None = None) -> bytes: ...

    def close(self) -> None: ...


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


class R2ObjectAlreadyExistsError(FileExistsError):
    """Raised when a conditional create loses to an existing immutable key."""


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

    def put_bytes_create_only(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> R2ObjectMetadata:
        if not self._writable:
            raise R2AccessPolicyError("R2 snowflake_stage identity is read-only")
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
                Metadata=metadata or {},
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if _is_precondition_failure(exc):
                raise R2ObjectAlreadyExistsError("R2_OBJECT_ALREADY_EXISTS") from None
            raise
        return self.head(key)

    def put_file_create_only(
        self,
        key: str,
        path: Path,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> R2ObjectMetadata:
        if not self._writable:
            raise R2AccessPolicyError("R2 snowflake_stage identity is read-only")
        if not path.is_file() or path.is_symlink():
            raise ValueError("R2 upload source must be a regular file")
        try:
            with path.open("rb") as handle:
                self._client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=handle,
                    ContentType=content_type,
                    Metadata=metadata or {},
                    IfNoneMatch="*",
                )
        except ClientError as exc:
            if _is_precondition_failure(exc):
                raise R2ObjectAlreadyExistsError("R2_OBJECT_ALREADY_EXISTS") from None
            raise
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

    def download_sha256(self, key: str, *, chunk_bytes: int = 1_048_576) -> tuple[str, int]:
        if chunk_bytes < 1:
            raise ValueError("chunk_bytes must be positive")
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        body = cast(_StreamingBody, response["Body"])
        digest = hashlib.sha256()
        observed_bytes = 0
        try:
            while chunk := body.read(chunk_bytes):
                digest.update(chunk)
                observed_bytes += len(chunk)
        finally:
            body.close()
        return digest.hexdigest(), observed_bytes

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


def _is_precondition_failure(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"409", "412", "ConditionalRequestConflict", "PreconditionFailed"} or status in {
        409,
        412,
    }
