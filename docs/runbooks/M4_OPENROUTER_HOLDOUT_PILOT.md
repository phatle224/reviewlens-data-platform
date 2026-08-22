# M4 private OpenRouter holdout pilot

## Scope

Only run this after the 200 human labels pass validation. The pilot processes
exactly 40 blind-holdout reviews, never the 160 training reviews. Queue,
predictions and reports remain under private_evaluation and are never committed,
uploaded or shown in screenshots.

Every item must pass DLP before a provider request. The pilot uses pinned model,
data collection deny, no fallback, two requests per second, 256 completion tokens
per review and the existing 5 USD project budget ledger. The v2 prompt requests
compact output (a short summary and at most two short highlights) while the
strict JSON Schema and semantic validator remain authoritative.

The batch uses exactly one initial request per holdout item. If that response is
schema/semantic-invalid, it can make exactly one schema-only repair request for
that same DLP-approved item; a failed repair quarantines the item and stops the
batch. Thus an owner approval for a repair-enabled batch covers at most 80
provider dispatches. No transient/network retry is automatic.

## Preflight only (no provider request)

~~~powershell
uv run dotenv -f .env run -- uv run reviewlens-m4-holdout-pilot preflight --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --annotation-queue-path private_evaluation\m4_enrichment_v1\annotation_queue.jsonl --split-seed m4-eval-holdout-v1
~~~

Continue only when the aggregate result has approved_count 40, holdout_count 40,
and status ready_for_authorized_private_pilot.

## Owner-authorized run

~~~powershell
uv run dotenv -f .env run -- uv run reviewlens-m4-holdout-pilot run --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --annotation-queue-path private_evaluation\m4_enrichment_v1\annotation_queue.jsonl --split-seed m4-eval-holdout-v1 --predictions-path private_evaluation\m4_enrichment_v1\holdout_predictions.jsonl
~~~

Success reports only a non-secret enrichment-version hash, prediction_count 40
and private_pilot_complete. The prediction file contains row-level output and
must remain private.

## Failure handling

If the command returns OPENROUTER_HTTP_4xx, OPENROUTER_HTTP_5xx,
OPENROUTER_RESPONSE_INVALID, AI_ENRICHMENT_SCHEMA_INVALID,
AI_ENRICHMENT_BUDGET_EXHAUSTED or a DLP code, stop. Do not launch another
batch. Inspect runtime_state/ai_enrichment_budget.json only for aggregate USD,
do not edit it, and ask the owner for explicit recovery approval.

## Single-item diagnostic retry

When the owner authorizes exactly one diagnostic retry, run this command. It
sends one DLP-approved holdout item, persists no prediction and prints only a
sanitized status:

~~~powershell
uv run dotenv -f .env run -- uv run reviewlens-m4-holdout-pilot diagnose --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --annotation-queue-path private_evaluation\m4_enrichment_v1\annotation_queue.jsonl --split-seed m4-eval-holdout-v1
~~~

Do not treat diagnostic success as a 40-item evaluation. A full prediction batch
still requires a separate owner approval.

## Evaluation after a complete pilot

~~~powershell
uv run reviewlens-golden-pack evaluate --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --split-seed m4-eval-holdout-v1 --predictions-path private_evaluation\m4_enrichment_v1\holdout_predictions.jsonl --enrichment-version <sha256-from-pilot> --report-path private_evaluation\m4_enrichment_v1\evaluation_report.json
~~~

The evaluator accepts only exact holdout IDs and writes aggregate metrics only.
