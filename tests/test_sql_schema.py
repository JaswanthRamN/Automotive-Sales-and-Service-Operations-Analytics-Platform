from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = PROJECT_ROOT / "sql"
DDL_FILES = [
    "001_create_schemas.sql",
    "002_create_staging_tables.sql",
    "003_create_dimensions.sql",
    "004_create_facts.sql",
    "005_create_indexes.sql",
]


def _ddl() -> str:
    return "\n".join((SQL_DIR / name).read_text(encoding="utf-8") for name in DDL_FILES)


def _table_block(ddl: str, qualified_table: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {re.escape(qualified_table)}\s*\((.*?)\n\);",
        ddl,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"Missing table definition for {qualified_table}"
    return match.group(1)


def test_ddl_files_are_ordered_and_transactional() -> None:
    assert [path.name for path in sorted(SQL_DIR.glob("*.sql"))] == DDL_FILES
    for name in DDL_FILES:
        sql = (SQL_DIR / name).read_text(encoding="utf-8").strip()
        assert sql.startswith("BEGIN;")
        assert sql.endswith("COMMIT;")
        assert sql.count("(") == sql.count(")")
        assert "DROP TABLE" not in sql.upper()
        assert "INSERT INTO" not in sql.upper()
        assert "COPY " not in sql.upper()


def test_required_schemas_and_tables_exist() -> None:
    ddl = _ddl()
    assert "CREATE SCHEMA IF NOT EXISTS staging" in ddl
    assert "CREATE SCHEMA IF NOT EXISTS analytics" in ddl

    staging_tables = {
        "customers",
        "vehicles",
        "dealerships",
        "employees",
        "sales",
        "inventory",
        "service_appointments",
        "service_orders",
    }
    dimensions = {
        "dim_date",
        "dim_customer",
        "dim_vehicle",
        "dim_dealership",
        "dim_employee",
        "dim_service",
    }
    facts = {"fact_sales", "fact_inventory", "fact_service"}
    for table in staging_tables:
        _table_block(ddl, f"staging.{table}")
    for table in dimensions | facts:
        _table_block(ddl, f"analytics.{table}")


def test_analytics_tables_have_primary_keys_and_named_constraints() -> None:
    ddl = _ddl()
    analytics_tables = {
        "dim_date",
        "dim_customer",
        "dim_vehicle",
        "dim_dealership",
        "dim_employee",
        "dim_service",
        "fact_sales",
        "fact_inventory",
        "fact_service",
    }
    for table in analytics_tables:
        block = _table_block(ddl, f"analytics.{table}")
        assert "PRIMARY KEY" in block, f"{table} has no primary key"
    assert len(re.findall(r"CONSTRAINT\s+fk_", ddl, flags=re.IGNORECASE)) == 16
    assert len(re.findall(r"CONSTRAINT\s+ck_", ddl, flags=re.IGNORECASE)) >= 20


def test_fact_foreign_keys_reference_conformed_dimensions() -> None:
    ddl = _ddl()
    expected_references = {
        "fact_sales": {"dim_date", "dim_customer", "dim_vehicle", "dim_dealership", "dim_employee"},
        "fact_inventory": {"dim_date", "dim_vehicle", "dim_dealership"},
        "fact_service": {"dim_date", "dim_customer", "dim_vehicle", "dim_dealership", "dim_employee", "dim_service"},
    }
    for fact, dimensions in expected_references.items():
        block = _table_block(ddl, f"analytics.{fact}")
        for dimension in dimensions:
            assert f"REFERENCES analytics.{dimension}" in block


def test_fact_grain_and_measure_constraints_are_present() -> None:
    ddl = _ddl()
    sales = _table_block(ddl, "analytics.fact_sales")
    inventory = _table_block(ddl, "analytics.fact_inventory")
    service = _table_block(ddl, "analytics.fact_service")

    assert "sale_id VARCHAR(20) NOT NULL UNIQUE" in sales
    assert "ABS((list_price - discount_amount) - sale_price) <= 0.02" in sales
    assert "uq_fact_inventory_vehicle_snapshot" in inventory
    assert "days_in_inventory >= 0" in inventory
    assert "service_order_id VARCHAR(20) NOT NULL UNIQUE" in service
    assert "appointment_id VARCHAR(20) NOT NULL UNIQUE" in service
    assert "opened_at <= promised_at AND opened_at <= completed_at" in service
    assert "ABS((labor_revenue + parts_revenue - discount_amount) - service_revenue) <= 0.02" in service


def test_foreign_keys_and_common_filter_paths_are_indexed() -> None:
    ddl = _ddl()
    indexes = re.findall(
        r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS\s+(\w+)\s+ON\s+analytics\.(\w+)\s*\(([^)]+)\)",
        ddl,
        flags=re.IGNORECASE,
    )
    assert len(indexes) >= 16
    indexed_tables = {table for _, table, _ in indexes}
    assert {"dim_customer", "dim_vehicle", "dim_employee", "fact_sales", "fact_inventory", "fact_service"} <= indexed_tables


def test_postgresql_specific_types_and_identity_keys_are_used() -> None:
    ddl = _ddl().upper()
    assert "GENERATED ALWAYS AS IDENTITY" in ddl
    assert "TIMESTAMPTZ" in ddl
    assert "NUMERIC(14, 2)" in ddl
    assert "GENERATED ALWAYS AS (COMPLETED_AT <= PROMISED_AT) STORED" in ddl
