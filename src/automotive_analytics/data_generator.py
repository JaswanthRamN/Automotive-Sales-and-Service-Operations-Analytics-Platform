"""Deterministic synthetic data generation for automotive analytics."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker


@dataclass(frozen=True)
class GeneratorConfig:
    """Row counts and seed used to create a coherent synthetic dataset."""

    seed: int = 42
    customers: int = 12_000
    vehicles: int = 20_000
    dealerships: int = 8
    employees: int = 160
    sales: int = 15_500
    inventory: int = 4_500
    service_appointments: int = 17_000
    service_orders: int = 15_500
    start_date: date = date(2022, 1, 1)
    end_date: date = date(2026, 8, 31)

    def validate(self) -> None:
        if min(
            self.customers,
            self.vehicles,
            self.dealerships,
            self.employees,
            self.sales,
            self.inventory,
            self.service_appointments,
            self.service_orders,
        ) <= 0:
            raise ValueError("All row counts must be positive")
        if self.sales + self.inventory > self.vehicles:
            raise ValueError("vehicles must be at least sales + inventory")
        if self.service_orders > self.service_appointments:
            raise ValueError("service_orders cannot exceed service_appointments")
        if self.employees < self.dealerships * 3:
            raise ValueError("employees must allow core roles at every dealership")
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")


VEHICLE_CATALOG = {
    "Toyota": [("Camry", "Sedan"), ("RAV4", "SUV"), ("Tacoma", "Truck")],
    "Honda": [("Civic", "Sedan"), ("CR-V", "SUV"), ("Pilot", "SUV")],
    "Ford": [("F-150", "Truck"), ("Escape", "SUV"), ("Mustang", "Coupe")],
    "Chevrolet": [("Silverado", "Truck"), ("Equinox", "SUV"), ("Malibu", "Sedan")],
    "Nissan": [("Altima", "Sedan"), ("Rogue", "SUV"), ("Frontier", "Truck")],
    "Hyundai": [("Elantra", "Sedan"), ("Tucson", "SUV"), ("Santa Fe", "SUV")],
    "Kia": [("K5", "Sedan"), ("Sportage", "SUV"), ("Telluride", "SUV")],
    "Subaru": [("Outback", "Wagon"), ("Forester", "SUV"), ("Impreza", "Hatchback")],
}

DEALERSHIP_LOCATIONS = [
    ("Atlanta", "GA"),
    ("Austin", "TX"),
    ("Charlotte", "NC"),
    ("Chicago", "IL"),
    ("Denver", "CO"),
    ("Nashville", "TN"),
    ("Orlando", "FL"),
    ("Phoenix", "AZ"),
    ("Raleigh", "NC"),
    ("Seattle", "WA"),
]


def _identifier(prefix: str, number: int, width: int = 6) -> str:
    return f"{prefix}{number:0{width}d}"


def _random_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _money(value: float) -> float:
    return round(value, 2)


def _build_dealerships(config: GeneratorConfig, fake: Faker) -> pd.DataFrame:
    rows = []
    for index in range(config.dealerships):
        city, state = DEALERSHIP_LOCATIONS[index % len(DEALERSHIP_LOCATIONS)]
        rows.append(
            {
                "dealership_id": _identifier("DLR", index + 1, 3),
                "dealership_name": f"{city} Premier Auto {index + 1}",
                "city": city,
                "state": state,
                "postal_code": fake.postcode(),
                "region": "South" if state in {"GA", "TX", "NC", "TN", "FL"} else "West" if state in {"CO", "AZ", "WA"} else "Midwest",
                "opened_date": date(2010 + index % 10, 1 + index % 12, 1),
            }
        )
    return pd.DataFrame(rows)


def _build_employees(
    config: GeneratorConfig, fake: Faker, rng: random.Random, dealerships: pd.DataFrame
) -> pd.DataFrame:
    dealership_ids = dealerships["dealership_id"].tolist()
    role_cycle = ["Sales Consultant", "Service Advisor", "Service Technician", "Inventory Specialist", "Manager"]
    rows = []
    for index in range(config.employees):
        dealership_id = dealership_ids[index % len(dealership_ids)]
        rows.append(
            {
                "employee_id": _identifier("EMP", index + 1),
                "dealership_id": dealership_id,
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "role": role_cycle[index % len(role_cycle)],
                "hire_date": _random_date(rng, date(2015, 1, 1), date(2021, 12, 31)),
                "employment_status": "Active" if rng.random() < 0.94 else "Inactive",
            }
        )
    return pd.DataFrame(rows)


def _build_customers(config: GeneratorConfig, fake: Faker, rng: random.Random) -> pd.DataFrame:
    rows = []
    for index in range(config.customers):
        created_date = _random_date(rng, date(2017, 1, 1), config.end_date - timedelta(days=30))
        rows.append(
            {
                "customer_id": _identifier("CUS", index + 1),
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "email": f"customer{index + 1:06d}@example.com",
                "phone": fake.numerify("###-###-####"),
                "city": fake.city(),
                "state": fake.state_abbr(),
                "postal_code": fake.postcode(),
                "customer_since_date": created_date,
                "customer_type": rng.choices(["Individual", "Business", "Fleet"], weights=[88, 8, 4])[0],
            }
        )
    return pd.DataFrame(rows)


def _build_vehicles(config: GeneratorConfig, rng: random.Random) -> pd.DataFrame:
    makes = list(VEHICLE_CATALOG)
    colors = ["Black", "White", "Silver", "Gray", "Blue", "Red", "Green"]
    fuel_types = ["Gasoline", "Hybrid", "Electric", "Diesel"]
    rows = []
    for index in range(config.vehicles):
        make = rng.choice(makes)
        model, body_type = rng.choice(VEHICLE_CATALOG[make])
        model_year = rng.randint(2015, config.end_date.year + 1)
        condition = rng.choices(["New", "Used"], weights=[62, 38])[0]
        mileage = 0 if condition == "New" else rng.randint(2_000, 110_000)
        rows.append(
            {
                "vehicle_id": _identifier("VEH", index + 1),
                "vin": f"SYN{config.seed:03d}{index + 1:011d}"[-17:],
                "make": make,
                "model": model,
                "model_year": model_year,
                "body_type": body_type,
                "fuel_type": rng.choices(fuel_types, weights=[71, 15, 9, 5])[0],
                "color": rng.choice(colors),
                "vehicle_condition": condition,
                "mileage_at_acquisition": mileage,
                "manufacturer_msrp": _money(rng.uniform(24_000, 78_000)),
            }
        )
    return pd.DataFrame(rows)


def _employee_lookup(employees: pd.DataFrame, role: str) -> dict[str, list[str]]:
    selected = employees.loc[employees["role"] == role]
    return selected.groupby("dealership_id")["employee_id"].apply(list).to_dict()


def _build_sales(
    config: GeneratorConfig,
    rng: random.Random,
    customers: pd.DataFrame,
    vehicles: pd.DataFrame,
    dealerships: pd.DataFrame,
    employees: pd.DataFrame,
) -> pd.DataFrame:
    customer_ids = customers["customer_id"].tolist()
    customer_start = customers.set_index("customer_id")["customer_since_date"].to_dict()
    dealership_ids = dealerships["dealership_id"].tolist()
    salespeople = _employee_lookup(employees, "Sales Consultant")
    vehicle_records = vehicles.iloc[: config.sales].to_dict("records")
    rows = []
    for index, vehicle in enumerate(vehicle_records):
        dealership_id = rng.choice(dealership_ids)
        customer_id = rng.choice(customer_ids)
        earliest_model_sale = date(int(vehicle["model_year"]) - 1, 7, 1)
        earliest_sale = max(
            config.start_date, customer_start[customer_id], earliest_model_sale
        )
        sale_date = _random_date(rng, earliest_sale, config.end_date)
        base_price = float(vehicle["manufacturer_msrp"])
        age = max(0, sale_date.year - int(vehicle["model_year"]))
        condition_factor = 1.0 if vehicle["vehicle_condition"] == "New" else max(0.35, 0.86 - age * 0.055)
        list_price = base_price * condition_factor * rng.uniform(0.94, 1.08)
        discount = list_price * rng.uniform(0.0, 0.09)
        sale_price = list_price - discount
        vehicle_cost = sale_price * rng.uniform(0.78, 0.94)
        rows.append(
            {
                "sale_id": _identifier("SAL", index + 1),
                "sale_date": sale_date,
                "customer_id": customer_id,
                "vehicle_id": vehicle["vehicle_id"],
                "dealership_id": dealership_id,
                "salesperson_id": rng.choice(salespeople[dealership_id]),
                "sales_channel": rng.choices(["Showroom", "Online", "Fleet", "Partner"], weights=[61, 25, 9, 5])[0],
                "list_price": _money(list_price),
                "discount_amount": _money(discount),
                "sale_price": _money(sale_price),
                "vehicle_cost": _money(vehicle_cost),
                "gross_profit": _money(sale_price - vehicle_cost),
                "payment_type": rng.choices(["Finance", "Cash", "Lease"], weights=[62, 23, 15])[0],
                "sale_status": "Completed",
            }
        )
    return pd.DataFrame(rows)


def _build_inventory(
    config: GeneratorConfig,
    rng: random.Random,
    vehicles: pd.DataFrame,
    dealerships: pd.DataFrame,
) -> pd.DataFrame:
    dealership_ids = dealerships["dealership_id"].tolist()
    vehicle_records = vehicles.iloc[config.sales : config.sales + config.inventory].to_dict("records")
    rows = []
    for index, vehicle in enumerate(vehicle_records):
        acquired_date = _random_date(rng, config.end_date - timedelta(days=240), config.end_date)
        days_in_inventory = (config.end_date - acquired_date).days
        carrying_cost = float(vehicle["manufacturer_msrp"]) * rng.uniform(0.68, 0.9)
        rows.append(
            {
                "inventory_id": _identifier("INV", index + 1),
                "snapshot_date": config.end_date,
                "vehicle_id": vehicle["vehicle_id"],
                "dealership_id": rng.choice(dealership_ids),
                "acquired_date": acquired_date,
                "inventory_status": rng.choices(["Available", "Reserved", "In Transit", "Demonstrator"], weights=[76, 12, 7, 5])[0],
                "carrying_cost": _money(carrying_cost),
                "days_in_inventory": days_in_inventory,
                "slow_moving_flag": days_in_inventory > 90,
            }
        )
    return pd.DataFrame(rows)


def _build_service_appointments(
    config: GeneratorConfig,
    rng: random.Random,
    customers: pd.DataFrame,
    vehicles: pd.DataFrame,
    dealerships: pd.DataFrame,
    employees: pd.DataFrame,
) -> pd.DataFrame:
    customer_ids = customers["customer_id"].tolist()
    customer_start = customers.set_index("customer_id")["customer_since_date"].to_dict()
    vehicle_ids = vehicles["vehicle_id"].tolist()
    dealership_ids = dealerships["dealership_id"].tolist()
    advisors = _employee_lookup(employees, "Service Advisor")
    rows = []
    for index in range(config.service_appointments):
        customer_id = rng.choice(customer_ids)
        dealership_id = rng.choice(dealership_ids)
        earliest = max(config.start_date, customer_start[customer_id])
        is_completed = index < config.service_orders
        latest = config.end_date - timedelta(days=3) if is_completed else config.end_date
        appointment_date = _random_date(rng, earliest, latest)
        rows.append(
            {
                "appointment_id": _identifier("APT", index + 1),
                "customer_id": customer_id,
                "vehicle_id": rng.choice(vehicle_ids),
                "dealership_id": dealership_id,
                "service_advisor_id": rng.choice(advisors[dealership_id]),
                "appointment_date": appointment_date,
                "appointment_time": f"{rng.randint(7, 17):02d}:{rng.choice([0, 15, 30, 45]):02d}:00",
                "service_type": rng.choice(["Maintenance", "Repair", "Inspection", "Recall", "Tires"]),
                "appointment_status": "Completed" if is_completed else rng.choice(["Scheduled", "Cancelled", "No Show"]),
            }
        )
    return pd.DataFrame(rows)


def _build_service_orders(
    config: GeneratorConfig,
    rng: random.Random,
    appointments: pd.DataFrame,
    employees: pd.DataFrame,
) -> pd.DataFrame:
    technicians = _employee_lookup(employees, "Service Technician")
    rows = []
    for index, appointment in enumerate(appointments.iloc[: config.service_orders].to_dict("records")):
        opened_at = datetime.combine(appointment["appointment_date"], datetime.strptime(appointment["appointment_time"], "%H:%M:%S").time())
        promised_at = opened_at + timedelta(hours=rng.randint(2, 48))
        completed_at = opened_at + timedelta(hours=rng.randint(1, 60))
        labor_revenue = rng.uniform(65, 1_450)
        parts_revenue = rng.uniform(0, 2_800)
        discount = (labor_revenue + parts_revenue) * rng.uniform(0, 0.06)
        service_revenue = labor_revenue + parts_revenue - discount
        rows.append(
            {
                "service_order_id": _identifier("SRO", index + 1),
                "appointment_id": appointment["appointment_id"],
                "customer_id": appointment["customer_id"],
                "vehicle_id": appointment["vehicle_id"],
                "dealership_id": appointment["dealership_id"],
                "service_advisor_id": appointment["service_advisor_id"],
                "technician_id": rng.choice(technicians[appointment["dealership_id"]]),
                "opened_at": opened_at,
                "promised_at": promised_at,
                "completed_at": completed_at,
                "order_status": "Completed",
                "payer_type": rng.choices(["Customer Pay", "Warranty", "Internal"], weights=[73, 20, 7])[0],
                "labor_revenue": _money(labor_revenue),
                "parts_revenue": _money(parts_revenue),
                "discount_amount": _money(discount),
                "service_revenue": _money(service_revenue),
            }
        )
    return pd.DataFrame(rows)


def generate_datasets(config: GeneratorConfig | None = None) -> dict[str, pd.DataFrame]:
    """Generate all datasets in dependency order without writing files."""

    config = config or GeneratorConfig()
    config.validate()
    Faker.seed(config.seed)
    fake = Faker("en_US")
    fake.seed_instance(config.seed)
    rng = random.Random(config.seed)

    dealerships = _build_dealerships(config, fake)
    employees = _build_employees(config, fake, rng, dealerships)
    customers = _build_customers(config, fake, rng)
    vehicles = _build_vehicles(config, rng)
    sales = _build_sales(config, rng, customers, vehicles, dealerships, employees)
    inventory = _build_inventory(config, rng, vehicles, dealerships)
    service_appointments = _build_service_appointments(
        config, rng, customers, vehicles, dealerships, employees
    )
    service_orders = _build_service_orders(config, rng, service_appointments, employees)

    return {
        "customers": customers,
        "vehicles": vehicles,
        "dealerships": dealerships,
        "employees": employees,
        "sales": sales,
        "inventory": inventory,
        "service_appointments": service_appointments,
        "service_orders": service_orders,
    }


def write_datasets(
    output_dir: str | Path, config: GeneratorConfig | None = None
) -> dict[str, Path]:
    """Generate datasets and write them as UTF-8 CSV files."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    datasets = generate_datasets(config)
    paths = {}
    for name, frame in datasets.items():
        path = destination / f"{name}.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%d")
        paths[name] = path
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    paths = write_datasets(args.output_dir, GeneratorConfig(seed=args.seed))
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
