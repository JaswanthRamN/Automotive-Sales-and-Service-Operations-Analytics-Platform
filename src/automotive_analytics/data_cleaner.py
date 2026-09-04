"""Deterministic cleaning pipeline for automotive CSV datasets."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from automotive_analytics.data_profiler import (
    ALLOWED_VALUES,
    DATE_COLUMNS,
    FOREIGN_KEYS,
    NONNEGATIVE_COLUMNS,
    PRIMARY_KEYS,
    build_foreign_key_report,
    build_validation_report,
    load_datasets,
)


NUMERIC_COLUMNS = {
    "vehicles": ["model_year", "mileage_at_acquisition", "manufacturer_msrp"],
    "sales": ["list_price", "discount_amount", "sale_price", "vehicle_cost", "gross_profit"],
    "inventory": ["carrying_cost", "days_in_inventory"],
    "service_orders": ["labor_revenue", "parts_revenue", "discount_amount", "service_revenue"],
}

BOOLEAN_COLUMNS = {"inventory": ["slow_moving_flag"]}

CRITICAL_COLUMNS = {
    "customers": ["customer_id", "customer_since_date"],
    "vehicles": ["vehicle_id", "vin", "model_year", "manufacturer_msrp"],
    "dealerships": ["dealership_id", "opened_date"],
    "employees": ["employee_id", "dealership_id", "role", "hire_date"],
    "sales": ["sale_id", "sale_date", "customer_id", "vehicle_id", "dealership_id", "salesperson_id", "list_price", "discount_amount", "sale_price", "vehicle_cost", "gross_profit"],
    "inventory": ["inventory_id", "snapshot_date", "vehicle_id", "dealership_id", "acquired_date", "carrying_cost", "days_in_inventory", "slow_moving_flag"],
    "service_appointments": ["appointment_id", "customer_id", "vehicle_id", "dealership_id", "service_advisor_id", "appointment_date", "appointment_status"],
    "service_orders": ["service_order_id", "appointment_id", "customer_id", "vehicle_id", "dealership_id", "service_advisor_id", "technician_id", "opened_at", "promised_at", "completed_at", "labor_revenue", "parts_revenue", "discount_amount", "service_revenue"],
}

IDENTIFIER_COLUMNS = {
    "customer_id",
    "vehicle_id",
    "dealership_id",
    "employee_id",
    "sale_id",
    "inventory_id",
    "appointment_id",
    "service_order_id",
    "salesperson_id",
    "service_advisor_id",
    "technician_id",
    "vin",
}


@dataclass(frozen=True)
class CleaningResult:
    output_paths: dict[str, Path]
    audit_path: Path
    log_path: Path
    rows_read: int
    rows_written: int


class Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def record(self, dataset: str, action: str, count: int, details: str = "") -> None:
        if count:
            self.rows.append(
                {"dataset": dataset, "action": action, "affected_rows": int(count), "details": details}
            )

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            self.rows,
            columns=["dataset", "action", "affected_rows", "details"],
        )


def _configure_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("automotive_analytics.data_cleaner")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def _standardize_strings(name: str, frame: pd.DataFrame, audit: Audit) -> pd.DataFrame:
    result = frame.copy()
    for column in result.select_dtypes(include=["object", "string"]).columns:
        original = result[column].copy()
        result[column] = result[column].astype("string").str.strip()
        result[column] = result[column].replace(r"^\s*$", pd.NA, regex=True)
        if column in IDENTIFIER_COLUMNS:
            result[column] = result[column].str.upper()
        elif column == "email":
            result[column] = result[column].str.lower()
        changed = int((original.astype("string").fillna("") != result[column].fillna("")).sum())
        audit.record(name, "standardized string values", changed, column)
    return result


def _coerce_types(name: str, frame: pd.DataFrame, audit: Audit) -> pd.DataFrame:
    result = frame.copy()
    for column in DATE_COLUMNS.get(name, []):
        if column in result:
            original_nonnull = result[column].notna()
            result[column] = pd.to_datetime(result[column], errors="coerce", format="mixed")
            audit.record(name, "invalid date coerced to null", int((original_nonnull & result[column].isna()).sum()), column)
    for column in NUMERIC_COLUMNS.get(name, []):
        if column in result:
            original_nonnull = result[column].notna()
            result[column] = pd.to_numeric(result[column], errors="coerce")
            audit.record(name, "invalid number coerced to null", int((original_nonnull & result[column].isna()).sum()), column)
    for column in BOOLEAN_COLUMNS.get(name, []):
        if column in result:
            mapped = result[column].astype("string").str.strip().str.lower().map(
                {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}
            )
            audit.record(name, "invalid boolean coerced to null", int((result[column].notna() & mapped.isna()).sum()), column)
            result[column] = mapped.astype("boolean")
    return result


def _standardize_categories(name: str, frame: pd.DataFrame, audit: Audit) -> pd.DataFrame:
    result = frame.copy()
    for (dataset, column), allowed in ALLOWED_VALUES.items():
        if dataset != name or column not in result:
            continue
        canonical = {value.casefold(): value for value in allowed}
        original = result[column].copy()
        normalized = result[column].astype("string").str.strip().str.casefold().map(canonical)
        result[column] = normalized.astype("string")
        changed = int((original.astype("string").fillna("") != result[column].fillna("")).sum())
        audit.record(name, "standardized category", changed, column)
    return result


def _drop_bad_rows(name: str, frame: pd.DataFrame, audit: Audit) -> pd.DataFrame:
    result = frame.copy()
    exact_duplicates = result.duplicated()
    audit.record(name, "removed duplicate rows", int(exact_duplicates.sum()))
    result = result.loc[~exact_duplicates].copy()

    key = PRIMARY_KEYS.get(name)
    if key in result:
        duplicate_keys = result[key].notna() & result[key].duplicated(keep="first")
        audit.record(name, "removed duplicate primary keys", int(duplicate_keys.sum()), key)
        result = result.loc[~duplicate_keys].copy()

    for column in NONNEGATIVE_COLUMNS.get(name, []):
        if column in result:
            invalid = result[column] < 0
            audit.record(name, "invalid negative value set to null", int(invalid.fillna(False).sum()), column)
            result.loc[invalid.fillna(False), column] = pd.NA

    critical = [column for column in CRITICAL_COLUMNS.get(name, []) if column in result]
    if critical:
        missing = result[critical].isna().any(axis=1)
        audit.record(name, "removed rows missing critical values", int(missing.sum()), ", ".join(critical))
        result = result.loc[~missing].copy()

    for column in result.select_dtypes(include=["object", "string"]).columns:
        if column not in critical:
            missing = int(result[column].isna().sum())
            if missing:
                result[column] = result[column].fillna("Unknown")
                audit.record(name, "filled missing descriptive values", missing, column)
    return result.reset_index(drop=True)


def _repair_derived_values(datasets: dict[str, pd.DataFrame], audit: Audit) -> None:
    if "sales" in datasets:
        frame = datasets["sales"]
        expected_sale_price = (frame.list_price - frame.discount_amount).round(2)
        changed = (frame.sale_price - expected_sale_price).abs() > 0.02
        frame.loc[changed, "sale_price"] = expected_sale_price.loc[changed]
        audit.record("sales", "recalculated sale_price", int(changed.sum()))
        expected_profit = (frame.sale_price - frame.vehicle_cost).round(2)
        changed = (frame.gross_profit - expected_profit).abs() > 0.02
        frame.loc[changed, "gross_profit"] = expected_profit.loc[changed]
        audit.record("sales", "recalculated gross_profit", int(changed.sum()))

    if "inventory" in datasets:
        frame = datasets["inventory"]
        invalid_order = frame.acquired_date > frame.snapshot_date
        audit.record("inventory", "removed rows with acquisition after snapshot", int(invalid_order.sum()))
        frame = frame.loc[~invalid_order].copy()
        expected_days = (frame.snapshot_date - frame.acquired_date).dt.days
        changed = frame.days_in_inventory != expected_days
        frame.loc[changed, "days_in_inventory"] = expected_days.loc[changed]
        audit.record("inventory", "recalculated days_in_inventory", int(changed.sum()))
        expected_flag = expected_days > 90
        changed = frame.slow_moving_flag != expected_flag
        frame.loc[changed, "slow_moving_flag"] = expected_flag.loc[changed]
        audit.record("inventory", "recalculated slow_moving_flag", int(changed.sum()))
        datasets["inventory"] = frame.reset_index(drop=True)

    if "service_orders" in datasets:
        frame = datasets["service_orders"]
        valid_order = (frame.opened_at <= frame.promised_at) & (frame.opened_at <= frame.completed_at)
        audit.record("service_orders", "removed rows with invalid timestamp order", int((~valid_order).sum()))
        frame = frame.loc[valid_order].copy()
        expected = (frame.labor_revenue + frame.parts_revenue - frame.discount_amount).round(2)
        changed = (frame.service_revenue - expected).abs() > 0.02
        frame.loc[changed, "service_revenue"] = expected.loc[changed]
        audit.record("service_orders", "recalculated service_revenue", int(changed.sum()))
        datasets["service_orders"] = frame.reset_index(drop=True)


def _drop_orphans(datasets: dict[str, pd.DataFrame], audit: Audit) -> None:
    for child, child_column, parent, parent_column in FOREIGN_KEYS:
        if child not in datasets or parent not in datasets:
            continue
        child_frame, parent_frame = datasets[child], datasets[parent]
        if child_column not in child_frame or parent_column not in parent_frame:
            continue
        orphan = ~child_frame[child_column].isin(set(parent_frame[parent_column].dropna()))
        audit.record(child, "removed broken foreign-key rows", int(orphan.sum()), f"{child_column} -> {parent}.{parent_column}")
        datasets[child] = child_frame.loc[~orphan].reset_index(drop=True)


def _enforce_business_relationships(datasets: dict[str, pd.DataFrame], audit: Audit) -> None:
    if "employees" in datasets:
        roles = datasets["employees"].set_index("employee_id")["role"]
        role_links = [
            ("sales", "salesperson_id", "Sales Consultant"),
            ("service_appointments", "service_advisor_id", "Service Advisor"),
            ("service_orders", "service_advisor_id", "Service Advisor"),
            ("service_orders", "technician_id", "Service Technician"),
        ]
        for dataset, column, role in role_links:
            if dataset in datasets and column in datasets[dataset]:
                frame = datasets[dataset]
                invalid = frame[column].map(roles) != role
                audit.record(dataset, "removed rows with invalid employee role", int(invalid.sum()), f"{column} requires {role}")
                datasets[dataset] = frame.loc[~invalid].reset_index(drop=True)

    if "service_orders" in datasets and "service_appointments" in datasets:
        orders = datasets["service_orders"]
        appointments = datasets["service_appointments"].set_index("appointment_id")
        shared = ["customer_id", "vehicle_id", "dealership_id", "service_advisor_id"]
        for column in shared:
            expected = orders.appointment_id.map(appointments[column])
            changed = orders[column] != expected
            orders.loc[changed, column] = expected.loc[changed]
            audit.record("service_orders", "reconciled value to appointment", int(changed.sum()), column)
        datasets["service_orders"] = orders

    if "sales" in datasets and "inventory" in datasets:
        sold = set(datasets["sales"].vehicle_id)
        inventory = datasets["inventory"]
        overlap = inventory.vehicle_id.isin(sold)
        audit.record("inventory", "removed vehicles also present in sales", int(overlap.sum()))
        datasets["inventory"] = inventory.loc[~overlap].reset_index(drop=True)

    if "sales" in datasets and "customers" in datasets and "vehicles" in datasets:
        sales = datasets["sales"]
        customer_dates = datasets["customers"].set_index("customer_id").customer_since_date
        model_years = datasets["vehicles"].set_index("vehicle_id").model_year
        invalid = (sales.sale_date < sales.customer_id.map(customer_dates)) | (
            sales.sale_date.dt.year < sales.vehicle_id.map(model_years) - 1
        )
        audit.record("sales", "removed rows with invalid relational dates", int(invalid.sum()))
        datasets["sales"] = sales.loc[~invalid].reset_index(drop=True)


def clean_datasets(datasets: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Clean in-memory datasets and return them with an audit report."""

    audit = Audit()
    cleaned: dict[str, pd.DataFrame] = {}
    for name, frame in datasets.items():
        normalized = frame.rename(columns=lambda value: str(value).strip().lower())
        normalized = _standardize_strings(name, normalized, audit)
        normalized = _coerce_types(name, normalized, audit)
        normalized = _standardize_categories(name, normalized, audit)
        cleaned[name] = _drop_bad_rows(name, normalized, audit)

    _repair_derived_values(cleaned, audit)
    _drop_orphans(cleaned, audit)
    _enforce_business_relationships(cleaned, audit)
    _drop_orphans(cleaned, audit)
    return cleaned, audit.frame()


