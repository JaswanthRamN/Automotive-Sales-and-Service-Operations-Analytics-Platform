"""Transactional PostgreSQL ETL from cleaned CSVs to the analytics warehouse."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from automotive_analytics.data_profiler import (
    build_foreign_key_report,
    build_validation_report,
    load_datasets,
)


DATASETS = (
    "customers",
    "vehicles",
    "dealerships",
    "employees",
    "sales",
    "inventory",
    "service_appointments",
    "service_orders",
)

STAGING_COLUMNS = {
    "customers": ["customer_id", "first_name", "last_name", "email", "phone", "city", "state", "postal_code", "customer_since_date", "customer_type"],
    "vehicles": ["vehicle_id", "vin", "make", "model", "model_year", "body_type", "fuel_type", "color", "vehicle_condition", "mileage_at_acquisition", "manufacturer_msrp"],
    "dealerships": ["dealership_id", "dealership_name", "city", "state", "postal_code", "region", "opened_date"],
    "employees": ["employee_id", "dealership_id", "first_name", "last_name", "role", "hire_date", "employment_status"],
    "sales": ["sale_id", "sale_date", "customer_id", "vehicle_id", "dealership_id", "salesperson_id", "sales_channel", "list_price", "discount_amount", "sale_price", "vehicle_cost", "gross_profit", "payment_type", "sale_status"],
    "inventory": ["inventory_id", "snapshot_date", "vehicle_id", "dealership_id", "acquired_date", "inventory_status", "carrying_cost", "days_in_inventory", "slow_moving_flag"],
    "service_appointments": ["appointment_id", "customer_id", "vehicle_id", "dealership_id", "service_advisor_id", "appointment_date", "appointment_time", "service_type", "appointment_status"],
    "service_orders": ["service_order_id", "appointment_id", "customer_id", "vehicle_id", "dealership_id", "service_advisor_id", "technician_id", "opened_at", "promised_at", "completed_at", "order_status", "payer_type", "labor_revenue", "parts_revenue", "discount_amount", "service_revenue"],
}

WAREHOUSE_SOURCE_COUNTS = {
    "analytics.dim_customer": "customers",
    "analytics.dim_vehicle": "vehicles",
    "analytics.dim_dealership": "dealerships",
    "analytics.dim_employee": "employees",
    "analytics.fact_sales": "sales",
    "analytics.fact_inventory": "inventory",
    "analytics.fact_service": "service_orders",
}


class ETLError(RuntimeError):
    """Base exception for actionable ETL failures."""


class ETLConfigError(ETLError):
    """Raised when required environment configuration is absent or unsafe."""


class ETLValidationError(ETLError):
    """Raised when source or warehouse validation fails."""


@dataclass(frozen=True)
class ETLConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str = "prefer"
    processed_dir: Path = Path("data/processed")
    log_path: Path = Path("logs/etl.log")

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
            query={"sslmode": self.sslmode},
        )

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: str | Path | None = ".env",
    ) -> "ETLConfig":
        if env_file:
            load_dotenv(Path(env_file), override=False)
        values = env if env is not None else os.environ
        required = ["POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise ETLConfigError(f"Missing required environment variables: {', '.join(missing)}")
        password = values["POSTGRES_PASSWORD"]
        if password == "change_me":
            raise ETLConfigError("POSTGRES_PASSWORD still contains the .env.example placeholder")
        try:
            port = int(values["POSTGRES_PORT"])
        except ValueError as exc:
            raise ETLConfigError("POSTGRES_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ETLConfigError("POSTGRES_PORT must be between 1 and 65535")
        return cls(
            host=values["POSTGRES_HOST"],
            port=port,
            database=values["POSTGRES_DB"],
            user=values["POSTGRES_USER"],
            password=password,
            sslmode=values.get("POSTGRES_SSLMODE", "prefer"),
            processed_dir=Path(values.get("ETL_PROCESSED_DIR", "data/processed")),
            log_path=Path(values.get("ETL_LOG_PATH", "logs/etl.log")),
        )


@dataclass(frozen=True)
class ETLResult:
    source_counts: dict[str, int]
    staging_counts: dict[str, int]
    warehouse_counts: dict[str, int]


def configure_logging(path: Path) -> logging.Logger:
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("automotive_analytics.etl")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def validate_processed_files(processed_dir: str | Path) -> dict[str, int]:
    """Validate all expected cleaned CSVs before opening a database transaction."""

    source = Path(processed_dir)
    missing = [name for name in DATASETS if not (source / f"{name}.csv").is_file()]
    if missing:
        raise ETLValidationError(f"Missing processed CSV files: {', '.join(missing)}")
    datasets = {name: pd.read_csv(source / f"{name}.csv", low_memory=False) for name in DATASETS}
    for name, columns in STAGING_COLUMNS.items():
        actual = list(datasets[name].columns)
        if actual != columns:
            raise ETLValidationError(
                f"{name}.csv columns do not match the staging contract; expected {columns}, got {actual}"
            )
    validation = build_validation_report(datasets)
    failures = validation[(validation["severity"] == "ERROR") & (validation["status"] == "FAIL")]
    foreign_keys = build_foreign_key_report(datasets)
    fk_failures = foreign_keys[foreign_keys["status"] != "PASS"]
    if not failures.empty or not fk_failures.empty:
        raise ETLValidationError(
            f"Processed data failed preflight: {len(failures)} validation checks and "
            f"{len(fk_failures)} foreign-key checks failed"
        )
    counts = {name: len(frame) for name, frame in datasets.items()}
    if any(count == 0 for count in counts.values()):
        empty = [name for name, count in counts.items() if count == 0]
        raise ETLValidationError(f"Processed datasets are empty: {', '.join(empty)}")
    return counts


def split_sql_statements(sql: str) -> list[str]:
    """Split this project's SQL files into executable statements."""

    statements = []
    for chunk in sql.split(";"):
        statement = chunk.strip()
        if not statement or statement.upper() in {"BEGIN", "COMMIT"}:
            continue
        statements.append(statement)
    return statements


