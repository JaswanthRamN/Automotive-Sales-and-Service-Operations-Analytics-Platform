from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_SQL = PROJECT_ROOT / "sql" / "analytics" / "customer_analytics.sql"
VALIDATION_SQL = PROJECT_ROOT / "sql" / "analytics" / "customer_analytics_validation.sql"


def _analytics_sql() -> str:
    return ANALYTICS_SQL.read_text(encoding="utf-8")


def _validation_sql() -> str:
    return VALIDATION_SQL.read_text(encoding="utf-8")


def test_expected_customer_views_are_defined_once() -> None:
    actual = re.findall(
        r"CREATE OR REPLACE VIEW\s+analytics\.(\w+)",
        _analytics_sql(),
        re.IGNORECASE,
    )
    expected = {
        "vw_customer_lifetime_detail",
        "vw_customer_kpis",
        "vw_customer_segment_summary",
        "vw_customer_service_frequency",
    }

    assert set(actual) == expected
    assert len(actual) == len(expected)


def test_sales_and_service_are_aggregated_before_customer_join() -> None:
    sql = _analytics_sql()
    detail = sql.split("CREATE OR REPLACE VIEW analytics.vw_customer_kpis", 1)[0]

    assert "sales_by_customer AS" in detail
    assert "service_by_customer AS" in detail
    assert detail.count("GROUP BY f.customer_key") == 2
    assert "LEFT JOIN sales_by_customer" in detail
    assert "LEFT JOIN service_by_customer" in detail
    assert "WHERE c.is_current" in detail


def test_customer_segments_are_clear_and_mutually_exclusive() -> None:
    sql = _analytics_sql()

    for relationship in ("Sales Only", "Service Only", "Sales + Service", "No Activity"):
        assert relationship in sql
    for lifecycle in ("Prospect", "New Customer", "Repeat Customer"):
        assert lifecycle in sql
    for activity in ("Never Active", "Inactive", "Active"):
        assert activity in sql


def test_new_repeat_rate_and_inactive_definitions_are_explicit() -> None:
    sql = _analytics_sql()

    assert "qualifying_interaction_count = 1 THEN 'New Customer'" in sql
    assert "ELSE 'Repeat Customer'" in sql
    assert "NULLIF(COUNT(*) FILTER (WHERE qualifying_interaction_count > 0), 0)" in sql
    assert "last_activity_date < as_of_date - INTERVAL '365 days'" in sql


def test_clv_is_revenue_based_and_not_mixed_with_unavailable_service_profit() -> None:
    sql = _analytics_sql()

    assert "(sales_revenue + service_revenue)::NUMERIC(18, 2) AS customer_lifetime_value" in sql
    assert "'Revenue-based interim CLV'::TEXT AS clv_method" in sql
    assert "service_profit" not in sql
    assert "gross_profit" not in sql


def test_required_customer_kpis_are_present() -> None:
    sql = _analytics_sql()

    for metric in (
        "total_customers",
        "new_customers",
        "repeat_customers",
        "repeat_rate_percent",
        "customer_revenue",
        "customer_lifetime_value",
        "sales_only_customers",
        "service_only_customers",
        "sales_and_service_customers",
        "inactive_customers",
        "service_frequency_per_year",
        "average_days_between_services",
    ):
        assert metric in sql


def test_service_frequency_segments_are_ordered_and_exposed() -> None:
    sql = _analytics_sql()

    for segment in (
        "No Service",
        "One-time Service",
        "Occasional Service",
        "Frequent Service",
        "Loyal Service",
    ):
        assert segment in sql
    assert "service_frequency_sort" in sql
    assert "service_frequency_per_year" in sql


def test_validation_reconciles_facts_kpis_segments_and_frequency() -> None:
    sql = _validation_sql()

    for check in (
        "detail_customer_uniqueness",
        "detail_vs_current_customers",
        "detail_vs_fact_sales_transactions",
        "detail_vs_fact_sales_revenue",
        "detail_vs_fact_service_orders",
        "detail_vs_fact_service_revenue",
        "customer_revenue_formula",
        "revenue_based_clv_formula",
        "lifecycle_segments_are_exclusive",
        "relationship_segments_are_exclusive",
        "inactive_customer_definition",
        "kpis_vs_detail_customer_count",
        "segment_summary_vs_detail_customers",
        "frequency_summary_vs_detail_customers",
    ):
        assert check in sql


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
