---
name: reviewlens-dev-workflow
description: Execute and track the ReviewLens data-platform development lifecycle phase by phase. Use when the user asks to continue vibe coding, start or implement a ReviewLens milestone, pick the next task, run project tests, report progress, close a coding session, or update PRD/implementation/checklist/test/status documentation in this repository.
---

# ReviewLens development workflow

## Overview

Deliver the smallest verifiable slice of the active ReviewLens phase, then leave the repository with reproducible tests and an accurate status dashboard. Communicate with the solo developer in Vietnamese unless they request another language.

## 1. Establish project state

Work from the repository root. Read these files in order:

1. `docs/PROJECT_STATUS.md`.
2. `docs/phases/<current-phase>/README.md`.
3. `docs/phases/<current-phase>/<phase>_CHECKLIST.md`.
4. `docs/phases/<current-phase>/<phase>_TEST_CASES.md`.
5. The current phase section in `docs/IMPLEMENTATION_PLAN.md`.
6. Only the relevant requirements in `docs/PRD.md` and relevant ADRs.
7. `references/project-map.md` in this skill.

Also inspect `git status --short`. Treat existing changes as user work and preserve unrelated modifications. If `docs/PROJECT_STATUS.md` does not exist, create it before implementation using the headings required by the validator.

Determine the current phase from `PROJECT_STATUS.md`; confirm it against the phase checklist. Never infer completion solely from prose or a prior chat message.

## 2. Choose session scope

Select the smallest dependency-ready vertical slice that produces useful evidence. Prefer one to three related `IMP-Mx-nnn` items per session. For a large or unclear item, split it into documented subtasks before coding.

Before changing code:

- State the selected work item IDs, intended outcome, likely files, and test approach.
- Check dependencies, required user inputs, data-policy boundary, external cost, and secret requirements.
- Continue with synthetic fixtures or fakes when live credentials are absent and the plan permits it.
- Ask the user only when a missing choice materially changes architecture, cost, public exposure, or data handling.

Do not request or store secrets in chat or Markdown. Use environment variables and committed `.env.example` placeholders.

## 3. Prepare phase artifacts

For a new phase, create these files before implementation:

- `docs/phases/Mx/README.md`
- `docs/phases/Mx/Mx_CHECKLIST.md`
- `docs/phases/Mx/Mx_TEST_CASES.md`

Copy all phase work-item IDs from the implementation plan into the checklist. Define test cases before or alongside implementation, including happy path, failure path, security/privacy, idempotency/replay, and cost controls when applicable.

Use the status vocabulary in `docs/phases/README.md`. A work item is `DONE` only when its artifact exists and its verification passes. Use `PARTIAL`, `BLOCKED`, or `DEFERRED` honestly; never convert a missing live test to `PASS`.

## 4. Implement safely

Follow repository conventions and the accepted ADRs. Keep provider access behind adapters, configuration typed, and generated artifacts reproducible. Add or update tests in the same slice as production code.

Apply these non-negotiable gates:

- Keep real Yelp data local unless documented eligibility, written approval, or a qualified review explicitly opens cloud/AI/public transfer.
- Use synthetic data for R2, Snowflake, OpenRouter, CI, screenshots, and public demos while that gate is closed.
- Keep Snowflake as the only warehouse; do not introduce DuckDB as a fallback.
- Keep R2 private, use scoped credentials, and use batch `COPY INTO` through `s3compat://` for the MVP.
- Keep ChromaDB local and versioned; treat Snowflake `AI.RAG_DOCUMENT` as authoritative.
- Enforce read-only allowlisted Text-to-SQL with negative tests.
- Respect budget caps and avoid paid live calls unless the task requires them and configuration is available.

Create an ADR when changing an accepted architecture, security boundary, source semantic, public-deployment decision, or irreversible data contract. Update the PRD only for requirement/scope changes; update the implementation plan only for delivery sequencing, work breakdown, estimates, or acceptance criteria.

## 5. Verify proportionally

Run the narrowest tests during iteration, then the relevant phase suite before declaring completion. Prefer:

1. Static checks, formatting, lint, typing, and secret scans.
2. Unit and contract tests using deterministic fixtures.
3. Data-quality/dbt tests and replay/idempotency tests.
4. Integration tests with fakes, then live synthetic smoke tests when credentials exist.
5. Security-negative, failure-injection, cost, latency, and rollback tests for high-risk paths.
6. Golden-set regression for enrichment, RAG, or Text-to-SQL.

Record the actual command, outcome, date, and evidence in `Mx_TEST_CASES.md`. A test that was not executed is `PENDING` or `DEFERRED`, never `PASS`.

Run the project-status validator before closing the session:

```powershell
python .agents/skills/reviewlens-dev-workflow/scripts/validate_project_status.py --root .
```

Fix validator errors. Treat warnings as explicit follow-up items when they cannot be resolved in the current scope.

## 6. Close every coding session

Update all relevant state before responding:

1. `Mx_CHECKLIST.md`: status and evidence for touched work items; phase totals and exit gate.
2. `Mx_TEST_CASES.md`: newly designed tests and actual results/evidence.
3. `docs/PROJECT_STATUS.md`: last update, current phase, recent work, test summary, blockers/risks, costs, required user inputs, and next three to five actions.
4. `docs/IMPLEMENTATION_PLAN.md`: only if sequencing or task definition changed.
5. `docs/PRD.md`: only if product scope or requirements changed.
6. ADR/decision register: only for a material decision.

Keep `PROJECT_STATUS.md` concise and make it the first file the user reads. Do not duplicate detailed logs there; link to the phase evidence.

Conclude in Vietnamese with:

- Outcome and work-item IDs completed or progressed.
- Tests run and whether they passed, failed, or were deferred.
- Current blocker/risk and any user input needed, without asking for secrets.
- Exact next recommended task.
- Links to `PROJECT_STATUS.md`, the active checklist, and active test cases.

Do not claim the phase is complete until all mandatory tests and exit criteria have evidence.
