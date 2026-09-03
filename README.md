# Automotive Sales & Service Operations Analytics Platform

A portfolio-ready analytics platform for automotive sales and service operations. The planned stack includes Python, Pandas, PostgreSQL, SQL, Power BI, DAX, Power Query, Airflow, FastAPI, Docker, and Git/GitHub.

## Current status

Day 1 establishes the repository structure and development tooling only. ETL pipelines, database objects, APIs, Airflow DAGs, Docker services, and Power BI assets are intentionally deferred to later project days.

## Project structure

```text
.
|-- airflow/             # Future Airflow configuration and DAG support
|-- api/                 # Future FastAPI application
|-- config/              # Future application configuration
|-- dashboards/          # Future Power BI documentation and assets
|-- data/
|   |-- output/          # Generated exports
|   |-- processed/       # Processed datasets
|   `-- raw/             # Source datasets
|-- docker/              # Future container configuration
|-- docs/                # Project documentation
|-- notebooks/           # Exploratory analysis
|-- scripts/             # Future utility and execution scripts
|-- sql/                 # Future SQL definitions and queries
|-- src/
|   `-- automotive_analytics/
|-- tests/               # Automated tests
|-- .env.example
|-- .gitignore
|-- Makefile
|-- pytest.ini
|-- README.md
`-- requirements.txt
```

## Local setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and replace placeholder values when later development requires them.
4. Run the test suite:

   ```bash
   python -m pytest
   ```

Alternatively, on systems with `make`, use `make install` and `make test`.

## Synthetic raw data

Generate the reproducible development datasets with the default seed (`42`):

```bash
python scripts/generate_data.py
```

Use `--seed <number>` to create a different deterministic dataset. Generated CSV files are written to `data/raw/` and are intentionally ignored by Git.

## Raw data profiling

Profile and validate every CSV in `data/raw/`:

```bash
python scripts/profile_data.py
```

The command checks dataset and column statistics, nulls, duplicate rows and keys, unique values, numeric and date ranges, invalid domain and calculated values, date ordering, and foreign-key integrity. It writes CSV, JSON, and Markdown reports to `data/processed/profiling/`. A failing validation returns a nonzero exit code.

## Development guardrails

- Never commit `.env`, credentials, raw operational data, generated output, or local Power BI files.
- Keep business logic inside the `automotive_analytics` package and cover it with tests.
- Implement each project day only after inspecting and testing the existing repository.