def _format_dates(frame: pd.DataFrame, dataset: str) -> pd.DataFrame:
    result = frame.copy()
    for column in DATE_COLUMNS.get(dataset, []):
        if column in result:
            includes_time = column in {"opened_at", "promised_at", "completed_at"}
            result[column] = result[column].dt.strftime("%Y-%m-%d %H:%M:%S" if includes_time else "%Y-%m-%d")
    return result


def clean_raw_data(
    raw_dir: str | Path,
    output_dir: str | Path,
    log_path: str | Path,
) -> CleaningResult:
    """Load, clean, validate, and write all automotive datasets."""

    logger = _configure_logger(Path(log_path))
    raw = load_datasets(raw_dir)
    rows_read = sum(len(frame) for frame in raw.values())
    logger.info("Loaded %s datasets containing %s rows", len(raw), rows_read)
    cleaned, audit = clean_datasets(raw)

    validation = build_validation_report(cleaned)
    foreign_keys = build_foreign_key_report(cleaned)
    failed_validation = validation[(validation.severity == "ERROR") & (validation.status == "FAIL")]
    failed_foreign_keys = foreign_keys[foreign_keys.status != "PASS"]
    if not failed_validation.empty or not failed_foreign_keys.empty:
        logger.error("Cleaned data failed validation: %s checks, %s foreign keys", len(failed_validation), len(failed_foreign_keys))
        raise ValueError("Cleaned datasets failed validation")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, frame in sorted(cleaned.items()):
        path = destination / f"{name}.csv"
        _format_dates(frame, name).to_csv(path, index=False)
        paths[name] = path
        logger.info("Wrote %s cleaned rows to %s", len(frame), path)
    audit_path = destination / "cleaning_summary.csv"
    audit.to_csv(audit_path, index=False)
    rows_written = sum(len(frame) for frame in cleaned.values())
    logger.info("Cleaning complete: %s rows read, %s rows written", rows_read, rows_written)
    return CleaningResult(paths, audit_path, Path(log_path), rows_read, rows_written)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--log-path", type=Path, default=Path("logs/data_cleaning.log"))
    args = parser.parse_args()
    result = clean_raw_data(args.raw_dir, args.output_dir, args.log_path)
    print(f"Rows read: {result.rows_read}")
    print(f"Rows written: {result.rows_written}")
    for name, path in result.output_paths.items():
        print(f"{name}: {path}")
    print(f"audit: {result.audit_path}")
    print(f"log: {result.log_path}")


if __name__ == "__main__":
    main()
