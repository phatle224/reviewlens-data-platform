from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from reviewlens.config import DataMode, load_settings
from reviewlens.providers.r2 import R2Client
from reviewlens.providers.snowflake import SnowflakeClient

pytestmark = pytest.mark.live


@pytest.mark.skipif(
    os.environ.get("REVIEWLENS_RUN_LIVE_SNOWFLAKE") != "1",
    reason="set REVIEWLENS_RUN_LIVE_SNOWFLAKE=1 for the synthetic R2-to-Snowflake smoke test",
)
def test_snowflake_foundation_and_r2_stage_copy_synthetic_row() -> None:
    settings = load_settings()
    assert settings.data_mode is DataMode.SYNTHETIC
    r2 = R2Client.from_config(settings.r2)
    snowflake = SnowflakeClient.connect_bootstrap(settings.snowflake)
    object_id = uuid4()
    key = f"manifests/_snowflake_smoke/{object_id}.json"
    body = json.dumps(
        {
            "data_class": "synthetic",
            "source": "reviewlens-m1-snowflake-live-smoke",
            "object_id": str(object_id),
        },
        sort_keys=True,
    ).encode()
    database = settings.snowflake.database
    warehouse = settings.snowflake.warehouse
    table = f"{database}.BRONZE._M1_R2_STAGE_SMOKE"

    try:
        r2.put_bytes(
            key,
            body,
            content_type="application/json",
            metadata={"data-class": "synthetic"},
        )
        snowflake.apply_foundation(Path("infra/snowflake/001_foundation.sql"))
        snowflake.create_or_replace_r2_stage(snowflake=settings.snowflake, r2=settings.r2)

        listed = snowflake.list_stage_path(database=database, key=key)
        assert len(listed) == 1
        assert key in str(listed[0][0])

        snowflake.execute(f"USE WAREHOUSE {warehouse}", operation="warehouse selection")
        snowflake.execute(
            f"CREATE OR REPLACE TEMPORARY TABLE {table} (payload VARIANT)",
            operation="synthetic smoke table creation",
        )
        snowflake.execute(
            f"""COPY INTO {table}
FROM (SELECT $1 FROM @{database}.BRONZE.R2_STAGE/{key})
FILE_FORMAT = (FORMAT_NAME = {database}.BRONZE.JSONL_FORMAT)
ON_ERROR = ABORT_STATEMENT
FORCE = TRUE""",
            operation="synthetic R2 COPY INTO",
        )
        rows = snowflake.query_all(
            f"SELECT payload:data_class::STRING, payload:object_id::STRING FROM {table}",
            operation="synthetic row reconciliation",
        )
        assert rows == [("synthetic", str(object_id))]
    finally:
        snowflake.suspend_warehouse(warehouse)
        snowflake.close()
        r2.delete(key)

    assert not r2.exists(key)
