"""Airflow 3 task graph for the ReviewLens Olist pipeline.

This module intentionally contains no provider, credential, environment, or
configuration access at import time. M2 ingestion imports its runtime only from
inside task bodies; later milestones remain fail-closed guards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from airflow.sdk import dag, task
from airflow.sdk.exceptions import AirflowSkipException

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
    description="Private Olist ingestion pipeline with gated downstream milestones",
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
    tags=["reviewlens", "olist", "local", "m2-ingestion"],
)
def build_olist_pipeline() -> None:
    """Build the stable task topology without touching an external system."""

    @task(
        task_id="validate_source",
        pool=POOL_CONTROL,
        pool_slots=1,
        retries=2,
        execution_timeout=timedelta(minutes=10),
    )
    def validate_source() -> dict[str, object]:
        from reviewlens.ingestion.orchestration import execute_airflow_task

        return execute_airflow_task("validate_source")

    @task(
        task_id="upload_to_r2",
        pool=POOL_R2,
        pool_slots=1,
        retries=2,
        execution_timeout=timedelta(minutes=30),
    )
    def upload_to_r2(context: dict[str, object]) -> dict[str, object]:
        from reviewlens.ingestion.orchestration import execute_airflow_task

        return execute_airflow_task("upload_to_r2", context)

    @task(
        task_id="copy_to_bronze",
        pool=POOL_SNOWFLAKE,
        pool_slots=1,
        retries=2,
        execution_timeout=timedelta(minutes=30),
    )
    def copy_to_bronze(context: dict[str, object]) -> dict[str, object]:
        from reviewlens.ingestion.orchestration import execute_airflow_task

        return execute_airflow_task("copy_to_bronze", context)

    @task(do_xcom_push=False)
    def milestone_guard(step: str) -> None:
        raise AirflowSkipException(
            f"{step} belongs to a later milestone and is not enabled for execution yet"
        )

    validated = validate_source()
    uploaded = upload_to_r2(validated)
    copied = copy_to_bronze(uploaded)
    guarded_tasks = {
        task_id: milestone_guard.override(
            task_id=task_id,
            pool=pool,
            pool_slots=1,
            retries=retries,
            execution_timeout=timedelta(minutes=timeout_minutes),
        )(task_id)
        for task_id, pool, retries, timeout_minutes in TASK_SPECS[3:]
    }
    copied >> guarded_tasks[TASK_SPECS[3][0]]
    for upstream_id, downstream_id in TASK_EDGES[3:]:
        guarded_tasks[upstream_id] >> guarded_tasks[downstream_id]


olist_pipeline = build_olist_pipeline()
