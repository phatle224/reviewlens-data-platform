from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest

DAG_PATH = Path("airflow/dags/olist_pipeline.py")
POOLS_PATH = Path("airflow/pools.json")

EXPECTED_TASKS = (
    "validate_source",
    "upload_to_r2",
    "copy_to_bronze",
    "dbt_build_silver",
    "dbt_test_silver",
    "enrich_reviews",
    "validate_enrichment",
    "build_embeddings",
    "dbt_build_gold",
    "dbt_test_gold",
    "publish_metrics",
)
EXPECTED_EDGES = tuple(pairwise(EXPECTED_TASKS))
EXPECTED_POOLS = {
    "reviewlens_ai",
    "reviewlens_control",
    "reviewlens_r2",
    "reviewlens_snowflake",
}

INSPECT_DAG = r"""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys

# Airflow officially runs on POSIX. This import-only shim supplies the one hook
# absent on native Windows; it never starts a scheduler, worker or metadata DB.
if not hasattr(os, "register_at_fork"):
    os.register_at_fork = lambda **kwargs: None

def blocked(*args, **kwargs):
    raise AssertionError("DAG import attempted an external or credential side effect")

socket.create_connection = blocked
socket.socket.connect = blocked

import dotenv
dotenv.dotenv_values = blocked
dotenv.load_dotenv = blocked

dag_path = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("reviewlens_test_olist_pipeline", dag_path)
if spec is None or spec.loader is None:
    raise RuntimeError("could not build DAG module spec")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
dag = module.olist_pipeline

tasks = {}
for task_id, item in dag.task_dict.items():
    tasks[task_id] = {
        "upstream": sorted(item.upstream_task_ids),
        "downstream": sorted(item.downstream_task_ids),
        "pool": item.pool,
        "pool_slots": item.pool_slots,
        "retries": item.retries,
        "retry_delay_seconds": item.retry_delay.total_seconds(),
        "timeout_seconds": item.execution_timeout.total_seconds(),
    }

print(json.dumps({
    "dag_id": dag.dag_id,
    "schedule": dag.schedule,
    "catchup": dag.catchup,
    "max_active_runs": dag.max_active_runs,
    "dagrun_timeout_seconds": dag.dagrun_timeout.total_seconds(),
    "tasks": tasks,
}))
"""


def _inspect_dag() -> dict[str, Any]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in ("PASSWORD", "SECRET", "TOKEN", "KEY"))
    }
    environment["_AIRFLOW__AS_LIBRARY"] = "1"
    result = subprocess.run(  # noqa: S603 - current locked Python interpreter
        [sys.executable, "-c", INSPECT_DAG, str(DAG_PATH)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
        timeout=30,
    )
    return cast(dict[str, Any], json.loads(result.stdout))


@pytest.mark.contract
def test_olist_pipeline_imports_with_expected_graph_and_no_side_effects() -> None:
    inspected = _inspect_dag()

    assert inspected["dag_id"] == "olist_pipeline"
    assert inspected["schedule"] is None
    assert inspected["catchup"] is False
    assert inspected["max_active_runs"] == 1
    assert inspected["dagrun_timeout_seconds"] == 4 * 60 * 60
    assert tuple(inspected["tasks"]) == EXPECTED_TASKS

    actual_edges = {
        (task_id, downstream_id)
        for task_id, item in inspected["tasks"].items()
        for downstream_id in item["downstream"]
    }
    assert actual_edges == set(EXPECTED_EDGES)


@pytest.mark.contract
def test_every_task_has_bounded_retry_timeout_and_pool() -> None:
    tasks = _inspect_dag()["tasks"]

    assert {item["pool"] for item in tasks.values()} == EXPECTED_POOLS
    for item in tasks.values():
        assert item["pool_slots"] == 1
        assert item["retries"] >= 1
        assert item["retry_delay_seconds"] == 5 * 60
        assert 0 < item["timeout_seconds"] <= 60 * 60
    assert tasks["enrich_reviews"]["retries"] == 1
    assert tasks["build_embeddings"]["retries"] == 1
    assert tasks["enrich_reviews"]["pool"] == "reviewlens_ai"
    assert tasks["build_embeddings"]["pool"] == "reviewlens_ai"


def test_pool_manifest_matches_dag_and_serializes_paid_work() -> None:
    pools = json.loads(POOLS_PATH.read_text(encoding="utf-8"))

    assert set(pools) == EXPECTED_POOLS
    assert all(pool["slots"] == 1 for pool in pools.values())
    assert all(pool["include_deferred"] is False for pool in pools.values())
    assert "paid OpenRouter" in pools["reviewlens_ai"]["description"]


def test_dag_source_has_no_import_time_provider_or_credential_access() -> None:
    source = DAG_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert imported_modules <= {"__future__", "airflow", "datetime"}
    for forbidden in (
        "Variable.get",
        "BaseHook",
        "load_dotenv",
        "dotenv_values",
        "load_settings",
        "load_environment_values",
        "boto3",
        "snowflake.connector",
        "httpx",
        "chromadb",
        "os.environ",
        "getenv",
    ):
        assert forbidden not in source


def test_scaffold_is_manual_and_fails_closed_if_triggered_early() -> None:
    source = DAG_PATH.read_text(encoding="utf-8")

    assert "schedule=None" in source
    assert "M1 task-graph scaffold and is not enabled for execution yet" in source
    assert "raise RuntimeError" in source
