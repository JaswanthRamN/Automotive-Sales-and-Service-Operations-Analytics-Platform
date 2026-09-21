from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_SQL = PROJECT_ROOT / "sql" / "analytics" / "service_analytics.sql"
VALIDATION_SQL = PROJECT_ROOT / "sql" / "analytics" / "service_analytics_validation.sql"


def _analytics_sql() -> str:
    return ANALYTICS_SQL.read_text(encoding="utf-8")


def _validation_sql() -> str:
    return VALIDATION_SQL.read_text(encoding="utf-8")


def test_expected_service_views_are_defined_once() -> None:
    actual = re.findall(
        r"CREATE OR REPLACE VIEW\s+analytics\.(\w+)",
        _analytics_sql(),
        re.IGNORECASE,
    )
    expected = {
        "vw_service_appointment_detail",
        "vw_service_kpis",
        "vw_monthly_service_performance",
        "vw_service_type_performance",
        "vw_dealership_service_performance",
        "vw_technician_service_performance",
    }

    assert set(actual) == expected
    assert len(actual) == len(expected)


def test_detail_view_preserves_appointment_grain_and_safe_revenue_join() -> None:
    detail = _analytics_sql().split(
        "CREATE OR REPLACE VIEW analytics.vw_service_kpis", 1
    )[0]

    assert "FROM staging.service_appointments a" in detail
    assert "LEFT JOIN analytics.fact_service fs" in detail
    assert "ON fs.appointment_id = a.appointment_id" in detail
    assert "advisor.dealership_key = dl.dealership_key" in detail
    assert "advisor.role = 'Service Advisor'" in detail
    assert "a.appointment_id" in detail
    assert "COALESCE(fs.service_revenue, 0)" in detail


def test_appointment_status_metrics_and_completion_denominator_are_explicit() -> None:
    sql = _analytics_sql()

    assert "appointment_status = 'Completed'" in sql
    assert "appointment_status = 'Cancelled'" in sql
    assert "appointment_status = 'No Show'" in sql
    assert "appointment_status IN ('Completed', 'Cancelled', 'No Show')" in sql
    assert "NULLIF(SUM(completion_eligible_count), 0)" in sql


def test_service_cost_and_profit_are_not_fabricated() -> None:
    sql = _analytics_sql()

    assert "NULL::NUMERIC(16, 2) AS service_cost" in sql
    assert "NULL::NUMERIC(16, 2) AS service_profit" in sql
    assert "FALSE AS service_cost_available" in sql
    assert "service_cost *" not in sql
    assert "parts_revenue *" not in sql
    assert "labor_revenue *" not in sql


def test_all_aggregate_views_use_only_canonical_detail() -> None:
    aggregate_sql = _analytics_sql().split(
        "CREATE OR REPLACE VIEW analytics.vw_service_kpis", 1
    )[1]

    assert aggregate_sql.count("FROM analytics.vw_service_appointment_detail") == 5
    assert "FROM analytics.fact_service" not in aggregate_sql
    assert "FROM staging.service_appointments" not in aggregate_sql


def test_required_metrics_and_breakdowns_are_present() -> None:
    sql = _analytics_sql()

    for metric in (
        "appointments",
        "completed_appointments",
        "cancellations",
        "no_shows",
        "completion_rate_percent",
        "service_revenue",
        "service_cost",
        "service_profit",
        "average_repair_order",
    ):
        assert metric in sql
    for breakdown in (
        "service_type",
        "technician_name",
        "dealership_name",
        "calendar_year",
        "month_number",
    ):
        assert breakdown in sql


def test_average_repair_order_is_revenue_per_distinct_joined_order() -> None:
    sql = _analytics_sql()

    assert "SUM(service_revenue) / NULLIF(COUNT(service_order_id), 0)" in sql
    assert "COUNT(DISTINCT service_order_id)" in sql


def test_validation_reconciles_source_fact_detail_and_grouped_views() -> None:
    sql = _validation_sql()

    assert "detail_vs_source_appointments" in sql
    assert "detail_vs_source_completed" in sql
    assert "detail_vs_source_cancellations" in sql
    assert "detail_vs_source_no_shows" in sql
    assert "detail_vs_fact_repair_orders" in sql
    assert "detail_vs_fact_service_revenue" in sql
    assert "detail_repair_order_uniqueness" in sql
    assert "completed_appointments_have_one_order" in sql
    for view in (
        "vw_monthly_service_performance",
        "vw_service_type_performance",
        "vw_dealership_service_performance",
        "vw_technician_service_performance",
    ):
        assert view in sql


def test_validation_returns_pass_fail_and_is_read_only() -> None:
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
