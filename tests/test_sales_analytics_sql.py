from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_SQL = PROJECT_ROOT / "sql" / "analytics" / "sales_analytics.sql"
VALIDATION_SQL = PROJECT_ROOT / "sql" / "analytics" / "sales_analytics_validation.sql"


def _analytics_sql() -> str:
    return ANALYTICS_SQL.read_text(encoding="utf-8")


def _validation_sql() -> str:
    return VALIDATION_SQL.read_text(encoding="utf-8")


def test_expected_sales_views_are_defined_once() -> None:
    sql = _analytics_sql()
    expected = {
        "vw_sales_detail",
        "vw_sales_kpis",
        "vw_monthly_sales",
        "vw_brand_model_performance",
        "vw_salesperson_performance",
        "vw_dealership_performance",
        "vw_vehicle_type_performance",
        "vw_payment_method_performance",
    }
    actual = re.findall(
        r"CREATE OR REPLACE VIEW\s+analytics\.(\w+)", sql, re.IGNORECASE
    )

    assert set(actual) == expected
    assert len(actual) == len(expected)


def test_detail_view_preserves_fact_grain_and_signs_returns() -> None:
    sql = _analytics_sql()
    detail = sql.split("CREATE OR REPLACE VIEW analytics.vw_sales_kpis", 1)[0]

    assert "f.sale_id" in detail
    assert "f.sale_price * f.unit_quantity" in detail
    assert "f.vehicle_cost * f.unit_quantity" in detail
    assert "f.gross_profit * f.unit_quantity" in detail
    assert "WHERE f.sale_status IN ('Completed', 'Returned')" in detail
    assert "dim_customer" not in detail


def test_all_aggregates_use_only_canonical_detail_view() -> None:
    sql = _analytics_sql()
    aggregate_sql = sql.split("CREATE OR REPLACE VIEW analytics.vw_sales_kpis", 1)[1]

    assert aggregate_sql.count("FROM analytics.vw_sales_detail") == 7
    assert "FROM analytics.fact_sales" not in aggregate_sql
    assert "JOIN analytics.dim_" not in aggregate_sql


def test_every_aggregate_exposes_required_kpis_and_grain_guard() -> None:
    sql = _analytics_sql()
    aggregate_names = [
        "vw_sales_kpis",
        "vw_monthly_sales",
        "vw_brand_model_performance",
        "vw_salesperson_performance",
        "vw_dealership_performance",
        "vw_vehicle_type_performance",
        "vw_payment_method_performance",
    ]
    for index, name in enumerate(aggregate_names):
        start = sql.index(f"CREATE OR REPLACE VIEW analytics.{name}")
        next_starts = [
            sql.find("CREATE OR REPLACE VIEW", start + 1),
            sql.find("COMMIT;", start + 1),
        ]
        end = min(position for position in next_starts if position >= 0)
        block = sql[start:end]
        for metric in (
            "units_sold",
            "revenue",
            "gross_profit",
            "gross_margin_percent",
            "average_selling_price",
            "fact_row_count",
            "distinct_sale_count",
        ):
            assert metric in block, f"{name} is missing {metric}"
        assert "NULLIF" in block
        assert "COUNT(DISTINCT sale_id)" in block


def test_requested_breakdown_columns_are_present() -> None:
    sql = _analytics_sql()

    assert "calendar_year" in sql and "month_number" in sql
    assert "brand" in sql and "model" in sql
    assert "salesperson_id" in sql and "salesperson_name" in sql
    assert "dealership_id" in sql and "dealership_name" in sql
    assert "vehicle_type" in sql and "vehicle_condition" in sql
    assert "payment_type" in sql


def test_validation_reconciles_fact_detail_kpis_and_all_grouped_views() -> None:
    sql = _validation_sql()

    assert "COUNT(DISTINCT sale_id)" in sql
    assert "fact_row_count - distinct_sale_count" in sql
    for metric in ("units_sold", "revenue", "gross_profit"):
        assert f"detail_vs_fact_{metric}" in sql
        assert f"kpi_vs_detail_{metric}" in sql
    for view in (
        "vw_monthly_sales",
        "vw_brand_model_performance",
        "vw_salesperson_performance",
        "vw_dealership_performance",
        "vw_vehicle_type_performance",
        "vw_payment_method_performance",
    ):
        assert view in sql


def test_validation_returns_clear_pass_fail_rows_and_is_read_only() -> None:
    sql = _validation_sql()

    assert "CASE WHEN ABS(difference) <= 0.02 THEN 'PASS' ELSE 'FAIL' END AS status" in sql
    assert "check_name" in sql and "difference" in sql and "details" in sql
    for mutation in ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE ", "DROP ", "ALTER "):
        assert mutation not in sql.upper()


def test_sql_files_have_balanced_parentheses_and_terminators() -> None:
    for path in (ANALYTICS_SQL, VALIDATION_SQL):
        sql = path.read_text(encoding="utf-8").strip()
        assert sql.count("(") == sql.count(")")
        assert sql.endswith(";")
