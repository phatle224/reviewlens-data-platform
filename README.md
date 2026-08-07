# ReviewLens Data Platform

ReviewLens is an Olist-powered portfolio data platform for e-commerce review and delivery intelligence. The target architecture uses Cloudflare R2, Snowflake, dbt, Airflow, OpenRouter, ChromaDB and Streamlit while keeping provider access behind typed Python adapters.

The project is currently in **M1 — Foundation**. It runs as one local demo environment; no staging, production or public URL is provisioned.

## Data and security boundary

- The primary source is the Olist Brazilian E-Commerce Public Dataset: nine relational CSV files under CC BY-NC-SA 4.0.
- Olist CSVs, review text, embeddings and row-level derived artifacts are never committed or published. Local raw files belong in an ignored source directory such as `archive/`.
- R2 and Snowflake may process the private Olist snapshot after source-manifest and privacy gates pass. External AI still requires a minimized, approved review projection; CI and public portfolio evidence use synthetic fixtures only.
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
uv run reviewlens-fixtures --output tests/fixtures/synthetic/olist/v1
```

Start the authenticated loopback-only foundation shell:

```powershell
uv run reviewlens-app
```

Open `http://127.0.0.1:8501` and enter the local `APP_AUTH_TOKEN`. The M1 page
shows configuration readiness only; it does not call managed providers or expose
Olist rows. Stop it with `Ctrl+C`.

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
- [Dataset attribution and obligations](docs/DATA_ATTRIBUTION.md)
- [Olist source manifest](docs/data/OLIST_SOURCE_MANIFEST.md)

## Attribution

This independent, non-commercial educational portfolio project uses the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). Olist does not sponsor or endorse this project. See [DATA_ATTRIBUTION.md](docs/DATA_ATTRIBUTION.md) for the complete notice.
