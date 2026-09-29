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

Verification on the current Windows host: Docker is absent, so build/start and
container health checks could not run. Local pytest checks validate the Compose
structure and bootstrap behavior; they do not establish image build or runtime
success. Run the commands above once Docker Desktop is installed and running.
