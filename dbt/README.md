# ReviewLens dbt foundation

This is the Snowflake-only dbt Core project for the single local ReviewLens
runtime. It uses `REVIEWLENS_TRANSFORM_SVC` with `TRANSFORMER_ROLE`; it has no
DuckDB adapter, password fallback, staging target or production target.

M1 introduced the source interface and M2 created/loaded immutable Bronze. M3
now declares every Bronze business/lineage column and type, a canonical physical
grain test, `INGESTED_AT` freshness (warn after 2 days, error after 7 days), and
privacy metadata that prevents `RAW_PAYLOAD` or restricted review text from being
treated as a public/downstream interface. Conformed Silver/Gold models remain M3
work and build under versioned candidate physical namespaces.

Credentials stay in the ignored root `.env`. The profile reads only:

- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_TRANSFORM_PRIVATE_KEY_PATH`
- optional `SNOWFLAKE_TRANSFORM_PRIVATE_KEY_PASSPHRASE`

From the repository root, install and verify with:

```powershell
uv sync --group dbt --locked
.venv\Scripts\dotenv.exe -f .env run -- `
  .venv\Scripts\dbt.exe parse --project-dir dbt --profiles-dir dbt --no-partial-parse
.venv\Scripts\dotenv.exe -f .env run -- `
  .venv\Scripts\dbt.exe --no-populate-cache compile --project-dir dbt `
  --profiles-dir dbt --no-introspect --select source_contract_registry
```

`dbt parse` is the normal offline structural gate. `dbt compile` may establish a
Snowflake connection even with introspection disabled, so keep the X-Small
warehouse auto-suspend/resource monitor enabled and suspend it after live work.

After the M3 processing migration is explicitly applied, run the complete Bronze
source/freshness contract against Snowflake with:

```powershell
.venv\Scripts\dotenv.exe -f .env run -- `
  .venv\Scripts\dbt.exe test --project-dir dbt --profiles-dir dbt `
  --selector m3_bronze_contract
.venv\Scripts\dotenv.exe -f .env run -- `
  .venv\Scripts\dbt.exe source freshness --project-dir dbt --profiles-dir dbt `
  --selector m3_bronze_contract
```

These commands are live and can resume the configured warehouse; they are not
part of the offline M3 bootstrap bundle.
