BEGIN;

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
