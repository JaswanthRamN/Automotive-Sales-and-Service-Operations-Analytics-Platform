TRUNCATE TABLE
    analytics.fact_service,
    analytics.fact_inventory,
    analytics.fact_sales,
    analytics.dim_service,
    analytics.dim_employee,
    analytics.dim_customer,
    analytics.dim_vehicle,
    analytics.dim_dealership,
    analytics.dim_date
RESTART IDENTITY CASCADE;

INSERT INTO analytics.dim_date (
    date_key, full_date, day_of_week, day_name, day_of_month, day_of_year,
    week_of_year, month_number, month_name, quarter_number, calendar_year, is_weekend
)
WITH date_bounds AS (
    SELECT MIN(event_date) AS min_date, MAX(event_date) AS max_date
    FROM (
        SELECT sale_date::DATE AS event_date FROM staging.sales
        UNION ALL SELECT snapshot_date::DATE FROM staging.inventory
        UNION ALL SELECT acquired_date::DATE FROM staging.inventory
        UNION ALL SELECT appointment_date::DATE FROM staging.service_appointments
        UNION ALL SELECT opened_at::TIMESTAMP::DATE FROM staging.service_orders
        UNION ALL SELECT completed_at::TIMESTAMP::DATE FROM staging.service_orders
        UNION ALL SELECT customer_since_date::DATE FROM staging.customers
        UNION ALL SELECT hire_date::DATE FROM staging.employees
        UNION ALL SELECT opened_date::DATE FROM staging.dealerships
    ) dates
), calendar AS (
    SELECT generate_series(min_date, max_date, INTERVAL '1 day')::DATE AS full_date
    FROM date_bounds
)
SELECT
    TO_CHAR(full_date, 'YYYYMMDD')::INTEGER,
    full_date,
    EXTRACT(ISODOW FROM full_date)::SMALLINT,
    TRIM(TO_CHAR(full_date, 'Day')),
    EXTRACT(DAY FROM full_date)::SMALLINT,
    EXTRACT(DOY FROM full_date)::SMALLINT,
    EXTRACT(WEEK FROM full_date)::SMALLINT,
    EXTRACT(MONTH FROM full_date)::SMALLINT,
    TRIM(TO_CHAR(full_date, 'Month')),
    EXTRACT(QUARTER FROM full_date)::SMALLINT,
    EXTRACT(YEAR FROM full_date)::SMALLINT,
    EXTRACT(ISODOW FROM full_date) IN (6, 7)
FROM calendar;

INSERT INTO analytics.dim_dealership (
    dealership_id, dealership_name, city, state, postal_code, region, opened_date
)
SELECT dealership_id, dealership_name, city, state, postal_code, region, opened_date::DATE
FROM staging.dealerships;

INSERT INTO analytics.dim_customer (
    customer_id, first_name, last_name, email, phone, city, state, postal_code,
    customer_since_date, customer_type
)
SELECT customer_id, first_name, last_name, NULLIF(email, ''), NULLIF(phone, ''),
       NULLIF(city, ''), NULLIF(state, ''), NULLIF(postal_code, ''),
       customer_since_date::DATE, customer_type
FROM staging.customers;

INSERT INTO analytics.dim_vehicle (
    vehicle_id, vin, make, model, model_year, body_type, fuel_type, color,
    vehicle_condition, mileage_at_acquisition, manufacturer_msrp
)
SELECT vehicle_id, vin, make, model, model_year::SMALLINT, body_type, fuel_type,
       NULLIF(color, ''), vehicle_condition, mileage_at_acquisition::INTEGER,
       manufacturer_msrp::NUMERIC(14, 2)
FROM staging.vehicles;

INSERT INTO analytics.dim_employee (
    employee_id, dealership_key, first_name, last_name, role, hire_date, employment_status
)
SELECT e.employee_id, d.dealership_key, e.first_name, e.last_name, e.role,
       e.hire_date::DATE, e.employment_status
FROM staging.employees e
JOIN analytics.dim_dealership d ON d.dealership_id = e.dealership_id;

