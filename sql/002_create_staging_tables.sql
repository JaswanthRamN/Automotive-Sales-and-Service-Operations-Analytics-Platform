BEGIN;

CREATE TABLE IF NOT EXISTS staging.customers (
    customer_id TEXT,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    customer_since_date TEXT,
    customer_type TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.vehicles (
    vehicle_id TEXT,
    vin TEXT,
    make TEXT,
    model TEXT,
    model_year TEXT,
    body_type TEXT,
    fuel_type TEXT,
    color TEXT,
    vehicle_condition TEXT,
    mileage_at_acquisition TEXT,
    manufacturer_msrp TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.dealerships (
    dealership_id TEXT,
    dealership_name TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    region TEXT,
    opened_date TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.employees (
    employee_id TEXT,
    dealership_id TEXT,
    first_name TEXT,
    last_name TEXT,
    role TEXT,
    hire_date TEXT,
    employment_status TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.sales (
    sale_id TEXT,
    sale_date TEXT,
    customer_id TEXT,
    vehicle_id TEXT,
    dealership_id TEXT,
    salesperson_id TEXT,
    sales_channel TEXT,
    list_price TEXT,
    discount_amount TEXT,
    sale_price TEXT,
    vehicle_cost TEXT,
    gross_profit TEXT,
    payment_type TEXT,
    sale_status TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.inventory (
    inventory_id TEXT,
    snapshot_date TEXT,
    vehicle_id TEXT,
    dealership_id TEXT,
    acquired_date TEXT,
    inventory_status TEXT,
    carrying_cost TEXT,
    days_in_inventory TEXT,
    slow_moving_flag TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.service_appointments (
    appointment_id TEXT,
    customer_id TEXT,
    vehicle_id TEXT,
    dealership_id TEXT,
    service_advisor_id TEXT,
    appointment_date TEXT,
    appointment_time TEXT,
    service_type TEXT,
    appointment_status TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staging.service_orders (
    service_order_id TEXT,
    appointment_id TEXT,
    customer_id TEXT,
    vehicle_id TEXT,
    dealership_id TEXT,
    service_advisor_id TEXT,
    technician_id TEXT,
    opened_at TEXT,
    promised_at TEXT,
    completed_at TEXT,
    order_status TEXT,
    payer_type TEXT,
    labor_revenue TEXT,
    parts_revenue TEXT,
    discount_amount TEXT,
    service_revenue TEXT,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
