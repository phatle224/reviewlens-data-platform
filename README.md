# ReviewLens Data Platform

ReviewLens is a synthetic-first portfolio data platform for restaurant intelligence. The target architecture uses Cloudflare R2, Snowflake, dbt, Airflow, OpenRouter, ChromaDB and Streamlit while keeping provider access behind typed Python adapters.

The project is currently in **M1 — Foundation**. It runs as one local demo environment; no staging, production or public URL is provisioned.

## Data and security boundary

- Real Yelp Open Dataset files, review text, embeddings and derived data are never committed or published.
- Until the compliance gate is explicitly reopened, managed cloud, external AI, CI and portfolio evidence use synthetic fixtures only.
- `config/config.toml` contains non-sensitive configuration. Credentials belong only in the ignored local `.env` file.
- R2 remains private and Snowflake is the only warehouse; there is no DuckDB fallback.

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop (needed by later M1 services)
- Optional live-test access to the private R2 bucket and Snowflake account

## Local setup

```powershell
git clone https://github.com/phatle224/reviewlens-data-platform.git
Set-Location reviewlens-data-platform
uv sync --locked --cache-dir .uv-cache
Copy-Item .env.example .env
```

Fill `.env` locally without sharing or committing it. Validate the secret-safe configuration summary:

```powershell
uv run reviewlens-config
```

Generate deterministic synthetic source fixtures:

```powershell
uv run reviewlens-fixtures --output tests/fixtures/synthetic/yelp/v1
```

## Quality checks

```powershell
uv run ruff format --check src tests
uv run ruff check src tests
uv run mypy src tests
uv run pytest --cov=reviewlens --cov-report=term-missing
```

Live tests are opt-in and may only use synthetic payloads. See the active [M1 test matrix](docs/phases/M1/M1_TEST_CASES.md) for exact commands and evidence.

## Project navigation

- [Current status](docs/PROJECT_STATUS.md)
- [Product requirements](docs/PRD.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [M1 checklist](docs/phases/M1/M1_CHECKLIST.md)
- [Architecture decisions](docs/ADR/)

## Attribution

This independent educational portfolio project is not sponsored or endorsed by Yelp. Any local use of the Yelp Open Dataset must follow the applicable Dataset Terms of Use and the project compliance boundary above.
