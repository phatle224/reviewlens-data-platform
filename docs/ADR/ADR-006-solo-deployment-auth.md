# ADR-006 — Solo Local-first Deployment and Authentication Gate

- Status: Accepted for portfolio MVP
- Date: 2026-08-04
- Owner: Solo Developer (App/Security/Ops hats)

## Decision

Run Airflow, ChromaDB and Streamlit through Docker/local services during development while Snowflake, R2 and OpenRouter are managed external services. Default bind is localhost/private access. Internet exposure is not part of the initial MVP release.

Before any public deployment, require authenticated access using an approved OIDC/reverse-proxy pattern, rate limits, HTTPS, secret backend, external Terms/security review and the full negative security suite. A shared hard-coded password is not an approved public solution.

## Consequences

- M0/M1 can proceed without choosing a paid hosting platform.
- Public portfolio URL is a separate deployment decision, not an implicit extension of localhost.

## Verification

Local bind test, anonymous public route absence, secret scan, container non-root test and public-candidate gate check.

