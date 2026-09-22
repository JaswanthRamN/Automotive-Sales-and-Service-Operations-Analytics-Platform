"""Airflow orchestration for the automotive analytics warehouse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import sys
from typing import Any

from airflow.models import DAG
from airflow.operators.python import PythonOperator
from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from automotive_analytics.etl import (  # noqa: E402
    DATASETS,
    ETLConfig,
    ETLValidationError,
    WAREHOUSE_SOURCE_COUNTS,
    apply_schema,
    load_staging,
    load_warehouse,
    query_counts,
    validate_database_counts,
    validate_processed_files,
)


LOGGER = logging.getLogger(__name__)
DAG_ID = "automotive_sales_service_etl"


def _integer_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _processed_dir() -> Path:
    configured = Path(os.getenv("ETL_PROCESSED_DIR", "data/processed"))
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


def _etl_config() -> ETLConfig:
    configured = Path(os.getenv("AIRFLOW_ENV_FILE", ".env"))
    env_file = configured if configured.is_absolute() else PROJECT_ROOT / configured
    return ETLConfig.from_env(env_file=env_file)


def _extract(**_: Any) -> dict[str, dict[str, int]]:
    """Discover the complete processed-file input set without mutating it."""

    source = _processed_dir()
    manifest: dict[str, dict[str, int]] = {}
    try:
        for dataset in DATASETS:
            path = source / f"{dataset}.csv"
            if not path.is_file():
                raise ETLValidationError(f"Missing processed CSV file: {path}")
            stat = path.stat()
            manifest[dataset] = {
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
            }
        LOGGER.info("Extracted manifest for %d datasets from %s", len(manifest), source)
        return manifest
    except Exception:
        LOGGER.exception("Source extraction failed")
        raise


def _validate(**context: Any) -> dict[str, int]:
    """Validate schema, values, relationships, and a stable extract manifest."""

    try:
        manifest = context["ti"].xcom_pull(task_ids="extract")
        source = _processed_dir()
        for dataset, metadata in manifest.items():
            stat = (source / f"{dataset}.csv").stat()
            if stat.st_size != metadata["size_bytes"] or stat.st_mtime_ns != metadata["modified_ns"]:
                raise ETLValidationError(f"{dataset}.csv changed after extraction")
        counts = validate_processed_files(source)
        LOGGER.info("Validated %,d rows across %d datasets", sum(counts.values()), len(counts))
        return counts
    except Exception:
        LOGGER.exception("Processed-data validation failed")
        raise


def _transform(**_: Any) -> None:
    """Apply schema migrations and replace the PostgreSQL staging layer."""

    config = _etl_config()
    engine = create_engine(config.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    try:
        with engine.begin() as connection:
            apply_schema(connection, PROJECT_ROOT / "sql")
            load_staging(connection, _processed_dir())
        LOGGER.info("Schema and staging transformation committed")
    except Exception:
        LOGGER.exception("Staging transformation failed; transaction rolled back")
        raise
    finally:
        engine.dispose()


def _load(**context: Any) -> dict[str, int]:
    """Build the dimensional warehouse and reconcile source-to-target counts."""

    config = _etl_config()
    source_counts = context["ti"].xcom_pull(task_ids="validate")
    engine = create_engine(config.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    staging_tables = [f"staging.{name}" for name in DATASETS]
    warehouse_tables = [
        "analytics.dim_date",
        "analytics.dim_customer",
        "analytics.dim_vehicle",
        "analytics.dim_dealership",
        "analytics.dim_employee",
        "analytics.dim_service",
        *WAREHOUSE_SOURCE_COUNTS,
    ]
    try:
        with engine.begin() as connection:
            staging_counts = query_counts(connection, staging_tables)
            load_warehouse(connection, PROJECT_ROOT / "sql" / "etl" / "001_load_warehouse.sql")
            warehouse_counts = query_counts(connection, warehouse_tables)
            validate_database_counts(source_counts, staging_counts, warehouse_counts)
        LOGGER.info("Warehouse load committed with %,d rows", sum(warehouse_counts.values()))
        return warehouse_counts
    except Exception:
        LOGGER.exception("Warehouse load failed; transaction rolled back")
        raise
    finally:
        engine.dispose()


def _quality_check(**_: Any) -> None:
    """Fail the run unless every warehouse quality check returns PASS."""

    config = _etl_config()
    engine = create_engine(config.database_url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
    quality_sql = (PROJECT_ROOT / "sql" / "analytics" / "data_quality.sql").read_text(encoding="utf-8")
    try:
        with engine.connect() as connection:
            rows = connection.exec_driver_sql(quality_sql).mappings().all()
        failures = [row for row in rows if row["status"] != "PASS"]
        if failures:
            details = "; ".join(
                f"{row['check_name']}={row['failed_count']}" for row in failures
            )
            raise ETLValidationError(f"Warehouse quality checks failed: {details}")
        LOGGER.info("All %d warehouse quality checks passed", len(rows))
    except Exception:
        LOGGER.exception("Warehouse quality check failed")
        raise
    finally:
        engine.dispose()


def _log_task_failure(context: dict[str, Any]) -> None:
    task = context.get("task_instance")
    LOGGER.error(
        "DAG task failed: dag_id=%s task_id=%s run_id=%s exception=%r",
        context.get("dag").dag_id if context.get("dag") else DAG_ID,
        task.task_id if task else "unknown",
        context.get("run_id", "unknown"),
        context.get("exception"),
    )


default_args = {
    "owner": os.getenv("AIRFLOW_DAG_OWNER", "analytics-engineering"),
    "depends_on_past": False,
    "retries": _integer_env("AIRFLOW_DAG_RETRIES", 2),
    "retry_delay": timedelta(minutes=_integer_env("AIRFLOW_RETRY_DELAY_MINUTES", 5, minimum=1)),
    "on_failure_callback": _log_task_failure,
}

with DAG(
    dag_id=DAG_ID,
    description="Processed CSV to PostgreSQL automotive analytics warehouse",
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    schedule=os.getenv("AIRFLOW_DAG_SCHEDULE", "@daily"),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["automotive", "etl", "postgresql"],
) as dag:
    extract = PythonOperator(task_id="extract", python_callable=_extract)
    validate = PythonOperator(task_id="validate", python_callable=_validate)
    transform = PythonOperator(task_id="transform", python_callable=_transform)
    load = PythonOperator(task_id="load", python_callable=_load)
    quality_check = PythonOperator(task_id="quality_check", python_callable=_quality_check)

    extract >> validate >> transform >> load >> quality_check
