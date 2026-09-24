# Automotive Sales & Service Operations Analytics Platform

A portfolio-ready analytics platform for automotive sales and service operations. The planned stack includes Python, Pandas, PostgreSQL, SQL, Power BI, DAX, Power Query, Airflow, FastAPI, Docker, and Git/GitHub.

## Current status

Day 1 establishes the repository structure and development tooling only. ETL pipelines, database objects, APIs, Airflow DAGs, Docker services, and Power BI assets are intentionally deferred to later project days.

## Project structure

```text
.
|-- airflow/             # Airflow DAGs and local runtime home
|-- api/                 # Read-only FastAPI analytics application
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

## Data cleaning

Clean all raw CSV datasets with deterministic Pandas pipelines:

```bash
python scripts/clean_data.py
```

The pipeline standardizes strings and categories, coerces data types, removes duplicates and unusable values, recalculates derived fields, enforces date rules, repairs service-order attributes from appointments, and removes broken relationships. Clean CSVs and `cleaning_summary.csv` are written to `data/processed/`; execution details are written to `logs/data_cleaning.log`. Raw files are never modified.

## PostgreSQL schema DDL

The ordered scripts in `sql/` define the `staging` and `analytics` schemas, eight text-based landing tables, six conformed dimensions, and the `fact_sales`, `fact_inventory`, and `fact_service` star-schema facts. Run them in numeric filename order when a PostgreSQL environment is available:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/001_create_schemas.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/002_create_staging_tables.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/003_create_dimensions.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/004_create_facts.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/005_create_indexes.sql
```

The schema includes surrogate and natural-key constraints, foreign keys, measure and domain checks, slowly changing dimension fields, generated service metrics, and indexes for common dashboard filters. These scripts define structures only; they do not load data.

## PostgreSQL ETL

Copy `.env.example` to `.env`, replace the PostgreSQL placeholder credentials, create the configured empty database, and run:

```bash
python scripts/run_etl.py
```

The ETL validates all eight processed CSV contracts with Pandas, creates missing schemas and tables, uses psycopg `COPY` to replace staging data, and rebuilds the dimensional warehouse within transactions. Row counts are verified before commit; failures roll back the active transaction and are logged to `logs/etl.log`. Full-refresh staging and warehouse steps make repeated runs deterministic.

Run source preflight without connecting to PostgreSQL:

```bash
python scripts/run_etl.py --validate-only
```

## Warehouse data quality

After a successful ETL run, execute the read-only analytics checks:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/data_quality.sql
```

The query returns one row per duplicate, duplicate-fact, missing-key, orphan, date, price, or negative-revenue check. Each row includes a `PASS`/`FAIL` status, failed-row count, and remediation detail; the warehouse passes only when every result is `PASS`.

## Airflow orchestration

The `automotive_sales_service_etl` DAG runs the ordered workflow `extract → validate → transform → load → quality_check → reporting_ready`. It fingerprints the processed CSV inputs, validates their contracts and relationships, refreshes PostgreSQL staging idempotently, transactionally rebuilds the warehouse, reconciles row counts, and fails unless every warehouse quality check passes. The all-success `reporting_ready` marker cannot run after a failed quality gate.

Configure PostgreSQL and the `AIRFLOW_*` values from `.env.example`, then place or symlink `airflow/dags/automotive_etl_dag.py` in the scheduler DAG folder. Retries, bounded exponential retry delays, task and quality-check timeouts, owner, schedule, source location, credentials, SSL mode, and environment-file location are controlled through environment variables. Task failures and retries are logged with DAG, task, run, attempt, and exception context.

## FastAPI analytics service

Configure PostgreSQL and the `API_*` connection-pool settings from `.env.example`, then start the read-only API from the repository root:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

The service exposes `/health`, `/sales`, `/inventory`, `/service`, `/customers`, and `/dealerships`. Analytics endpoints read only from the curated PostgreSQL views, use bounded `limit`/`offset` pagination, and return documented Pydantic contracts. Swagger UI is available at `/docs`, ReDoc at `/redoc`, and the OpenAPI document at `/openapi.json`. Database failures return a sanitized `503` response and are logged without exposing credentials.

## Sales analytics SQL

Create the sales analytics views after the warehouse is loaded:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/sales_analytics.sql
```

