# Snowflake foundation contract

`001_foundation.sql` is the idempotent, secret-free M1 bootstrap for the one local
portfolio runtime. It creates:

- database `REVIEWLENS` and schemas `BRONZE`, `SILVER`, `AI`, `GOLD`, `AUDIT`,
  and `QUARANTINE`;
- `REVIEWLENS_WH` at `XSMALL`, with 60-second auto-suspend and auto-resume;
- a 10-credit monthly resource monitor with notifications at 50/80% and an
  immediate suspend at 100%;
- JSON file format `REVIEWLENS.BRONZE.JSONL_FORMAT`.

The R2 external stage is deliberately not stored as rendered SQL. The Python
adapter builds `REVIEWLENS.BRONZE.R2_STAGE` in memory from local environment
credentials and sends it directly to Snowflake. It uses the Snowflake
`s3compat://` contract, the Cloudflare R2 account endpoint, and
`AUTO_REFRESH=FALSE`. Never paste or save the rendered statement.

Run the static contract without managed-service access:

```powershell
.venv\Scripts\pytest.exe tests\test_snowflake.py -q
```

Run the owner-approved synthetic live smoke test:

```powershell
$env:REVIEWLENS_RUN_LIVE_SNOWFLAKE='1'
.venv\Scripts\pytest.exe tests\live\test_snowflake_live.py -q -rs
```

The live test uploads one small synthetic JSON object, applies the foundation,
verifies R2 stage `LIST` and `COPY INTO`, deletes the object, and suspends the
warehouse in cleanup. It does not use Yelp data or OpenRouter.

Role creation and least-privilege grants are intentionally deferred to
`IMP-M1-007`. Until then, bootstrap requires an owner-operated account role.

