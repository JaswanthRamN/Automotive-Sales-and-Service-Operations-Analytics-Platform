from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from automotive_analytics.data_generator import GeneratorConfig, generate_datasets


SMALL_CONFIG = GeneratorConfig(
    seed=7,
    customers=40,
    vehicles=80,
    dealerships=2,
    employees=20,
    sales=50,
    inventory=30,
    service_appointments=60,
    service_orders=50,
)


def test_generation_is_reproducible() -> None:
    first = generate_datasets(SMALL_CONFIG)
    second = generate_datasets(SMALL_CONFIG)

    for name in first:
        pd.testing.assert_frame_equal(first[name], second[name])


def test_row_counts_and_primary_keys() -> None:
    datasets = generate_datasets(SMALL_CONFIG)
    expected_counts = {
        "customers": SMALL_CONFIG.customers,
        "vehicles": SMALL_CONFIG.vehicles,
        "dealerships": SMALL_CONFIG.dealerships,
        "employees": SMALL_CONFIG.employees,
        "sales": SMALL_CONFIG.sales,
        "inventory": SMALL_CONFIG.inventory,
        "service_appointments": SMALL_CONFIG.service_appointments,
        "service_orders": SMALL_CONFIG.service_orders,
    }
    primary_keys = {
        "customers": "customer_id",
        "vehicles": "vehicle_id",
        "dealerships": "dealership_id",
        "employees": "employee_id",
        "sales": "sale_id",
        "inventory": "inventory_id",
        "service_appointments": "appointment_id",
        "service_orders": "service_order_id",
    }

    for name, frame in datasets.items():
        key = primary_keys[name]
        assert len(frame) == expected_counts[name]
        assert frame[key].notna().all()
        assert frame[key].is_unique


def test_foreign_keys_are_valid() -> None:
    data = generate_datasets(SMALL_CONFIG)

    assert set(data["employees"].dealership_id) <= set(data["dealerships"].dealership_id)
    for frame_name in ("sales", "service_appointments", "service_orders"):
        assert set(data[frame_name].customer_id) <= set(data["customers"].customer_id)
        assert set(data[frame_name].vehicle_id) <= set(data["vehicles"].vehicle_id)
        assert set(data[frame_name].dealership_id) <= set(data["dealerships"].dealership_id)
    assert set(data["inventory"].vehicle_id) <= set(data["vehicles"].vehicle_id)
    assert set(data["inventory"].dealership_id) <= set(data["dealerships"].dealership_id)
    assert set(data["sales"].salesperson_id) <= set(data["employees"].employee_id)
    assert set(data["service_appointments"].service_advisor_id) <= set(data["employees"].employee_id)
    assert set(data["service_orders"].appointment_id) <= set(data["service_appointments"].appointment_id)
    assert set(data["service_orders"].technician_id) <= set(data["employees"].employee_id)


def test_dates_and_calculated_values_are_consistent() -> None:
    data = generate_datasets(SMALL_CONFIG)
    sales = data["sales"]
    inventory = data["inventory"]
    orders = data["service_orders"]
    customers = data["customers"].set_index("customer_id")
    vehicles = data["vehicles"].set_index("vehicle_id")

    assert sales.sale_date.between(SMALL_CONFIG.start_date, SMALL_CONFIG.end_date).all()
    assert all(
        row.sale_date >= customers.loc[row.customer_id, "customer_since_date"]
        for row in sales.itertuples()
    )
    assert all(
        row.sale_date.year >= vehicles.loc[row.vehicle_id, "model_year"] - 1
        for row in sales.itertuples()
    )
    assert (sales.sale_price > 0).all()
    assert ((sales.sale_price - sales.vehicle_cost - sales.gross_profit).abs() <= 0.02).all()
    assert (inventory.acquired_date <= inventory.snapshot_date).all()
    expected_days = (pd.to_datetime(inventory.snapshot_date) - pd.to_datetime(inventory.acquired_date)).dt.days
    assert (inventory.days_in_inventory == expected_days).all()
    assert (inventory.slow_moving_flag == (inventory.days_in_inventory > 90)).all()
    assert (orders.opened_at <= orders.completed_at).all()
    assert (orders.completed_at.dt.date <= SMALL_CONFIG.end_date).all()
    expected_revenue = orders.labor_revenue + orders.parts_revenue - orders.discount_amount
    assert ((orders.service_revenue - expected_revenue).abs() <= 0.02).all()


def test_inventory_and_sold_vehicles_do_not_overlap() -> None:
    data = generate_datasets(SMALL_CONFIG)

    assert set(data["inventory"].vehicle_id).isdisjoint(set(data["sales"].vehicle_id))
