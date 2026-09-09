from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from automotive_analytics.data_generator import GeneratorConfig, write_datasets
from automotive_analytics.etl import (
    DATASETS,
    ETLConfig,
    ETLConfigError,
    ETLValidationError,
    WAREHOUSE_SOURCE_COUNTS,
    split_sql_statements,
    validate_database_counts,
    validate_processed_files,
)


CONFIG = GeneratorConfig(
    seed=47,
    customers=40,
    vehicles=80,
    dealerships=2,
    employees=20,
    sales=50,
    inventory=30,
    service_appointments=60,
    service_orders=50,
)


def test_config_builds_encoded_psycopg_url() -> None:
    config = ETLConfig.from_env(
        {
            "POSTGRES_HOST": "db.internal",
            "POSTGRES_PORT": "5433",
            "POSTGRES_DB": "automotive",
            "POSTGRES_USER": "etl_user",
            "POSTGRES_PASSWORD": "p@ss:/word",
            "POSTGRES_SSLMODE": "require",
            "ETL_PROCESSED_DIR": "custom/processed",
            "ETL_LOG_PATH": "custom/etl.log",
        },
        env_file=None,
    )

    assert config.port == 5433
    assert config.database_url.drivername == "postgresql+psycopg"
    assert config.database_url.render_as_string(hide_password=False).startswith(
        "postgresql+psycopg://etl_user:p%40ss%3A%2Fword@db.internal:5433/automotive"
    )


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"POSTGRES_PASSWORD": ""}, "Missing required"),
        ({"POSTGRES_PASSWORD": "change_me"}, "placeholder"),
        ({"POSTGRES_PORT": "invalid"}, "integer"),
    ],
)
def test_config_rejects_invalid_values(overrides: dict[str, str], message: str) -> None:
    values = {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "automotive",
        "POSTGRES_USER": "etl_user",
        "POSTGRES_PASSWORD": "secret",
    }
    values.update(overrides)
    with pytest.raises(ETLConfigError, match=message):
        ETLConfig.from_env(values, env_file=None)


def test_processed_file_preflight_passes_valid_files(tmp_path: Path) -> None:
    write_datasets(tmp_path, CONFIG)

    counts = validate_processed_files(tmp_path)

    assert set(counts) == set(DATASETS)
    assert sum(counts.values()) == 332


def test_processed_file_preflight_rejects_schema_drift(tmp_path: Path) -> None:
    write_datasets(tmp_path, CONFIG)
    sales_path = tmp_path / "sales.csv"
    sales = pd.read_csv(sales_path).drop(columns=["gross_profit"])
    sales.to_csv(sales_path, index=False)

    with pytest.raises(ETLValidationError, match="staging contract"):
        validate_processed_files(tmp_path)


def test_processed_file_preflight_rejects_missing_dataset(tmp_path: Path) -> None:
    write_datasets(tmp_path, CONFIG)
    (tmp_path / "sales.csv").unlink()

    with pytest.raises(ETLValidationError, match="Missing processed CSV files: sales"):
        validate_processed_files(tmp_path)


def test_sql_splitter_omits_transaction_wrappers() -> None:
    sql = "BEGIN; CREATE SCHEMA IF NOT EXISTS staging; CREATE TABLE staging.x (id INT); COMMIT;"

    assert split_sql_statements(sql) == [
        "CREATE SCHEMA IF NOT EXISTS staging",
        "CREATE TABLE staging.x (id INT)",
    ]


def test_count_validation_accepts_matching_counts() -> None:
    source = {name: 10 for name in DATASETS}
    staging = {f"staging.{name}": 10 for name in DATASETS}
    warehouse = {table: 10 for table in WAREHOUSE_SOURCE_COUNTS}
    warehouse["analytics.dim_date"] = 100
    warehouse["analytics.dim_service"] = 5

    validate_database_counts(source, staging, warehouse)


def test_count_validation_rejects_mismatch() -> None:
    source = {name: 10 for name in DATASETS}
    staging = {f"staging.{name}": 10 for name in DATASETS}
    warehouse = {table: 10 for table in WAREHOUSE_SOURCE_COUNTS}
    warehouse["analytics.dim_date"] = 100
    warehouse["analytics.dim_service"] = 5
    warehouse["analytics.fact_sales"] = 9

    with pytest.raises(ETLValidationError, match="fact_sales: expected 10, got 9"):
        validate_database_counts(source, staging, warehouse)


def test_warehouse_transform_is_full_refresh_and_loads_all_targets() -> None:
    sql = (PROJECT_ROOT / "sql" / "etl" / "001_load_warehouse.sql").read_text(encoding="utf-8")

    assert "TRUNCATE TABLE" in sql
    assert "RESTART IDENTITY CASCADE" in sql
    for table in (
        "dim_date",
        "dim_customer",
        "dim_vehicle",
        "dim_dealership",
        "dim_employee",
        "dim_service",
        "fact_sales",
        "fact_inventory",
        "fact_service",
    ):
        assert f"INSERT INTO analytics.{table}" in sql
