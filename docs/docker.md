# Local Docker environment

Requires Docker Desktop with Linux containers and Compose v2. Allocate at least
4 GB RAM (8 GB recommended). This stack uses Airflow 3.3.2 because the application's
SQLAlchemy 2 requirement conflicts with Airflow 2. The DAG imports the Airflow 3
SDK and standard operators; the old imports remain as a compatibility fallback.

Copy `.env.example` to `.env` if no local file exists. Replace POSTGRES_PASSWORD
(the application rejects `change_me`) and all Docker secret placeholders.
Generate AIRFLOW_DB_PASSWORD and AIRFLOW_JWT_SECRET with
`python -c "import secrets; print(secrets.token_hex(32))"`.
AIRFLOW_DB_PASSWORD must be URL-safe because it is embedded in a database URL.
Generate AIRFLOW_FERNET_KEY with
`python -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`.
Set a separate AIRFLOW_ADMIN_PASSWORD. Do not commit `.env`.

From the repository root:

```sh
docker compose config --quiet
docker compose build
docker compose up -d --wait --wait-timeout 300
docker compose ps
docker compose logs --tail=100 warehouse-init airflow-init api airflow-scheduler
```

FastAPI: http://localhost:8000/docs; readiness: http://localhost:8000/health.
Airflow: http://localhost:8080 using AIRFLOW_ADMIN_USER/AIRFLOW_ADMIN_PASSWORD.
Host ports can be changed in `.env`; containers always connect to PostgreSQL at
`postgres:5432`, regardless of host POSTGRES_HOST/POSTGRES_PORT values.

The warehouse and Airflow metadata have separate PostgreSQL instances and named
volumes. Airflow uses LocalExecutor with separate API server, scheduler, and DAG
processor services. Named logs survive container recreation. Processed CSVs are
mounted read-only from `data/processed`; no credentials or datasets enter images.
Project code is baked into images, so rebuild after code changes.

warehouse-init applies schema migrations and analytics views transactionally;
it does not load or truncate datasets. Existing migrations may repair return unit
signs. API requests initially return empty results. Airflow DAGs start paused;
after supplying the eight processed CSV files, unpause/trigger the DAG in the UI.
Initialization jobs must finish successfully before dependent services start.
Long-running services each have a health check and restart policy.

```sh
docker compose exec airflow-dag-processor airflow dags list-import-errors
docker compose exec airflow-scheduler airflow dags list
docker compose down
```

`down` preserves the database and log volumes. Do not use `down -v` unless you
intend to permanently delete those volumes. Changing database credentials in
`.env` does not change credentials in an already initialized PostgreSQL volume.

## Clean-environment verification

The following deliberately deletes this project's PostgreSQL, Airflow metadata,
and log volumes. Raw and processed CSV files on the host are preserved.

```sh
docker compose down -v
docker compose up --build -d
docker compose ps -a
docker compose exec airflow-dag-processor airflow dags list-import-errors
docker compose exec airflow-scheduler airflow dags list
```

Wait until `automotive_sales_service_etl` appears in the DAG list before
unpausing it; service health does not guarantee initial DAG registration is
finished. Then trigger a run (use a distinct run ID for each manual invocation):

```sh
docker compose exec airflow-scheduler airflow dags unpause automotive_sales_service_etl
docker compose exec airflow-scheduler airflow dags trigger --run-id clean_environment_verification automotive_sales_service_etl
docker compose exec airflow-scheduler airflow dags list-runs automotive_sales_service_etl
```

Wait for a successful run, including `quality_check` and `reporting_ready`.
Unpausing also permits the configured daily schedule; `max_active_runs=1`
serializes scheduled and manual runs. Run the read-only integration verifier
from the host's activated Python environment:

```sh
python scripts/verify_runtime.py
python -m pytest --cov=api --cov=src --cov-report=term
```

The verifier compares processed CSV counts with staging and warehouse counts,
requires every SQL quality check to PASS, checks all paginated API routes and
OpenAPI, exercises filters/pagination/422 responses/empty results, and compares
API sales and service totals with PostgreSQL. Configure `API_BASE_URL` when
using a non-default API port and match host PostgreSQL settings in `.env` to
the published database port. The verifier has a bounded database connection
timeout and fails with a nonzero exit code on a mismatch.

Verified on Windows with Docker's Linux engine on September 30, 2026: clean
build/start succeeded, initialization jobs exited 0, all six long-running
services were healthy, no DAG import errors occurred, and manual and scheduled
ETL runs succeeded. All 28 SQL quality checks passed for 84,668 processed rows
across eight datasets. The warehouse contains 15,500 sales facts, 4,500 inventory
facts and 15,500 service facts. Integer conversions accept whole-valued decimal
CSV text (such as `0.0`); preflight rejects fractional/overflow values before
loading to prevent SQL rounding or truncation.

Final host pytest result: 121 passed, one skipped, with 83.97% combined API/src
coverage. The skipped test requires a local Airflow installation; the actual
container DAG import and complete task execution were verified separately.
