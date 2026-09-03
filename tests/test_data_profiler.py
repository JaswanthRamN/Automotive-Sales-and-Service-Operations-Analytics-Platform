from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from automotive_analytics.data_generator import GeneratorConfig, write_datasets
from automotive_analytics.data_profiler import (
    build_foreign_key_report,
    build_validation_report,
    load_datasets,
    profile_raw_data,
)


CONFIG = GeneratorConfig(
    seed=19,
    customers=40,
    vehicles=80,
    dealerships=2,
    employees=20,
    sales=50,
    inventory=30,
    service_appointments=60,
    service_orders=50,
)


def _raw_fixture(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw"
    write_datasets(raw_dir, CONFIG)
    return raw_dir


def test_profiler_writes_complete_reports(tmp_path: Path) -> None:
    raw_dir = _raw_fixture(tmp_path)
    result = profile_raw_data(raw_dir, tmp_path / "profiling")

    assert result.passed
    assert result.error_count == 0
    assert set(result.report_paths) == {
        "dataset_profile",
        "column_profile",
        "validation_report",
        "foreign_key_report",
        "summary",
        "manifest",
    }
    assert all(path.is_file() and path.stat().st_size > 0 for path in result.report_paths.values())

    dataset_report = pd.read_csv(result.report_paths["dataset_profile"])
    column_report = pd.read_csv(result.report_paths["column_profile"])
    assert dict(zip(dataset_report.dataset, dataset_report.row_count)) == {
        "customers": 40,
        "dealerships": 2,
        "employees": 20,
        "inventory": 30,
        "sales": 50,
        "service_appointments": 60,
        "service_orders": 50,
        "vehicles": 80,
    }
    assert {"data_type", "null_count", "unique_count", "numeric_min", "numeric_max", "date_min", "date_max"} <= set(column_report.columns)


def test_profiler_detects_orphaned_foreign_key(tmp_path: Path) -> None:
    raw_dir = _raw_fixture(tmp_path)
    sales_path = raw_dir / "sales.csv"
    sales = pd.read_csv(sales_path)
    sales.loc[0, "customer_id"] = "CUS-MISSING"
    sales.to_csv(sales_path, index=False)

    report = build_foreign_key_report(load_datasets(raw_dir))
    customer_check = report[(report.child_dataset == "sales") & (report.child_column == "customer_id")].iloc[0]

    assert customer_check.status == "FAIL"
    assert customer_check.orphan_count == 1
    assert "CUS-MISSING" in customer_check.details


def test_profiler_detects_invalid_values_and_duplicates(tmp_path: Path) -> None:
    raw_dir = _raw_fixture(tmp_path)
    sales_path = raw_dir / "sales.csv"
    sales = pd.read_csv(sales_path)
    sales.loc[0, "gross_profit"] = -500
    sales.loc[1, "sale_id"] = sales.loc[0, "sale_id"]
    sales.to_csv(sales_path, index=False)

    report = build_validation_report(load_datasets(raw_dir))
    failed = report[(report.dataset == "sales") & (report.status == "FAIL")]

    assert "gross_profit is nonnegative numeric" in set(failed.check)
    assert "gross_profit equals sale_price minus vehicle_cost" in set(failed.check)
    assert "sale_id is unique" in set(failed.check)


def test_profiler_detects_invalid_dates(tmp_path: Path) -> None:
    raw_dir = _raw_fixture(tmp_path)
    inventory_path = raw_dir / "inventory.csv"
    inventory = pd.read_csv(inventory_path)
    inventory.loc[0, "acquired_date"] = "not-a-date"
    inventory.to_csv(inventory_path, index=False)

    report = build_validation_report(load_datasets(raw_dir))
    check = report[(report.dataset == "inventory") & (report.check == "acquired_date contains valid dates")].iloc[0]

    assert check.status == "FAIL"
    assert check.invalid_count == 1
