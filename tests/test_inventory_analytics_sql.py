from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_SQL = PROJECT_ROOT / "sql" / "analytics" / "inventory_analytics.sql"
VALIDATION_SQL = PROJECT_ROOT / "sql" / "analytics" / "inventory_analytics_validation.sql"


def _analytics_sql() -> str:
    return ANALYTICS_SQL.read_text(encoding="utf-8")


def _validation_sql() -> str:
    return VALIDATION_SQL.read_text(encoding="utf-8")


def test_expected_inventory_views_are_defined_once() -> None:
    actual = re.findall(
        r"CREATE OR REPLACE VIEW\s+analytics\.(\w+)",
        _analytics_sql(),
        re.IGNORECASE,
    )
    expected = {
        "vw_inventory_detail",
        "vw_inventory_kpis",
        "vw_inventory_aging_buckets",
        "vw_brand_model_inventory",
        "vw_dealership_inventory",
        "vw_slow_moving_vehicles",
    }

    assert set(actual) == expected
    assert len(actual) == len(expected)


def test_detail_view_preserves_inventory_snapshot_grain() -> None:
    detail = _analytics_sql().split(
        "CREATE OR REPLACE VIEW analytics.vw_inventory_kpis", 1
    )[0]

    assert "f.inventory_key" in detail
    assert "f.snapshot_date_key" in detail
    assert "f.vehicle_key" in detail
    assert "f.dealership_key" in detail
    assert "FROM analytics.fact_inventory f" in detail
    assert detail.count("JOIN analytics.dim_") == 3


def test_aging_buckets_are_mutually_exclusive_and_ordered() -> None:
    sql = _analytics_sql()

    boundaries = [
        "BETWEEN 0 AND 30 THEN '0-30'",
        "BETWEEN 31 AND 60 THEN '31-60'",
        "BETWEEN 61 AND 90 THEN '61-90'",
        "BETWEEN 91 AND 120 THEN '91-120'",
        "ELSE '120+'",
    ]
    for boundary in boundaries:
        assert boundary in sql
    assert "aging_bucket_sort" in sql


def test_slow_moving_definition_is_strictly_over_90_days() -> None:
    sql = _analytics_sql()

    assert "(f.days_in_inventory > 90) AS is_slow_moving" in sql
    assert "WHERE days_in_inventory > 90" in sql
    assert ">= 90" not in sql


def test_all_aggregate_views_are_snapshot_aware_and_use_canonical_detail() -> None:
    sql = _analytics_sql()
    aggregate_sql = sql.split(
        "CREATE OR REPLACE VIEW analytics.vw_inventory_kpis", 1
    )[1]

    assert aggregate_sql.count("FROM analytics.vw_inventory_detail") == 5
    assert "FROM analytics.fact_inventory" not in aggregate_sql
    assert aggregate_sql.count("snapshot_date_key") >= 9


def test_required_inventory_metrics_and_breakdowns_are_present() -> None:
    sql = _analytics_sql()

    for metric in (
        "inventory_units",
        "inventory_value",
        "days_in_inventory",
        "total_inventory_days",
        "average_age_days",
        "slow_moving_units",
        "slow_moving_value",
    ):
        assert metric in sql
    for breakdown in (
        "aging_bucket",
        "brand",
        "model",
        "dealership_name",
    ):
        assert breakdown in sql


def test_average_age_is_weighted_and_safe_for_empty_units() -> None:
    sql = _analytics_sql()

    assert "SUM(days_in_inventory * inventory_units)::NUMERIC" in sql
    assert "NULLIF(SUM(inventory_units), 0)" in sql


def test_validation_reconciles_all_views_by_snapshot() -> None:
    sql = _validation_sql()

    assert "detail_vs_fact_by_snapshot" in sql
    assert "kpis_vs_detail_by_snapshot" in sql
    assert "slow_moving_view_vs_detail_by_snapshot" in sql
    for view in (
        "vw_inventory_aging_buckets",
        "vw_brand_model_inventory",
        "vw_dealership_inventory",
    ):
        assert view in sql
    assert "FULL JOIN" in sql
    assert "GROUP BY snapshot_date_key" in sql


def test_validation_returns_pass_fail_and_is_read_only() -> None:
    sql = _validation_sql()

    assert "CASE WHEN failed_count = 0 THEN 'PASS' ELSE 'FAIL' END AS status" in sql
    assert "check_name" in sql and "failed_count" in sql and "details" in sql
    for mutation in ("INSERT INTO", "UPDATE ", "DELETE FROM", "TRUNCATE ", "DROP ", "ALTER "):
        assert mutation not in sql.upper()


def test_sql_files_have_balanced_parentheses_and_terminators() -> None:
    for path in (ANALYTICS_SQL, VALIDATION_SQL):
        sql = path.read_text(encoding="utf-8").strip()
        assert sql.count("(") == sql.count(")")
        assert sql.endswith(";")
