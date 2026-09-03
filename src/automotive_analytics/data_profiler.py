"""Profile and validate the synthetic automotive CSV datasets."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PRIMARY_KEYS = {
    "customers": "customer_id",
    "vehicles": "vehicle_id",
    "dealerships": "dealership_id",
    "employees": "employee_id",
    "sales": "sale_id",
    "inventory": "inventory_id",
    "service_appointments": "appointment_id",
    "service_orders": "service_order_id",
}

DATE_COLUMNS = {
    "customers": ["customer_since_date"],
    "dealerships": ["opened_date"],
    "employees": ["hire_date"],
    "sales": ["sale_date"],
    "inventory": ["snapshot_date", "acquired_date"],
    "service_appointments": ["appointment_date"],
    "service_orders": ["opened_at", "promised_at", "completed_at"],
}

FOREIGN_KEYS = [
    ("employees", "dealership_id", "dealerships", "dealership_id"),
    ("sales", "customer_id", "customers", "customer_id"),
    ("sales", "vehicle_id", "vehicles", "vehicle_id"),
    ("sales", "dealership_id", "dealerships", "dealership_id"),
    ("sales", "salesperson_id", "employees", "employee_id"),
    ("inventory", "vehicle_id", "vehicles", "vehicle_id"),
    ("inventory", "dealership_id", "dealerships", "dealership_id"),
    ("service_appointments", "customer_id", "customers", "customer_id"),
    ("service_appointments", "vehicle_id", "vehicles", "vehicle_id"),
    ("service_appointments", "dealership_id", "dealerships", "dealership_id"),
    ("service_appointments", "service_advisor_id", "employees", "employee_id"),
    ("service_orders", "appointment_id", "service_appointments", "appointment_id"),
    ("service_orders", "customer_id", "customers", "customer_id"),
    ("service_orders", "vehicle_id", "vehicles", "vehicle_id"),
    ("service_orders", "dealership_id", "dealerships", "dealership_id"),
    ("service_orders", "service_advisor_id", "employees", "employee_id"),
    ("service_orders", "technician_id", "employees", "employee_id"),
]

ALLOWED_VALUES = {
    ("customers", "customer_type"): {"Individual", "Business", "Fleet"},
    ("employees", "role"): {"Sales Consultant", "Service Advisor", "Service Technician", "Inventory Specialist", "Manager"},
    ("employees", "employment_status"): {"Active", "Inactive"},
    ("vehicles", "vehicle_condition"): {"New", "Used"},
    ("sales", "sales_channel"): {"Showroom", "Online", "Fleet", "Partner"},
    ("sales", "payment_type"): {"Finance", "Cash", "Lease"},
    ("sales", "sale_status"): {"Completed"},
    ("inventory", "inventory_status"): {"Available", "Reserved", "In Transit", "Demonstrator"},
    ("service_appointments", "appointment_status"): {"Completed", "Scheduled", "Cancelled", "No Show"},
    ("service_orders", "order_status"): {"Completed"},
    ("service_orders", "payer_type"): {"Customer Pay", "Warranty", "Internal"},
}

NONNEGATIVE_COLUMNS = {
    "vehicles": ["mileage_at_acquisition", "manufacturer_msrp"],
    "sales": ["list_price", "discount_amount", "sale_price", "vehicle_cost", "gross_profit"],
    "inventory": ["carrying_cost", "days_in_inventory"],
    "service_orders": ["labor_revenue", "parts_revenue", "discount_amount", "service_revenue"],
}


@dataclass(frozen=True)
class ProfileResult:
    """Generated report locations and overall validation outcome."""

    report_paths: dict[str, Path]
    passed: bool
    error_count: int


def load_datasets(raw_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Load every CSV in a directory, failing clearly when none are present."""

    source = Path(raw_dir)
    csv_paths = sorted(source.glob("*.csv"))
    if not csv_paths:
        raise FileNotFoundError(f"No CSV files found in {source}")
    return {path.stem: pd.read_csv(path, low_memory=False) for path in csv_paths}


def _safe_date_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], errors="coerce", format="mixed")


