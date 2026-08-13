# Airflow 3 orchestration

`dags/olist_pipeline.py` defines the stable ReviewLens task graph with the
public Airflow 3 `airflow.sdk` API. It is manual-only (`schedule=None`), has a
single active DAG run, and assigns every task a retry policy, execution timeout,
and one-slot resource pool.

## M2 ingestion boundary

- DAG parsing does not read `.env`, `config/config.toml`, Airflow Variables or
  Connections, and does not call R2, Snowflake, OpenRouter, Chroma or any network.
- `validate_source`, `upload_to_r2` and `copy_to_bronze` are enabled runtime task
  bodies. Their XCom payloads contain versioned IDs, object keys, hashes and counts
  only—never credentials or row text.
- Execution remains fail-closed unless `REVIEWLENS_ENABLE_OLIST_PIPELINE=1` and
  both `REVIEWLENS_SOURCE_DIR` and `REVIEWLENS_OUTPUT_DIR` are available inside
  the worker. The Compose service mounts `archive/` read-only and writes derived
  artifacts only to the private Airflow runtime volume.
- Source/archive and raw artifacts are create-only; Parquet timestamps and IDs are
  deterministic; Snowflake COPY uses `FORCE=FALSE`. Airflow retries therefore
  resume or replay instead of overwriting data.
- M3-M5 tasks remain fail-closed skip guards until their owning milestone passes
  its unit, failure, idempotency, security and cost gates. The first unavailable
  milestone is marked skipped and default trigger rules skip everything downstream,
  allowing a successful M2-only DAG run without executing future work.
- Apache Airflow does not support native Windows runtime. Local execution will
  use the Linux container introduced by `IMP-M1-016`; the Windows test suite uses
  an isolated import-only compatibility shim and never starts Airflow services.

## Intentional private run

The Airflow image includes the locked ReviewLens runtime dependencies. Compose
maps the local ingestion and transform key files into fixed container paths so
Windows host paths never enter task code.

Before a real manual run:

1. Keep the exact nine approved CSVs plus `manifest.json` in ignored `archive/`.
2. Confirm `.env` points to the host ingestion and transform PKCS#8 key files.
3. Set `REVIEWLENS_ENABLE_OLIST_PIPELINE=1` only for the intended private run.
4. Build/start the refreshed Airflow image, then trigger `olist_pipeline` once.
5. Return the flag to `0` after the run and verify warehouse auto-suspend.

Do not put credentials, raw rows or review text into DAG-run configuration. A
failed task exposes only `AIRFLOW_INGESTION_TASK_FAILED`; detailed evidence is
restricted to identifiers, counts and stable error codes.

Normal run, replay/backfill, quarantine, alert response and shutdown procedures
are documented in [`docs/runbooks/M2_INGESTION_OPERATIONS.md`](../docs/runbooks/M2_INGESTION_OPERATIONS.md).

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