INSERT INTO analytics.dim_service (service_type, service_category)
SELECT DISTINCT service_type,
       CASE
           WHEN service_type IN ('Maintenance', 'Inspection') THEN 'Preventive'
           WHEN service_type IN ('Repair', 'Recall') THEN 'Corrective'
           WHEN service_type = 'Tires' THEN 'Tire Services'
           ELSE 'Other'
       END
FROM staging.service_appointments;

INSERT INTO analytics.fact_sales (
    sale_id, sale_date_key, customer_key, vehicle_key, dealership_key, salesperson_key,
    sales_channel, list_price, discount_amount, sale_price, vehicle_cost, gross_profit,
    unit_quantity, payment_type, sale_status
)
SELECT s.sale_id, TO_CHAR(s.sale_date::DATE, 'YYYYMMDD')::INTEGER,
       c.customer_key, v.vehicle_key, d.dealership_key, e.employee_key,
       s.sales_channel, s.list_price::NUMERIC(14, 2), s.discount_amount::NUMERIC(14, 2),
       s.sale_price::NUMERIC(14, 2), s.vehicle_cost::NUMERIC(14, 2),
       s.gross_profit::NUMERIC(14, 2), 1, s.payment_type, s.sale_status
FROM staging.sales s
JOIN analytics.dim_customer c ON c.customer_id = s.customer_id AND c.is_current
JOIN analytics.dim_vehicle v ON v.vehicle_id = s.vehicle_id
JOIN analytics.dim_dealership d ON d.dealership_id = s.dealership_id
JOIN analytics.dim_employee e ON e.employee_id = s.salesperson_id AND e.is_current;

INSERT INTO analytics.fact_inventory (
    inventory_id, snapshot_date_key, vehicle_key, dealership_key, acquired_date,
    inventory_status, carrying_cost, days_in_inventory, slow_moving_flag, on_hand_quantity
)
SELECT i.inventory_id, TO_CHAR(i.snapshot_date::DATE, 'YYYYMMDD')::INTEGER,
       v.vehicle_key, d.dealership_key, i.acquired_date::DATE, i.inventory_status,
       i.carrying_cost::NUMERIC(14, 2), i.days_in_inventory::INTEGER,
       i.slow_moving_flag::BOOLEAN, 1
FROM staging.inventory i
JOIN analytics.dim_vehicle v ON v.vehicle_id = i.vehicle_id
JOIN analytics.dim_dealership d ON d.dealership_id = i.dealership_id;

INSERT INTO analytics.fact_service (
    service_order_id, appointment_id, completed_date_key, customer_key, vehicle_key,
    dealership_key, service_advisor_key, technician_key, service_key, opened_at,
    promised_at, completed_at, order_status, payer_type, labor_revenue, parts_revenue,
    discount_amount, service_revenue, repair_order_quantity
)
SELECT so.service_order_id, so.appointment_id,
       TO_CHAR(so.completed_at::TIMESTAMP::DATE, 'YYYYMMDD')::INTEGER,
       c.customer_key, v.vehicle_key, d.dealership_key, advisor.employee_key,
       technician.employee_key, svc.service_key, so.opened_at::TIMESTAMP,
       so.promised_at::TIMESTAMP, so.completed_at::TIMESTAMP, so.order_status,
       so.payer_type, so.labor_revenue::NUMERIC(14, 2),
       so.parts_revenue::NUMERIC(14, 2), so.discount_amount::NUMERIC(14, 2),
       so.service_revenue::NUMERIC(14, 2), 1
FROM staging.service_orders so
JOIN staging.service_appointments sa ON sa.appointment_id = so.appointment_id
JOIN analytics.dim_customer c ON c.customer_id = so.customer_id AND c.is_current
JOIN analytics.dim_vehicle v ON v.vehicle_id = so.vehicle_id
JOIN analytics.dim_dealership d ON d.dealership_id = so.dealership_id
JOIN analytics.dim_employee advisor
  ON advisor.employee_id = so.service_advisor_id AND advisor.is_current
JOIN analytics.dim_employee technician
  ON technician.employee_id = so.technician_id AND technician.is_current
JOIN analytics.dim_service svc ON svc.service_type = sa.service_type;