The views expose units sold, revenue, gross profit, gross margin, average selling price, monthly performance, brand/model, salesperson, dealership, vehicle type, and payment-method analysis. Every aggregate reads from a canonical one-row-per-sale view, signs returns with `unit_quantity`, and excludes cancelled sales.

Validate all totals and duplicate-count safeguards:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/sales_analytics_validation.sql
```

Every validation result must return `PASS` before the views are published to downstream reporting.

## Inventory analytics SQL

Create the snapshot-aware inventory analytics views after the warehouse is loaded:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/inventory_analytics.sql
```

The views expose inventory units and value, days in inventory, weighted average age, aging buckets, brand/model inventory, dealership inventory, and vehicle-level slow-moving stock. Buckets are `0-30`, `31-60`, `61-90`, `91-120`, and `120+`; to avoid overlap, day 120 belongs to `91-120` and `120+` means more than 120 days. Slow-moving inventory is strictly more than 90 days. Every aggregate retains its snapshot date.

Validate snapshot-level totals and grain safeguards:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/inventory_analytics_validation.sql
```

Every validation result must return `PASS` before inventory views are published.

## Service analytics SQL

Create the appointment and service analytics views after the ETL has loaded staging and warehouse tables:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/service_analytics.sql
```

The views expose appointments, completions, cancellations, no-shows, completion rate, service revenue, average repair order, monthly revenue, and performance by service type, technician, and dealership. The canonical view has one row per appointment and joins the unique repair order by `appointment_id`, preventing duplicated service revenue. Completion rate uses completed, cancelled, and no-show appointments as its denominator; scheduled appointments are excluded.

The source model does not currently contain authoritative service cost. Consequently, `service_cost` and `service_profit` are deliberately `NULL`, and `service_cost_available` is false rather than using invented margin assumptions.

Validate appointment counts and revenue reconciliation:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/service_analytics_validation.sql
```

Every validation result must return `PASS` before service views are published.

## Customer analytics SQL

Create customer analytics after the warehouse facts are loaded:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/customer_analytics.sql
```

The customer views aggregate sales and service independently before joining them to one current customer row, preventing cross-product revenue duplication. They expose total, new, repeat, inactive, sales-only, service-only, and sales-plus-service customers; repeat rate; customer revenue; service frequency; and customer lifetime value. New customers have exactly one lifetime qualifying interaction, repeat customers have two or more, and inactive customers have prior activity but none within 365 days of the latest warehouse activity.

Because authoritative service cost is unavailable, customer lifetime value is explicitly labeled as interim revenue-based CLV (`sales revenue + service revenue`) rather than mixing sales profit with service revenue.

Validate customer counts, revenue, segments, and frequency totals:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/customer_analytics_validation.sql
```

Every validation result must return `PASS` before customer views are published.

## Power BI PostgreSQL views

After creating all domain analytics views, create the curated Power BI layer:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/power_bi_views.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/analytics/power_bi_views_validation.sql
```

The layer provides `vw_sales_performance`, `vw_inventory_aging`, `vw_service_performance`, `vw_customer_value`, and a cross-domain `vw_dealership_performance`. Detail views preserve canonical grains, while the dealership scorecard aggregates each subject before joining to prevent duplicated measures. See `docs/power_bi_views.md` for grains, modeling guidance, privacy decisions, and refresh validation requirements.

## Development guardrails

- Never commit `.env`, credentials, raw operational data, generated output, or local Power BI files.
- Keep business logic inside the `automotive_analytics` package and cover it with tests.
- Implement each project day only after inspecting and testing the existing repository.
