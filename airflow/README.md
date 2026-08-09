# Airflow 3 orchestration scaffold

`dags/olist_pipeline.py` defines the stable ReviewLens task graph with the
public Airflow 3 `airflow.sdk` API. It is manual-only (`schedule=None`), has a
single active DAG run, and assigns every task a retry policy, execution timeout,
and one-slot resource pool.

## M1 safety boundary

- DAG parsing does not read `.env`, `config/config.toml`, Airflow Variables or
  Connections, and does not call R2, Snowflake, OpenRouter, Chroma or any network.
- Task bodies are fail-closed M1 guards. An accidental manual trigger stops at
  `validate_source` before external work or paid usage.
- M2-M5 replace each guard only when the owning ingestion, transformation, AI,
  and release gate has its own unit, failure, idempotency, security, and cost tests.
- Apache Airflow does not support native Windows runtime. Local execution will
  use the Linux container introduced by `IMP-M1-016`; the Windows test suite uses
  an isolated import-only compatibility shim and never starts Airflow services.

## Pools

`pools.json` is versioned separately because declaring a task's `pool` does not
create that pool. Once the local Linux Airflow service exists, import the manifest:

```powershell
docker compose exec airflow airflow pools import /opt/reviewlens/airflow/pools.json
```

All pools have one slot. This is deliberate for a solo portfolio demo: R2 and
Snowflake work cannot fan out, and paid AI tasks are serialized to protect the
USD 5 OpenRouter project budget.

## Offline verification

```powershell
uv sync --group airflow --locked
uv run --group airflow pytest tests/test_airflow.py -q
uv run --group airflow ruff check airflow tests/test_airflow.py --select AIR301,AIR302,AIR303
```

The contract test imports the real DAG in an isolated subprocess, validates the
exact topology and policies, blocks network calls and dotenv access, and checks
the pool manifest. It does not need credentials or a metadata database.

References: [Airflow 3 public Task SDK](https://airflow.apache.org/docs/task-sdk/stable/api.html),
[DAG top-level-code guidance](https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html#top-level-python-code),
and [pool behavior](https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/pools.html).
