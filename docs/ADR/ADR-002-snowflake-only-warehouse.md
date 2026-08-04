# ADR-002 — Snowflake-only Warehouse

- Status: Accepted
- Date: 2026-08-04
- Owner: Solo Developer (Data/Analytics hats)

## Decision

Use Snowflake for development, integration and portfolio demo. Use `dbt-snowflake` only; do not implement DuckDB or another warehouse fallback. Start with `X-SMALL`, `AUTO_SUSPEND=60`, `AUTO_RESUME=TRUE`, isolated schemas and resource monitors.

## Consequences

- SQL, dbt models and tests optimize for one dialect and one RBAC model.
- Development depends on Snowflake account availability and credits.
- Trial expiry/remaining credits are read from the account and tracked operationally; no fixed advertised duration is assumed.
- If the account becomes unavailable, the project reports backend unavailable rather than silently switching semantics.

## Verification

Connection smoke, dbt parse/compile, role negative tests, auto-suspend observation, resource monitor alert/suspend and single-local config contract.