def _to_markdown_table(frame: pd.DataFrame) -> str:
    """Render a compact Markdown table without optional dependencies."""

    columns = [str(column) for column in frame.columns]

    def clean(value: object) -> str:
        if pd.isna(value):
            return ""
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines.extend(
        "| " + " | ".join(clean(value) for value in row) + " |"
        for row in frame.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def build_dataset_profile(datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, frame in sorted(datasets.items()):
        key = PRIMARY_KEYS.get(name)
        rows.append(
            {
                "dataset": name,
                "row_count": len(frame),
                "column_count": len(frame.columns),
                "duplicate_row_count": int(frame.duplicated().sum()),
                "total_null_count": int(frame.isna().sum().sum()),
                "primary_key": key or "",
                "duplicate_primary_key_count": int(frame[key].duplicated().sum()) if key in frame else "",
            }
        )
    return pd.DataFrame(rows)


def build_column_profile(datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for dataset, frame in sorted(datasets.items()):
        configured_dates = set(DATE_COLUMNS.get(dataset, []))
        for column in frame.columns:
            series = frame[column]
            nonnull = series.dropna()
            numeric = pd.to_numeric(series, errors="coerce") if pd.api.types.is_numeric_dtype(series) else None
            parsed_dates = _safe_date_series(frame, column) if column in configured_dates else None
            sample_values = sorted({str(value) for value in nonnull.head(1_000)})[:5]
            rows.append(
                {
                    "dataset": dataset,
                    "column": column,
                    "data_type": str(series.dtype),
                    "row_count": len(series),
                    "null_count": int(series.isna().sum()),
                    "null_percent": round(float(series.isna().mean() * 100), 4),
                    "unique_count": int(series.nunique(dropna=True)),
                    "sample_unique_values": " | ".join(sample_values),
                    "numeric_min": numeric.min() if numeric is not None and numeric.notna().any() else "",
                    "numeric_max": numeric.max() if numeric is not None and numeric.notna().any() else "",
                    "numeric_mean": numeric.mean() if numeric is not None and numeric.notna().any() else "",
                    "date_min": parsed_dates.min().isoformat() if parsed_dates is not None and parsed_dates.notna().any() else "",
                    "date_max": parsed_dates.max().isoformat() if parsed_dates is not None and parsed_dates.notna().any() else "",
                    "invalid_date_count": int(parsed_dates.isna().sum() - series.isna().sum()) if parsed_dates is not None else "",
                }
            )
    return pd.DataFrame(rows)


def build_foreign_key_report(datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for child, child_column, parent, parent_column in FOREIGN_KEYS:
        if child not in datasets or parent not in datasets:
            rows.append(
                {
                    "child_dataset": child,
                    "child_column": child_column,
                    "parent_dataset": parent,
                    "parent_column": parent_column,
                    "checked_rows": 0,
                    "orphan_count": "",
                    "status": "NOT_CHECKED",
                    "details": "Required dataset is missing",
                }
            )
            continue
        child_frame, parent_frame = datasets[child], datasets[parent]
        if child_column not in child_frame or parent_column not in parent_frame:
            rows.append(
                {
                    "child_dataset": child,
                    "child_column": child_column,
                    "parent_dataset": parent,
                    "parent_column": parent_column,
                    "checked_rows": 0,
                    "orphan_count": "",
                    "status": "NOT_CHECKED",
                    "details": "Required column is missing",
                }
            )
            continue
        values = child_frame[child_column].dropna()
        orphan_mask = ~values.isin(set(parent_frame[parent_column].dropna()))
        orphan_count = int(orphan_mask.sum())
        examples = values[orphan_mask].astype(str).drop_duplicates().head(5).tolist()
        rows.append(
            {
                "child_dataset": child,
                "child_column": child_column,
                "parent_dataset": parent,
                "parent_column": parent_column,
                "checked_rows": len(values),
                "orphan_count": orphan_count,
                "status": "PASS" if orphan_count == 0 else "FAIL",
                "details": " | ".join(examples),
            }
        )
    return pd.DataFrame(rows)


def _check_row(
    dataset: str,
    check: str,
    invalid: pd.Series | list[bool],
    severity: str = "ERROR",
    detail_values: pd.Series | None = None,
) -> dict[str, object]:
    mask = pd.Series(invalid, dtype=bool)
    count = int(mask.sum())
    examples = [] if detail_values is None else detail_values.loc[mask].astype(str).drop_duplicates().head(5).tolist()
    return {
        "dataset": dataset,
        "check": check,
        "severity": severity,
        "invalid_count": count,
        "status": "PASS" if count == 0 else "FAIL",
        "examples": " | ".join(examples),
    }


def build_validation_report(datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    required = set(PRIMARY_KEYS)
    for missing in sorted(required - set(datasets)):
        rows.append({"dataset": missing, "check": "required dataset exists", "severity": "ERROR", "invalid_count": 1, "status": "FAIL", "examples": "missing CSV"})

    for dataset, frame in sorted(datasets.items()):
        key = PRIMARY_KEYS.get(dataset)
        if key is not None:
            if key not in frame:
                rows.append({"dataset": dataset, "check": f"primary key column {key} exists", "severity": "ERROR", "invalid_count": 1, "status": "FAIL", "examples": "missing column"})
            else:
                rows.append(_check_row(dataset, f"{key} is populated", frame[key].isna(), detail_values=frame[key]))
                rows.append(_check_row(dataset, f"{key} is unique", frame[key].duplicated(keep=False), detail_values=frame[key]))
        rows.append(_check_row(dataset, "rows are unique", frame.duplicated(keep=False)))

        for column in DATE_COLUMNS.get(dataset, []):
            if column not in frame:
                rows.append({"dataset": dataset, "check": f"{column} exists", "severity": "ERROR", "invalid_count": 1, "status": "FAIL", "examples": "missing column"})
            else:
                parsed = _safe_date_series(frame, column)
                rows.append(_check_row(dataset, f"{column} contains valid dates", parsed.isna() & frame[column].notna(), detail_values=frame[column]))

        for column in NONNEGATIVE_COLUMNS.get(dataset, []):
            if column in frame:
                numeric = pd.to_numeric(frame[column], errors="coerce")
                rows.append(_check_row(dataset, f"{column} is nonnegative numeric", numeric.isna() | (numeric < 0), detail_values=frame[column]))

        for (domain_dataset, column), allowed in ALLOWED_VALUES.items():
            if domain_dataset == dataset and column in frame:
                rows.append(_check_row(dataset, f"{column} uses allowed values", ~frame[column].isin(allowed), detail_values=frame[column]))

    if "customers" in datasets and "email" in datasets["customers"]:
        emails = datasets["customers"]["email"].astype("string")
        rows.append(_check_row("customers", "email has a valid basic format", ~emails.str.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", na=False), detail_values=emails))

    if "inventory" in datasets:
        inventory = datasets["inventory"]
        needed = {"acquired_date", "snapshot_date", "days_in_inventory", "slow_moving_flag"}
        if needed <= set(inventory):
            acquired = _safe_date_series(inventory, "acquired_date")
            snapshot = _safe_date_series(inventory, "snapshot_date")
            expected_days = (snapshot - acquired).dt.days
            rows.append(_check_row("inventory", "acquired_date is on or before snapshot_date", acquired > snapshot))
            rows.append(_check_row("inventory", "days_in_inventory matches dates", pd.to_numeric(inventory.days_in_inventory, errors="coerce") != expected_days, detail_values=inventory.inventory_id))
            slow_flag = inventory.slow_moving_flag.astype("string").str.lower().map({"true": True, "false": False})
            rows.append(_check_row("inventory", "slow_moving_flag matches 90-day rule", slow_flag != (expected_days > 90), detail_values=inventory.inventory_id))

    if "sales" in datasets:
        sales = datasets["sales"]
        needed = {"list_price", "discount_amount", "sale_price", "vehicle_cost", "gross_profit"}
        if needed <= set(sales):
            rows.append(_check_row("sales", "sale_price equals list_price minus discount", (sales.list_price - sales.discount_amount - sales.sale_price).abs() > 0.02, detail_values=sales.sale_id))
            rows.append(_check_row("sales", "gross_profit equals sale_price minus vehicle_cost", (sales.sale_price - sales.vehicle_cost - sales.gross_profit).abs() > 0.02, detail_values=sales.sale_id))

    if "service_orders" in datasets:
        orders = datasets["service_orders"]
        dates = {column: _safe_date_series(orders, column) for column in ("opened_at", "promised_at", "completed_at") if column in orders}
        if {"opened_at", "promised_at", "completed_at"} <= set(dates):
            rows.append(_check_row("service_orders", "opened_at is on or before promised_at", dates["opened_at"] > dates["promised_at"], detail_values=orders.service_order_id))
            rows.append(_check_row("service_orders", "opened_at is on or before completed_at", dates["opened_at"] > dates["completed_at"], detail_values=orders.service_order_id))
        needed = {"labor_revenue", "parts_revenue", "discount_amount", "service_revenue"}
        if needed <= set(orders):
            expected = orders.labor_revenue + orders.parts_revenue - orders.discount_amount
            rows.append(_check_row("service_orders", "service_revenue matches components", (expected - orders.service_revenue).abs() > 0.02, detail_values=orders.service_order_id))

    if "service_orders" in datasets and "service_appointments" in datasets:
        orders = datasets["service_orders"]
        appointments = datasets["service_appointments"]
        shared = ["customer_id", "vehicle_id", "dealership_id", "service_advisor_id"]
        if "appointment_id" in orders and {"appointment_id", *shared} <= set(appointments) and set(shared) <= set(orders):
            merged = orders[["service_order_id", "appointment_id", *shared]].merge(
                appointments[["appointment_id", *shared]], on="appointment_id", how="left", suffixes=("_order", "_appointment")
            )
            for column in shared:
                mismatch = merged[f"{column}_order"] != merged[f"{column}_appointment"]
                rows.append(_check_row("service_orders", f"{column} matches appointment", mismatch, detail_values=merged.service_order_id))

    return pd.DataFrame(rows)


def _write_markdown_summary(
    output_path: Path,
    dataset_profile: pd.DataFrame,
    column_profile: pd.DataFrame,
    validation: pd.DataFrame,
    foreign_keys: pd.DataFrame,
) -> None:
    errors = validation[(validation.severity == "ERROR") & (validation.status == "FAIL")]
    failed_fks = foreign_keys[foreign_keys.status != "PASS"]
    lines = [
        "# Raw Data Profiling Summary",
        "",
        f"- Datasets profiled: {len(dataset_profile)}",
        f"- Rows profiled: {int(dataset_profile.row_count.sum()):,}",
        f"- Columns profiled: {len(column_profile)}",
        f"- Validation errors: {int(errors.invalid_count.sum())}",
        f"- Failed/not-checked foreign keys: {len(failed_fks)}",
        f"- Overall status: **{'PASS' if errors.empty and failed_fks.empty else 'FAIL'}**",
        "",
        "## Dataset overview",
        "",
        _to_markdown_table(dataset_profile),
        "",
        "## Failed validation checks",
        "",
        "None." if errors.empty else _to_markdown_table(errors),
        "",
        "## Failed or untested foreign keys",
        "",
        "None." if failed_fks.empty else _to_markdown_table(failed_fks),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def profile_raw_data(raw_dir: str | Path, output_dir: str | Path) -> ProfileResult:
    """Profile all raw CSVs, persist reports, and return the overall result."""

    datasets = load_datasets(raw_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    dataset_profile = build_dataset_profile(datasets)
    column_profile = build_column_profile(datasets)
    validation = build_validation_report(datasets)
    foreign_keys = build_foreign_key_report(datasets)

    paths = {
        "dataset_profile": destination / "dataset_profile.csv",
        "column_profile": destination / "column_profile.csv",
        "validation_report": destination / "validation_report.csv",
        "foreign_key_report": destination / "foreign_key_report.csv",
        "summary": destination / "profiling_summary.md",
        "manifest": destination / "profiling_manifest.json",
    }
    dataset_profile.to_csv(paths["dataset_profile"], index=False)
    column_profile.to_csv(paths["column_profile"], index=False)
    validation.to_csv(paths["validation_report"], index=False)
    foreign_keys.to_csv(paths["foreign_key_report"], index=False)
    _write_markdown_summary(paths["summary"], dataset_profile, column_profile, validation, foreign_keys)

    errors = validation[(validation.severity == "ERROR") & (validation.status == "FAIL")]
    failed_fks = foreign_keys[foreign_keys.status != "PASS"]
    error_count = int(errors.invalid_count.sum()) + len(failed_fks)
    passed = error_count == 0
    manifest = {
        "source_directory": str(Path(raw_dir)),
        "datasets_profiled": len(dataset_profile),
        "rows_profiled": int(dataset_profile.row_count.sum()),
        "columns_profiled": len(column_profile),
        "error_count": error_count,
        "status": "PASS" if passed else "FAIL",
        "reports": {name: str(path) for name, path in paths.items() if name != "manifest"},
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return ProfileResult(paths, passed, error_count)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/profiling"))
    args = parser.parse_args()
    result = profile_raw_data(args.raw_dir, args.output_dir)
    print(f"Profiling status: {'PASS' if result.passed else 'FAIL'}")
    print(f"Validation errors: {result.error_count}")
    for name, path in result.report_paths.items():
        print(f"{name}: {path}")
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
