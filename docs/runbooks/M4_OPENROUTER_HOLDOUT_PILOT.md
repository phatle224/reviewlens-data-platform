# M4 private OpenRouter holdout pilot

## Scope

Only run this after the 200 human labels pass validation. The pilot processes
exactly 40 blind-holdout reviews, never the 160 training reviews. Queue,
predictions and reports remain under private_evaluation and are never committed,
uploaded or shown in screenshots.

Every item must pass DLP before a provider request. The pilot uses pinned model,
data collection deny, no fallback, two requests per second, 200 completion tokens
per review and the existing 5 USD project budget ledger.

Each provider dispatch requires separate owner approval. Do not automatically
retry a failed dispatch because a retry can create cost.

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

Success reports only prediction_count 40 and private_pilot_complete. The
prediction file contains row-level output and must remain private.

## Failure handling

If the command returns OPENROUTER_HTTP_4xx, OPENROUTER_HTTP_5xx,
OPENROUTER_RESPONSE_INVALID, AI_ENRICHMENT_BUDGET_EXHAUSTED or a DLP code, stop.
Do not retry. Inspect runtime_state/ai_enrichment_budget.json only for aggregate
USD, do not edit it, and ask the owner for explicit retry approval.

## Evaluation after a complete pilot

~~~powershell
uv run reviewlens-golden-pack evaluate --labels-path private_evaluation\m4_enrichment_v1\labels.jsonl --split-seed m4-eval-holdout-v1 --predictions-path private_evaluation\m4_enrichment_v1\holdout_predictions.jsonl --enrichment-version <sha256-from-pilot> --report-path private_evaluation\m4_enrichment_v1\evaluation_report.json
~~~

The evaluator accepts only exact holdout IDs and writes aggregate metrics only.
