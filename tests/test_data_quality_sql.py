from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_QUALITY_SQL = PROJECT_ROOT / "sql" / "analytics" / "data_quality.sql"


def _sql() -> str:
    return DATA_QUALITY_SQL.read_text(encoding="utf-8")


def test_data_quality_sql_exists_and_is_read_only() -> None:
    sql = _sql()

    assert sql.count("(") == sql.count(")")
    assert sql.rstrip().endswith(";")
    for mutation in ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE ", "DROP ", "ALTER "):
        assert mutation not in sql.upper()


def test_result_contract_has_clear_pass_fail_fields() -> None:
    sql = _sql()

    assert "check_category" in sql
    assert "check_name" in sql
    assert "failed_count" in sql
    assert "details" in sql
    assert "CASE WHEN failed_count = 0 THEN 'PASS' ELSE 'FAIL' END AS status" in sql
    assert "ORDER BY check_category, check_name" in sql


def test_every_requested_quality_category_is_covered() -> None:
    sql = _sql()
    categories = set(re.findall(r"SELECT\s+'([a-z_]+)'(?:::\w+)?\s*(?:AS\s+check_category)?", sql, re.IGNORECASE))

    assert {
        "duplicates",
        "duplicate_facts",
        "missing_foreign_keys",
        "orphan_records",
        "invalid_dates",
        "invalid_prices",
        "negative_revenue",
    } <= {category.lower() for category in categories}


def test_checks_cover_all_dimensions_and_facts() -> None:
    sql = _sql()
    for table in (
        "dim_customer",
        "dim_vehicle",
        "dim_employee",
        "dim_dealership",
        "dim_service",
        "dim_date",
        "fact_sales",
        "fact_inventory",
        "fact_service",
    ):
        assert f"analytics.{table}" in sql


def test_all_fact_foreign_keys_are_checked_for_missing_and_orphans() -> None:
    sql = _sql()
    fact_keys = {
        "fact_sales": ["sale_date_key", "customer_key", "vehicle_key", "dealership_key", "salesperson_key"],
        "fact_inventory": ["snapshot_date_key", "vehicle_key", "dealership_key"],
        "fact_service": ["completed_date_key", "customer_key", "vehicle_key", "dealership_key", "service_advisor_key", "technician_key", "service_key"],
    }
    for fact, keys in fact_keys.items():
        assert f"{fact} missing foreign keys" in sql
        assert f"{fact} orphan dimension keys" in sql
        for key in keys:
            assert key in sql


def test_duplicate_fact_grains_are_explicit() -> None:
    sql = _sql()

    assert "fact_sales duplicate sale_id" in sql
    assert "GROUP BY sale_id" in sql
    assert "fact_inventory duplicate vehicle snapshot" in sql
    assert "GROUP BY vehicle_key, dealership_key, snapshot_date_key" in sql
    assert "fact_service duplicate order or appointment" in sql
    assert "GROUP BY service_order_id" in sql
    assert "GROUP BY appointment_id" in sql


def test_price_revenue_and_date_formulas_match_schema_contract() -> None:
    sql = _sql()

    assert "ABS((list_price - discount_amount) - sale_price) > 0.02" in sql
    assert "ABS((sale_price - vehicle_cost) - gross_profit) > 0.02" in sql
    assert "ABS((labor_revenue + parts_revenue - discount_amount) - service_revenue) > 0.02" in sql
    assert "sale_price < 0" in sql
    assert "service_revenue < 0" in sql
    assert "acquired_date > d.full_date" in sql
    assert "opened_at > f.promised_at" in sql


def test_query_returns_one_check_row_per_union_branch() -> None:
    sql = _sql()
    check_names = re.findall(
        r"SELECT\s+'[a-z_]+'(?:::\w+)?(?:\s+AS\s+check_category)?,\s*'([^']+)'",
        sql,
        re.IGNORECASE,
    )

    assert len(check_names) >= 20
    assert len(check_names) == len(set(check_names))
