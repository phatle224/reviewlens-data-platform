# Snowflake foundation contract

`001_foundation.sql` is the idempotent, secret-free M1 bootstrap for the one local
portfolio runtime. It creates:

- database `REVIEWLENS` and schemas `BRONZE`, `SILVER`, `AI`, `GOLD`, `AUDIT`,
  and `QUARANTINE`;
- `REVIEWLENS_WH` at `XSMALL`, with 60-second auto-suspend and auto-resume;
- a 10-credit monthly resource monitor with notifications at 50/80% and an
  immediate suspend at 100%;
- JSON file format `REVIEWLENS.BRONZE.JSONL_FORMAT` for synthetic smoke tests;
- Olist CSV file format `REVIEWLENS.BRONZE.OLIST_CSV_FORMAT` for the nine-file
  Brazilian e-commerce source contract.

The R2 external stage is deliberately not stored as rendered SQL. The Python
adapter builds `REVIEWLENS.BRONZE.R2_STAGE` in memory from the dedicated
read-only `R2_STAGE_*` environment credentials and sends it directly to
Snowflake. It uses the Snowflake
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
warehouse in cleanup. It does not use Olist source data or OpenRouter. The real
Olist upload and nine-table load are M2 concerns and require the source manifest,
privacy scan and explicit operator action.

`002_roles.sql` creates the least-privilege custom role hierarchy under
`SYSADMIN`. It also creates `REVIEWLENS_SQL_WH`, an isolated XSMALL/60-second
warehouse attached to the same resource monitor. The role boundaries are:

| Role | Broad baseline | Object-specific grants added later |
|---|---|---|
| `INGEST_ROLE` | Stage/file-format usage; insert-only Bronze/Quarantine | Bronze target tables |
| `TRANSFORMER_ROLE` | Read Bronze; create/read/write Silver | dbt-owned Silver objects |
| `AI_ENRICH_ROLE` | Silver/AI/Audit containers | Approved review view and AI/audit targets |
| `VECTOR_INDEXER_ROLE` | AI container | Approved release RAG document view |
| `GOLD_BUILDER_ROLE` | Create Gold objects; Silver/AI containers | Approved release inputs |
| `ANALYST_ROLE` | Gold container | Published Gold views |
| `TEXT_TO_SQL_ROLE` | Gold container and isolated SQL warehouse | Curated semantic views only |
| `RAG_ROLE` | AI container | Release-bound secure RAG document view |

AI, Gold-consumption, RAG and Text-to-SQL object grants are intentionally exact,
not schema-wide future grants. Their migrations add access only when the
approved object exists. ChromaDB writer/reader credentials are separate local
service boundaries and are not Snowflake roles.

Run the static role contract:

```powershell
.venv\Scripts\pytest.exe tests\test_snowflake_rbac.py -q
```

Run the opt-in live positive/negative permission suite:

```powershell
$env:REVIEWLENS_RUN_LIVE_SNOWFLAKE_RBAC='1'
.venv\Scripts\pytest.exe tests\live\test_snowflake_rbac_live.py -q -rs
```

The live suite disables secondary roles for every service-role probe, creates
only synthetic test objects, re-applies the role DDL to verify idempotency,
checks allowed and denied operations, drops the probes and suspends both
warehouses. The bootstrap connection uses `ACCOUNTADMIN` only to provision and
test roles; no runtime credential is assigned an admin role.

`003_service_identities.sql` creates eight dedicated `TYPE=SERVICE` users. New
users are disabled by default, have empty default secondary roles and receive
exactly one corresponding service role. Re-applying the file does not disable an
already activated user. It contains no password, private/public key or rendered
credential. Register the recommended role-restricted named key pair and perform
rotation/revocation using the
[M1 credential runbook](../../docs/runbooks/M1_CREDENTIAL_ROTATION.md).

Run the static service-identity contract:

```powershell
.venv\Scripts\pytest.exe tests\test_service_identities.py -q
```

Run the opt-in named-key authentication suite:

```powershell
$env:REVIEWLENS_RUN_LIVE_SNOWFLAKE_IDENTITIES='1'
.venv\Scripts\pytest.exe tests\live\test_snowflake_service_identities_live.py -q -rs -p no:cacheprovider
```

The suite verifies each named key is active and role-restricted, then logs in as
all eight service users and checks the exact current user, primary role,
warehouse and database. Runtime connection fails closed unless
`CURRENT_SECONDARY_ROLES()` reports no active/requested secondary role. Both
warehouses are suspended in cleanup.

## Audit ledger migration

`004_audit_ledgers.sql` creates versioned, append-only ingestion, source-file,
processing, release and AI invocation ledgers plus the guarded local active
release pointer. The tables contain IDs, hashes, counts, versions, cost and
sanitized metadata; they intentionally contain no raw payload, review text,
prompt text, response body or credential value.

Snowflake standard-table primary/unique constraints are informational, while
`NOT NULL` is enforced. Producers must therefore generate deterministic event
IDs and use replay-safe writes; later M2-M5 implementations own those scenario
tests. The migration itself uses only DDL `CREATE ... IF NOT EXISTS`, exposes a
constant `SCHEMA_COMPATIBILITY` view, and never replaces an existing table or
runs DML. Applying it therefore does not select/resume a virtual warehouse.

Runtime grants are exact-table only. Event producers receive `SELECT, INSERT`
without `UPDATE`, `DELETE`, `TRUNCATE`, ownership or future-table grants. The
active pointer is read-only until M3 creates an owner-executed guarded publish
procedure, so M1 code cannot bypass release gates.

Run the offline migration contract:

```powershell
.venv\Scripts\pytest.exe tests\test_snowflake_audit.py -q
```

Apply the up migration only from the owner/bootstrap session:

```powershell
.venv\Scripts\dotenv.exe -f .env run -- `
  .venv\Scripts\python.exe -c "from pathlib import Path; from reviewlens.config import load_settings; from reviewlens.providers.snowflake import SnowflakeClient; c=SnowflakeClient.connect_bootstrap(load_settings().snowflake); c.apply_sql_file(Path('infra/snowflake/004_audit_ledgers.sql'), operation='audit migration'); c.close()"
```

The down migration is destructive and is not part of normal setup. It fails
closed unless both exact session variables are set in the same Snowflake owner
session. Run `004_audit_ledgers_down.sql` as one Snowflake Scripting statement
in Snowsight/Snowflake CLI, not through the repository's simple statement
splitter:

```sql
SET REVIEWLENS_RUNTIME = 'local';
SET REVIEWLENS_AUDIT_DOWN_CONFIRMATION = 'DROP_REVIEWLENS_AUDIT_LEDGERS';
-- Then execute the complete EXECUTE IMMEDIATE block from 004_audit_ledgers_down.sql.
```

This design follows Snowflake's current
[table/constraint semantics](https://docs.snowflake.com/en/sql-reference/constraints),
[session-variable contract](https://docs.snowflake.com/en/sql-reference/session-variables),
and [Snowflake Scripting exception handling](https://docs.snowflake.com/en/developer-guide/snowflake-scripting/exceptions).
