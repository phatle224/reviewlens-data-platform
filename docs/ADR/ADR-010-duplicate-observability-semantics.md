# ADR-010: Report deterministic duplicates separately from invalid quarantine

- Status: Accepted
- Date: 2026-08-14
- Scope: M2 ingestion observability and exit gate

## Context

The approved Olist geolocation source contains many exact repeated business rows.
M2 deliberately removes those candidate duplicates before immutable Bronze and
reconciles them as an explicit source disposition. The first full private DAG run
proved that behavior, but the operations snapshot grouped duplicate rows with
contract-invalid quarantine rows. That made the generic five-percent quarantine
alert fire even though validation and parsing had rejected zero rows.

## Decision

Expose `duplicate` as its own bounded metadata-only outcome. Keep `quarantined`
for rows rejected by the typed contract and keep `parse_failed` separate. The
source equation is therefore:

`source = accepted + duplicate + quarantined + parse_failed`.

The quarantine-rate alert uses only invalid quarantine and parse failures.
Duplicate counts remain visible and must still reconcile, but expected,
deterministic deduplication does not raise an invalid-data alert.

## Consequences

- No source, R2 object, Bronze row, record hash or immutable load-history entry is
  rewritten.
- Operators can distinguish source duplication from contract/parser failures.
- A duplicate-count change remains observable and must be investigated during a
  new source-release review.
- M2 exit evidence must include all six row outcomes and an empty alert list.
