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

## Confirmed M1 development target

- R2 bucket: `reviewlens-data-dev`; location hint `apac`; Standard storage; public access disabled.
- Snowflake account: Standard Edition on AWS Asia Pacific (Singapore), `AWS_AP_SOUTHEAST_1`.
- This is a supported cross-provider topology: the Snowflake cloud identifies its compute deployment, while R2 is reached as external S3-compatible storage over HTTPS.
- Stage contract: `URL='s3compat://reviewlens-data-dev/<prefix>/'`, `ENDPOINT='<R2_ACCOUNT_ID>.r2.cloudflarestorage.com'`, direct scoped credentials injected outside Git, and `AUTO_REFRESH=FALSE` where applicable.
- R2 SDK clients use region `auto`; this does not change the Snowflake account region.

Cloudflare recommends the `apac` R2 location hint for Snowflake AWS Singapore. Snowflake enables Cloudflare `r2.cloudflarestorage.com` endpoints by default and supports bulk `COPY INTO` from S3-compatible external stages. Sources: [Cloudflare Snowflake region guidance](https://developers.cloudflare.com/r2/reference/partners/snowflake-regions/), [Snowflake S3-compatible storage](https://docs.snowflake.com/en/user-guide/data-load-s3-compatible-storage).
