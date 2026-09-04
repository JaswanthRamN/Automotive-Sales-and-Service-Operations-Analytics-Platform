from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from automotive_analytics.data_cleaner import clean_datasets, clean_raw_data
from automotive_analytics.data_generator import GeneratorConfig, generate_datasets, write_datasets
from automotive_analytics.data_profiler import build_foreign_key_report, build_validation_report


CONFIG = GeneratorConfig(
    seed=31,
    customers=40,
    vehicles=80,
    dealerships=2,
    employees=20,
    sales=50,
    inventory=30,
    service_appointments=60,
    service_orders=50,
)


def test_cleaner_preserves_valid_data() -> None:
    raw = generate_datasets(CONFIG)
    cleaned, audit = clean_datasets(raw)

    assert {name: len(frame) for name, frame in cleaned.items()} == {
        name: len(frame) for name, frame in raw.items()
    }
    removal_actions = audit[audit.action.str.startswith("removed", na=False)]
    assert removal_actions.empty
    assert (build_validation_report(cleaned).status == "PASS").all()
    assert (build_foreign_key_report(cleaned).status == "PASS").all()


def test_cleaner_repairs_values_and_removes_bad_rows() -> None:
    raw = generate_datasets(CONFIG)
    raw["customers"].loc[0, "first_name"] = "  Alex  "
    raw["customers"].loc[1, "customer_type"] = " individual "
    raw["customers"] = pd.concat([raw["customers"], raw["customers"].iloc[[2]]], ignore_index=True)
    raw["vehicles"]["manufacturer_msrp"] = raw["vehicles"]["manufacturer_msrp"].astype("object")
    raw["vehicles"].loc[0, "manufacturer_msrp"] = "not-a-number"
    raw["sales"].loc[0, "gross_profit"] = 999_999
    raw["sales"].loc[1, "customer_id"] = "missing-customer"
    raw["inventory"].loc[0, "days_in_inventory"] = -5
    raw["service_orders"].loc[0, "customer_id"] = raw["customers"].loc[3, "customer_id"]
    raw["service_orders"].loc[1, "service_revenue"] = -1

    cleaned, audit = clean_datasets(raw)

    assert cleaned["customers"].loc[0, "first_name"] == "Alex"
    assert cleaned["customers"].loc[1, "customer_type"] == "Individual"
    assert cleaned["customers"].customer_id.is_unique
    assert raw["vehicles"].loc[0, "vehicle_id"] not in set(cleaned["vehicles"].vehicle_id)
    assert raw["sales"].loc[1, "sale_id"] not in set(cleaned["sales"].sale_id)
    assert raw["inventory"].loc[0, "inventory_id"] not in set(cleaned["inventory"].inventory_id)
    appointment = cleaned["service_appointments"].set_index("appointment_id")
    order = cleaned["service_orders"].set_index("service_order_id").loc[raw["service_orders"].loc[0, "service_order_id"]]
    assert order.customer_id == appointment.loc[order.appointment_id, "customer_id"]
    assert not audit.empty
    assert (build_validation_report(cleaned).status == "PASS").all()
    assert (build_foreign_key_report(cleaned).status == "PASS").all()


def test_clean_raw_data_writes_outputs_audit_and_log(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    write_datasets(raw_dir, CONFIG)

    result = clean_raw_data(raw_dir, tmp_path / "processed", tmp_path / "logs" / "cleaning.log")

    assert result.rows_read == result.rows_written
    assert len(result.output_paths) == 8
    assert all(path.is_file() and path.stat().st_size > 0 for path in result.output_paths.values())
    assert result.audit_path.is_file()
    assert result.log_path.is_file() and "Cleaning complete" in result.log_path.read_text(encoding="utf-8")


def test_cleaner_drops_invalid_dates_and_relationships() -> None:
    raw = generate_datasets(CONFIG)
    bad_appointment = raw["service_appointments"].loc[0, "appointment_id"]
    raw["service_appointments"].loc[0, "appointment_date"] = "invalid-date"
    raw["employees"].loc[0, "dealership_id"] = "DLR-MISSING"

    cleaned, _ = clean_datasets(raw)

    assert bad_appointment not in set(cleaned["service_appointments"].appointment_id)
    assert bad_appointment not in set(cleaned["service_orders"].appointment_id)
    assert (build_foreign_key_report(cleaned).status == "PASS").all()
