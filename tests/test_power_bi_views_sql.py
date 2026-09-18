from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIEWS_SQL = PROJECT_ROOT / "sql" / "analytics" / "power_bi_views.sql"
VALIDATION_SQL = PROJECT_ROOT / "sql" / "analytics" / "power_bi_views_validation.sql"
DOCUMENTATION = PROJECT_ROOT / "docs" / "power_bi_views.md"


def _views_sql() -> str:
    return VIEWS_SQL.read_text(encoding="utf-8")


def _validation_sql() -> str:
    return VALIDATION_SQL.read_text(encoding="utf-8")


def test_exact_requested_power_bi_views_are_created() -> None:
    actual = re.findall(
        r"CREATE OR REPLACE VIEW\s+analytics\.(\w+)",
        _views_sql(),
        re.IGNORECASE,
    )
    expected = {
        "vw_sales_performance",
        "vw_inventory_aging",
        "vw_service_performance",
        "vw_customer_value",
        "vw_dealership_performance",
    }

    assert set(actual) == expected
    assert len(actual) == len(expected)


def test_detail_views_select_from_canonical_grain_safe_views() -> None:
    sql = _views_sql()

    assert "FROM analytics.vw_sales_detail" in sql
    assert "FROM analytics.vw_inventory_detail" in sql
    assert "FROM analytics.vw_service_appointment_detail" in sql
    assert "FROM analytics.vw_customer_lifetime_detail" in sql


def test_dealership_subjects_are_aggregated_before_joining() -> None:
    sql = _views_sql()
    dealership = sql.split(
        "CREATE OR REPLACE VIEW analytics.vw_dealership_performance", 1
    )[1]

    for cte in ("sales AS", "inventory AS", "service AS", "customers AS"):
        assert cte in dealership
    assert dealership.count("GROUP BY dealership_key") >= 3
    assert "LEFT JOIN sales" in dealership
    assert "LEFT JOIN inventory" in dealership
    assert "LEFT JOIN service" in dealership
    assert "LEFT JOIN customers" in dealership
    assert "WHERE d.is_current" in dealership


def test_inventory_scorecard_uses_only_latest_snapshot() -> None:
    sql = _views_sql()

    assert "latest_inventory_snapshot AS" in sql
    assert "SELECT MAX(snapshot_date_key)" in sql
    assert "s.snapshot_date_key = i.snapshot_date_key" in sql


def test_business_metrics_and_friendly_columns_are_present() -> None:
    sql = _views_sql()

    for metric in (
        "units_sold",
        "sales_revenue",
        "gross_margin_percent",
        "inventory_units",
        "inventory_value",
        "days_in_inventory",
        "service_revenue",
        "completion_eligible_count",
        "customer_lifetime_value",
        "relationship_segment",
        "unique_customers",
        "total_revenue",
    ):
        assert metric in sql


def test_customer_view_excludes_direct_contact_fields() -> None:
    sql = _views_sql()
    customer_projection = sql.split(
        "CREATE OR REPLACE VIEW analytics.vw_customer_value", 1
    )[1].split("FROM analytics.vw_customer_lifetime_detail", 1)[0]

    assert "email" not in customer_projection.lower()
    assert "phone" not in customer_projection.lower()


def test_every_view_has_database_documentation() -> None:
    sql = _views_sql()
    comments = re.findall(r"COMMENT ON VIEW analytics\.(\w+)", sql, re.IGNORECASE)

    assert len(comments) == 5
    assert DOCUMENTATION.is_file()
    docs = DOCUMENTATION.read_text(encoding="utf-8")
    for view in comments:
        assert f"`analytics.{view}`" in docs


def test_validation_checks_each_view_and_reconciles_revenue() -> None:
    sql = _validation_sql()

    for view in (
        "vw_sales_performance",
        "vw_inventory_aging",
        "vw_service_performance",
        "vw_customer_value",
        "vw_dealership_performance",
    ):
        assert view in sql
    assert "COUNT(DISTINCT sale_id)" in sql
    assert "COUNT(DISTINCT appointment_id)" in sql
    assert "COUNT(DISTINCT customer_id)" in sql
    assert "vw_service_performance_revenue" in sql
    assert "vw_customer_value_revenue" in sql


def test_validation_returns_pass_fail_and_is_read_only() -> None:
    sql = _validation_sql()

    assert "CASE WHEN ABS(difference) <= 0.02 THEN 'PASS' ELSE 'FAIL' END AS status" in sql
    for mutation in ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE ", "DROP ", "ALTER "):
        assert mutation not in sql.upper()


def test_sql_files_have_balanced_parentheses_and_terminators() -> None:
    for path in (VIEWS_SQL, VALIDATION_SQL):
        sql = path.read_text(encoding="utf-8").strip()
        assert sql.count("(") == sql.count(")")
        assert sql.endswith(";")
