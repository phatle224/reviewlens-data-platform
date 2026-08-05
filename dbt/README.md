# ReviewLens dbt foundation

This is the Snowflake-only dbt Core project for the single local ReviewLens
runtime. It uses `REVIEWLENS_TRANSFORM_SVC` with `TRANSFORMER_ROLE`; it has no
DuckDB adapter, password fallback, staging target or production target.

M1 declares the nine immutable Bronze source interfaces and compiles one
metadata-only contracted registry. It does not read or materialize Olist rows.
M2 owns Bronze creation/loading, while M3 owns conformed Silver/Gold models.

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
