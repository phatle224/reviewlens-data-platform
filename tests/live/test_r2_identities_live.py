from __future__ import annotations

import hashlib
import json
import os
from typing import Any
from uuid import uuid4

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from reviewlens.config import AppSettings, DataMode, load_environment_values, load_settings
from reviewlens.providers.r2 import R2Client, R2RuntimePurpose

pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.environ.get("REVIEWLENS_RUN_LIVE_R2_IDENTITIES") != "1",
    reason="set REVIEWLENS_RUN_LIVE_R2_IDENTITIES=1 for dedicated R2 identity tests",
)
def test_dedicated_r2_ingestion_write_and_stage_read_only_contract() -> None:
    settings = load_settings()
    credentials = load_environment_values()
    assert settings.data_mode is DataMode.SYNTHETIC
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
    key = f"manifests/_smoke/runtime-identities/{uuid4()}.json"
    forbidden_key = f"manifests/_smoke/runtime-identities/{uuid4()}-forbidden.json"
    body = json.dumps(
        {"data_class": "synthetic", "source": "reviewlens-r2-runtime-identity-smoke"},
        sort_keys=True,
    ).encode()
    checksum = hashlib.sha256(body).hexdigest()
    ingestion_write_succeeded = False
    stage_write_succeeded = False

    try:
        uploaded = ingestion.put_bytes(
            key,
            body,
            content_type="application/json",
            metadata={"data-class": "synthetic", "sha256": checksum},
        )
        ingestion_write_succeeded = True
        assert uploaded.size == len(body)
        assert stage.head(key).metadata["sha256"] == checksum
        assert hashlib.sha256(stage.get_bytes(key)).hexdigest() == checksum
        assert key in stage.list_keys("manifests/_smoke/runtime-identities/")
        assert ingestion.account_level_bucket_listing_is_denied()
        assert stage.account_level_bucket_listing_is_denied()

        raw_stage = _raw_stage_client(settings, credentials)
        try:
            raw_stage.put_object(
                Bucket=settings.r2.bucket,
                Key=forbidden_key,
                Body=b'{"data_class":"synthetic"}\n',
                ContentType="application/json",
            )
            stage_write_succeeded = True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            assert code in {"401", "403", "AccessDenied", "Unauthorized"}
        assert not stage_write_succeeded
    finally:
        if ingestion_write_succeeded:
            ingestion.delete(key)
        if stage_write_succeeded:
            ingestion.delete(forbidden_key)

    assert not ingestion.exists(key)
    assert not ingestion.exists(forbidden_key)


def _raw_stage_client(
    settings: AppSettings,
    credentials: dict[str, str],
) -> Any:
    endpoint = settings.r2.endpoint
    if endpoint is None:
        raise ValueError("R2 endpoint is required")
    access_env = settings.identities.r2_stage_access_key_env
    secret_env = settings.identities.r2_stage_secret_key_env
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=credentials[access_env],
        aws_secret_access_key=credentials[secret_env],
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 1, "mode": "standard"},
            s3={"addressing_style": "path"},
        ),
    )
