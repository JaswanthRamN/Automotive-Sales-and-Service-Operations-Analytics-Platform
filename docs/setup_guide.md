# Setup and operation

## Prerequisites and configuration

Use Python 3.12, Git, Docker Desktop Linux containers/Compose v2 and Power BI
Desktop for report acceptance. Docker needs hardware virtualization and a
working Windows WSL/virtualization backend. If Docker reports virtualization
support not detected, enable CPU virtualization in BIOS/UEFI with your device's
instructions, configure the supported WSL backend and restart Windows before
retrying. A Compose file cannot resolve missing virtualization.

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Edit the existing .env rather than overwriting it. Replace POSTGRES_PASSWORD,
AIRFLOW_DB_PASSWORD, AIRFLOW_ADMIN_PASSWORD, AIRFLOW_FERNET_KEY and
AIRFLOW_JWT_SECRET. `change_me` is rejected by application configuration.
Use distinct random values. Generate URL-safe hex secrets and a Fernet key:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
.\.venv\Scripts\python.exe -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

POSTGRES_HOST/PORT are host connection coordinates; POSTGRES_PUBLISHED_PORT
controls Docker's exposed port. Match them when using Docker from host scripts.
API_BASE_URL defaults to http://localhost:8000 for runtime verification; adjust
it if API_PORT changes. Airflow metadata uses a separate password/database.
AIRFLOW_DB_PASSWORD must be URL-safe because Compose embeds it in a URL.
Keep .env local; changing its credentials does not update an existing database
volume's stored users/passwords.

## Data and Docker startup

Generate/profile/clean once for a new workspace; these commands replace their
generated outputs, so preserve any customized data first:

```powershell
.\.venv\Scripts\python.exe scripts/generate_data.py --seed 42
.\.venv\Scripts\python.exe scripts/profile_data.py
.\.venv\Scripts\python.exe scripts/clean_data.py
.\.venv\Scripts\python.exe scripts/run_etl.py --validate-only
docker compose config --quiet
docker compose build
docker compose up -d --wait --wait-timeout 300
docker compose ps -a
docker compose logs --tail=100 warehouse-init airflow-init api airflow-scheduler
```

warehouse-init creates tables/views without loading data. Wait for init exit 0,
healthy services and DAG registration. Trigger the DAG and verify success:

```powershell
docker compose exec airflow-dag-processor airflow dags list-import-errors
docker compose exec airflow-scheduler airflow dags list
docker compose exec airflow-scheduler airflow dags trigger automotive_sales_service_etl
docker compose exec airflow-scheduler airflow dags list-runs automotive_sales_service_etl
.\.venv\Scripts\python.exe scripts/check_sql.py
.\.venv\Scripts\python.exe scripts/verify_runtime.py
Invoke-RestMethod http://localhost:8000/health
```

Enable scheduled runs by unpausing in Airflow after verifying a manual run.
Schedule/retries/timeouts use AIRFLOW_* settings in .env.example. Wait for the
run, not just HTTP health, before refreshing Power BI. Do not launch host ETL
concurrently with the DAG.

## Host PostgreSQL alternative

If a local PostgreSQL 16 instance is used, create the configured database/user
outside this project and set .env to it. The user must have DDL/load privileges.
Host ETL applies migrations and loads data; apply views once in dependency order
using a securely configured psql connection:

```powershell
.\.venv\Scripts\python.exe scripts/run_etl.py
psql -v ON_ERROR_STOP=1 -f sql/analytics/sales_analytics.sql
psql -v ON_ERROR_STOP=1 -f sql/analytics/inventory_analytics.sql
psql -v ON_ERROR_STOP=1 -f sql/analytics/service_analytics.sql
psql -v ON_ERROR_STOP=1 -f sql/analytics/customer_analytics.sql
psql -v ON_ERROR_STOP=1 -f sql/analytics/power_bi_views.sql
.\.venv\Scripts\python.exe scripts/check_sql.py
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

psql uses its own PGHOST/PGPORT/PGDATABASE/PGUSER and credential mechanism; it
does not automatically read this project's .env. Schema migration 006 is applied
by ETL/bootstrap along with 001–005. Do not omit it in manual migration tooling.

## Tests, stop and troubleshooting

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=api --cov-report=term-missing --cov-fail-under=80
.\.venv\Scripts\python.exe scripts/validate_powerbi_report.py
.\.venv\Scripts\python.exe scripts/reconcile_kpis.py --postgres
docker compose down
```

See [dashboard guide](dashboard_guide.md) for PBIP generation and refresh. The
--use-existing-snapshot option requires local ignored snapshots and can use
stale data; it does not connect to PostgreSQL. Empty API results before ETL are
normal. A 503 indicates database readiness/connection failure; 422 indicates
invalid inputs. Inspect init/job logs and .env without posting secrets. SQL
check commands exit nonzero on FAIL rows, unlike psql's exit status alone.

`docker compose down -v` permanently deletes project named database/metadata/log
volumes. It is only for an intentional clean reset after backup; it is not part
of this final review. Dependencies/Docker images require network downloads.
Historical successful runs do not override today's unavailable runtime status.
