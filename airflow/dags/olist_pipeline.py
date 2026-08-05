"""Airflow 3 scaffold for the ReviewLens Olist pipeline.

This module intentionally contains no provider, credential, environment, or
configuration access at import time. Runtime implementations replace the
fail-closed task callable in the milestone that owns each task.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from airflow.sdk import dag, task

DAG_ID = "olist_pipeline"

POOL_CONTROL = "reviewlens_control"
POOL_R2 = "reviewlens_r2"
POOL_SNOWFLAKE = "reviewlens_snowflake"
POOL_AI = "reviewlens_ai"

# task_id, pool, retries, execution timeout in minutes
TASK_SPECS = (
    ("validate_source", POOL_CONTROL, 2, 10),
    ("upload_to_r2", POOL_R2, 2, 30),
    ("copy_to_bronze", POOL_SNOWFLAKE, 2, 30),
    ("dbt_build_silver", POOL_SNOWFLAKE, 2, 45),
    ("dbt_test_silver", POOL_SNOWFLAKE, 2, 20),
    ("enrich_reviews", POOL_AI, 1, 60),
    ("validate_enrichment", POOL_SNOWFLAKE, 2, 20),
    ("build_embeddings", POOL_AI, 1, 60),
    ("dbt_build_gold", POOL_SNOWFLAKE, 2, 45),
    ("dbt_test_gold", POOL_SNOWFLAKE, 2, 20),
    ("publish_metrics", POOL_CONTROL, 1, 10),
)

TASK_EDGES = tuple(
    (TASK_SPECS[index][0], TASK_SPECS[index + 1][0]) for index in range(len(TASK_SPECS) - 1)
)


@dag(
    dag_id=DAG_ID,
    description="Fail-closed M1 scaffold for the Olist intelligence pipeline",
    schedule=None,
    start_date=datetime(2026, 8, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=4),
    default_args={
        "owner": "reviewlens-solo-developer",
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": 2.0,
    },
    tags=["reviewlens", "olist", "local", "m1-scaffold"],
)
def build_olist_pipeline() -> None:
    """Build the stable task topology without touching an external system."""

    @task(do_xcom_push=False)
    def milestone_guard(step: str) -> None:
        raise RuntimeError(
            f"{step} is an M1 task-graph scaffold and is not enabled for execution yet"
        )

    tasks = {
        task_id: milestone_guard.override(
            task_id=task_id,
            pool=pool,
            pool_slots=1,
            retries=retries,
            execution_timeout=timedelta(minutes=timeout_minutes),
        )(task_id)
        for task_id, pool, retries, timeout_minutes in TASK_SPECS
    }

    for upstream_id, downstream_id in TASK_EDGES:
        tasks[upstream_id] >> tasks[downstream_id]


olist_pipeline = build_olist_pipeline()
