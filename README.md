# Automotive Sales & Service Operations Analytics Platform

A reproducible automotive analytics portfolio project: synthetic relational data,
Pandas profiling and cleaning, PostgreSQL dimensional storage, Airflow ETL,
read-only FastAPI endpoints and a three-page Power BI report project.

Stack: Python 3.12, Pandas, Faker, PostgreSQL 16, SQLAlchemy, psycopg, FastAPI,
Airflow 3.3.2, Docker Compose, Power BI, DAX, Power Query and pytest.
Data is synthetic; this project does not claim a production deployment or real
business savings.

## Current acceptance status

Final review: October 9, 2026. See [the validation record](docs/final_review.md).
Docker configuration validates. Live Docker/PostgreSQL/API and actual Power BI
DAX execution must pass on a running environment before end-to-end acceptance.
[KPI reconciliation](docs/kpi_reconciliation.md) distinguishes snapshot results,
historical PostgreSQL evidence and current runtime limitations.

Implemented: eight related datasets; profiling/cleaning; six dimensions and three
facts with constraints/indexes; domain analytics; 14 API GET routes; a retryable
quality-gated DAG; isolated application/metadata databases; Executive Overview,
Sales & Inventory and Service & Customer pages with vehicle/model drill-through.
Dimensions/facts reside in `analytics`; `staging` holds landing data. There is
no separately populated `warehouse` schema in the checked-in DDL.

## Quick start (PowerShell)

Run from the repository root with Docker Desktop's Linux engine running.
Hardware virtualization and Windows WSL prerequisites must be ready.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env and replace database/Airflow secret placeholders.
.\.venv\Scripts\python.exe scripts/generate_data.py --seed 42
.\.venv\Scripts\python.exe scripts/profile_data.py
.\.venv\Scripts\python.exe scripts/clean_data.py
.\.venv\Scripts\python.exe scripts/run_etl.py --validate-only
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 300
docker compose ps -a
```

Initialization creates empty schemas/views. Trigger the DAG after registration
and wait for all tasks to succeed:

```powershell
docker compose exec airflow-dag-processor airflow dags list-import-errors
docker compose exec airflow-scheduler airflow dags list
docker compose exec airflow-scheduler airflow dags trigger automotive_sales_service_etl
docker compose exec airflow-scheduler airflow dags list-runs automotive_sales_service_etl
.\.venv\Scripts\python.exe scripts/verify_runtime.py
.\.venv\Scripts\python.exe scripts/check_sql.py
```

Manual triggers can run paused DAGs; unpause in Airflow when daily scheduling is
desired. Open API Swagger at http://localhost:8000/docs and Airflow at
http://localhost:8080. [Setup](docs/setup_guide.md) covers configuration and host
ETL. `docker compose down` preserves volumes; `down -v` deletes database,
metadata and log volumes and is not a routine stop.

## Tests and reconciliation

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=api --cov-report=term-missing --cov-fail-under=80
.\.venv\Scripts\python.exe scripts/check_sql.py
.\.venv\Scripts\python.exe scripts/verify_runtime.py
.\.venv\Scripts\python.exe scripts/validate_powerbi_report.py
.\.venv\Scripts\python.exe scripts/reconcile_kpis.py
.\.venv\Scripts\python.exe scripts/reconcile_kpis.py --postgres
```

pytest covers data processing, ETL, SQL contracts, DAG behavior, API schemas,
errors/filters/pagination, Docker structure and report/model definitions. The
host Airflow import test skips without Airflow. SQL fixtures and API mocks do
not replace live SQL/API and container checks. Report schema validation needs
Microsoft network access; snapshot reconciliation needs ignored local imports.

## Project structure

```text
.
|-- .github/workflows/ci.yml       # Python/API coverage and Docker static checks
|-- api/                          # main.py, models.py, database.py
|-- airflow/dags/automotive_etl_dag.py
|-- data/{raw,processed,output}/   # Generated/ignored data
|-- docker/                       # Images, bootstrap, app dependencies
|-- docs/                         # Architecture, setup, API, dictionary,
|                                 # dashboard, reconciliation, final review
|-- powerbi/
|   |-- ExecutiveOverview/        # PBIP, PBIR definitions, semantic model
|   |-- dax/measures.dax
|   `-- documentation/            # Star schema, Power Query, SQL references
|-- scripts/                      # Data, ETL, verification and reconciliation
|-- sql/
|   |-- 001...006_*.sql           # Ordered schema/migrations
|   |-- etl/001_load_warehouse.sql
|   `-- analytics/                # Domain/reporting views and checks
|-- src/automotive_analytics/      # Generator, profiler, cleaner, ETL
|-- tests/
|-- config/, dashboards/, notebooks/  # Reserved scaffolding
|-- .env.example, .gitignore, .dockerignore
`-- docker-compose.yml, requirements.txt, Makefile, pytest.ini
```

## Documentation

- [Business requirements](docs/business_requirements.md)
- [Architecture](docs/architecture.md)
- [Data dictionary](docs/data_dictionary.md)
- [Setup guide](docs/setup_guide.md) and [Docker details](docs/docker.md)
- [API reference](docs/api_documentation.md)
- [Dashboard guide](docs/dashboard_guide.md)
- [Power BI model](powerbi/documentation/README.md)
- [KPI reconciliation](docs/kpi_reconciliation.md)
- [Final review, GitHub description and resume bullets](docs/final_review.md)

## Metric and security boundaries

Returns reverse sales units/revenue/profit; cancelled sales are excluded. Stock
uses one as-of snapshot; slow-moving means >90 days. Power BI service finances
use completed orders and completion dates; API service routes use appointment
cohorts. API percent fields are 0–100; DAX ratios are 0–1. Registered Customers
and active customers differ. CLV is historical revenue, not a forecast; service
cost/profit stay null because inputs have no authoritative costs.

ETL is a full refresh that resets surrogate keys: import the whole Power BI model
after stable ETL, never concurrently. The API has no authentication and Compose
binds it to loopback; public deployment needs access controls and a read-only DB
role. Customer contact fields are excluded from the report import.

`.env`, logs, data, virtual environments and PBIX files remain local. Credentials
and local snapshots must not be published. This review prepares a local commit;
no GitHub push or publication is performed.
