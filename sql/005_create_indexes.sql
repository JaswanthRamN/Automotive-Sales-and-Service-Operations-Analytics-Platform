BEGIN;

-- Cleaned staging loads must preserve their declared business-key grains.
-- These indexes fail fast on duplicate source rows and support the warehouse
-- lookup from service orders to appointments.
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_customers_id
    ON staging.customers (customer_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_vehicles_id
    ON staging.vehicles (vehicle_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_dealerships_id
    ON staging.dealerships (dealership_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_employees_id
    ON staging.employees (employee_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_sales_id
    ON staging.sales (sale_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_inventory_grain
    ON staging.inventory (inventory_id, snapshot_date);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_service_appointments_id
    ON staging.service_appointments (appointment_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_service_orders_id
    ON staging.service_orders (service_order_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_staging_service_orders_appointment
    ON staging.service_orders (appointment_id);

CREATE INDEX IF NOT EXISTS idx_dim_customer_location
    ON analytics.dim_customer (state, city);
CREATE INDEX IF NOT EXISTS idx_dim_vehicle_hierarchy
    ON analytics.dim_vehicle (make, model, model_year);
CREATE INDEX IF NOT EXISTS idx_dim_employee_dealership_role
    ON analytics.dim_employee (dealership_key, role)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_fact_sales_date_dealership
    ON analytics.fact_sales (sale_date_key, dealership_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_customer_date
    ON analytics.fact_sales (customer_key, sale_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_vehicle
    ON analytics.fact_sales (vehicle_key);
CREATE INDEX IF NOT EXISTS idx_fact_sales_salesperson_date
    ON analytics.fact_sales (salesperson_key, sale_date_key);

CREATE INDEX IF NOT EXISTS idx_fact_inventory_date_dealership
    ON analytics.fact_inventory (snapshot_date_key, dealership_key);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_vehicle
    ON analytics.fact_inventory (vehicle_key);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_status_age
    ON analytics.fact_inventory (inventory_status, days_in_inventory);
CREATE INDEX IF NOT EXISTS idx_fact_inventory_slow_moving
    ON analytics.fact_inventory (snapshot_date_key, dealership_key, days_in_inventory)
    WHERE slow_moving_flag;

CREATE INDEX IF NOT EXISTS idx_fact_service_date_dealership
    ON analytics.fact_service (completed_date_key, dealership_key);
CREATE INDEX IF NOT EXISTS idx_fact_service_customer_date
    ON analytics.fact_service (customer_key, completed_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_service_vehicle
    ON analytics.fact_service (vehicle_key);
CREATE INDEX IF NOT EXISTS idx_fact_service_advisor_date
    ON analytics.fact_service (service_advisor_key, completed_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_service_technician_date
    ON analytics.fact_service (technician_key, completed_date_key);
CREATE INDEX IF NOT EXISTS idx_fact_service_type_date
    ON analytics.fact_service (service_key, completed_date_key);

COMMIT;
