# ADR-001 — Cloudflare R2 as Object Storage

- Status: Accepted
- Date: 2026-08-04
- Owner: Solo Developer (Platform/Data hats)

## Decision

Use one private Cloudflare R2 Standard bucket per environment with prefixes `source/`, `raw/`, `quarantine/` and `manifests/`. Python uses the S3-compatible endpoint and scoped token. Snowflake loads through `s3compat://` external stages; Airflow owns manifest discovery and batch `COPY INTO`. No Snowpipe or metadata auto-refresh in MVP.

## Consequences

- No AWS account/IAM/KMS/event integration.
- Direct credentials are restricted to the specific bucket and stored only in secret backend/Snowflake stage configuration.
- Cross-cloud latency is benchmarked; R2 and Snowflake regions are selected as close as practical.
- R2 logical URIs in audit are stable; signed/public URLs are never identity fields.

## Verification

Private-access negative test, scoped-token test, upload/download checksum, Snowflake `LIST` and `COPY INTO`, replay/no-overwrite and lifecycle checks.