def execute_sql_file(connection: Connection, path: Path) -> None:
    for statement in split_sql_statements(path.read_text(encoding="utf-8")):
        connection.exec_driver_sql(statement)


def apply_schema(connection: Connection, sql_dir: Path) -> None:
    for path in sorted(sql_dir.glob("[0-9][0-9][0-5]_*.sql")):
        execute_sql_file(connection, path)


def _copy_csv(connection: Connection, dataset: str, csv_path: Path) -> None:
    columns = STAGING_COLUMNS[dataset]
    column_sql = ", ".join(columns)
    copy_sql = (
        f"COPY staging.{dataset} ({column_sql}) "
        "FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')"
    )
    dbapi_connection = connection.connection.driver_connection
    with dbapi_connection.cursor() as cursor, cursor.copy(copy_sql) as copy:
        with csv_path.open("r", encoding="utf-8", newline="") as source:
            while chunk := source.read(1024 * 1024):
                copy.write(chunk)


def load_staging(connection: Connection, processed_dir: Path) -> None:
    table_list = ", ".join(f"staging.{name}" for name in DATASETS)
    connection.exec_driver_sql(f"TRUNCATE TABLE {table_list}")
    for dataset in DATASETS:
        _copy_csv(connection, dataset, processed_dir / f"{dataset}.csv")


def load_warehouse(connection: Connection, transform_sql: Path) -> None:
    execute_sql_file(connection, transform_sql)


def query_counts(connection: Connection, tables: Sequence[str]) -> dict[str, int]:
    return {
        table: int(connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
        for table in tables
    }


def validate_database_counts(
    source_counts: Mapping[str, int],
    staging_counts: Mapping[str, int],
    warehouse_counts: Mapping[str, int],
) -> None:
    mismatches = []
    for dataset, expected in source_counts.items():
        actual = staging_counts.get(f"staging.{dataset}")
        if actual != expected:
            mismatches.append(f"staging.{dataset}: expected {expected}, got {actual}")
    for table, dataset in WAREHOUSE_SOURCE_COUNTS.items():
        expected = source_counts[dataset]
        actual = warehouse_counts.get(table)
        if actual != expected:
            mismatches.append(f"{table}: expected {expected}, got {actual}")
    if not warehouse_counts.get("analytics.dim_date", 0):
        mismatches.append("analytics.dim_date is empty")
    if not warehouse_counts.get("analytics.dim_service", 0):
        mismatches.append("analytics.dim_service is empty")
    if mismatches:
        raise ETLValidationError("Row-count validation failed: " + "; ".join(mismatches))


def run_etl(
    config: ETLConfig,
    project_root: str | Path | None = None,
    engine: Engine | None = None,
) -> ETLResult:
    """Run a full-refresh ETL in one data transaction."""

    root = Path(project_root) if project_root else Path(__file__).resolve().parents[2]
    processed_dir = config.processed_dir if config.processed_dir.is_absolute() else root / config.processed_dir
    logger = configure_logging(config.log_path if config.log_path.is_absolute() else root / config.log_path)
    source_counts = validate_processed_files(processed_dir)
    logger.info("Preflight passed for %s source rows", sum(source_counts.values()))
    database_engine = engine or create_engine(
        config.database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    owns_engine = engine is None
    staging_tables = [f"staging.{name}" for name in DATASETS]
    warehouse_tables = [
        "analytics.dim_date",
        "analytics.dim_customer",
        "analytics.dim_vehicle",
        "analytics.dim_dealership",
        "analytics.dim_employee",
        "analytics.dim_service",
        "analytics.fact_sales",
        "analytics.fact_inventory",
        "analytics.fact_service",
    ]
    try:
        with database_engine.begin() as connection:
            apply_schema(connection, root / "sql")
        logger.info("Schema DDL applied successfully")
        with database_engine.begin() as connection:
            load_staging(connection, processed_dir)
            staging_counts = query_counts(connection, staging_tables)
            load_warehouse(connection, root / "sql" / "etl" / "001_load_warehouse.sql")
            warehouse_counts = query_counts(connection, warehouse_tables)
            validate_database_counts(source_counts, staging_counts, warehouse_counts)
        logger.info("ETL committed successfully: %s warehouse rows", sum(warehouse_counts.values()))
        return ETLResult(dict(source_counts), staging_counts, warehouse_counts)
    except (SQLAlchemyError, OSError, ETLError) as exc:
        logger.exception("ETL failed and the active transaction was rolled back")
        if isinstance(exc, ETLError):
            raise
        raise ETLError(f"ETL execution failed: {exc}") from exc
    finally:
        if owns_engine:
            database_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        processed_dir = Path(os.getenv("ETL_PROCESSED_DIR", "data/processed"))
        counts = validate_processed_files(processed_dir)
        print(f"Preflight status: PASS ({sum(counts.values()):,} rows across {len(counts)} datasets)")
        return
    try:
        config = ETLConfig.from_env(env_file=args.env_file)
        result = run_etl(config)
    except ETLError as exc:
        print(f"ETL status: FAIL - {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("ETL status: PASS")
    for table, count in result.warehouse_counts.items():
        print(f"{table}: {count:,}")


if __name__ == "__main__":
    main()
