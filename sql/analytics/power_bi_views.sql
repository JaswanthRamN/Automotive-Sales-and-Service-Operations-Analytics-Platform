/*
Business-friendly Power BI views.

Execution order:
  1. sales_analytics.sql
  2. inventory_analytics.sql
  3. service_analytics.sql
  4. customer_analytics.sql
  5. this script

The four detail views preserve their canonical source grain. The dealership
view aggregates each subject independently before joining, preventing
sales/inventory/service cross products and duplicated measures.
*/

BEGIN;

CREATE OR REPLACE VIEW analytics.vw_sales_performance AS
SELECT
    sale_id,
    sale_date,
    calendar_year AS sale_year,
    quarter_number AS sale_quarter,
    month_number AS sale_month_number,
    month_name AS sale_month_name,
    customer_key,
    vehicle_id,
    vin,
    brand,
    model,
    model_year,
    vehicle_type,
    fuel_type,
    vehicle_condition,
    dealership_id,
    dealership_name,
    region,
    state,
    salesperson_id,
    salesperson_name,
    sales_channel,
    payment_type,
    sale_status,
    units_sold,
    list_price,
    discount_amount,
    revenue,
    vehicle_cost,
    gross_profit,
    ROUND(gross_profit / NULLIF(revenue, 0) * 100, 2) AS gross_margin_percent,
    ROUND(revenue / NULLIF(units_sold, 0), 2) AS average_selling_price
FROM analytics.vw_sales_detail;

COMMENT ON VIEW analytics.vw_sales_performance IS
    'Power BI sales view at one row per eligible sale; signed returns and cancelled sales excluded by canonical source.';

CREATE OR REPLACE VIEW analytics.vw_inventory_aging AS
SELECT
    inventory_id,
    snapshot_date,
    vehicle_id,
    vin,
    brand,
    model,
    model_year,
    vehicle_type,
    fuel_type,
    vehicle_condition,
    dealership_id,
    dealership_name,
    region,
    state,
    acquired_date,
    inventory_status,
    inventory_units,
    inventory_value,
    days_in_inventory,
    aging_bucket,
    aging_bucket_sort,
    is_slow_moving
FROM analytics.vw_inventory_detail;

COMMENT ON VIEW analytics.vw_inventory_aging IS
    'Power BI inventory view at one vehicle/dealership/snapshot row with ordered aging buckets and >90-day slow-moving flag.';

CREATE OR REPLACE VIEW analytics.vw_service_performance AS
SELECT
    appointment_id,
    appointment_date,
    calendar_year AS appointment_year,
    quarter_number AS appointment_quarter,
    month_number AS appointment_month_number,
    month_name AS appointment_month_name,
    appointment_time,
    customer_key,
    vehicle_id,
    vin,
    vehicle_brand,
    vehicle_model,
    dealership_id,
    dealership_name,
    region,
    state,
    service_advisor_id,
    service_advisor_name,
    service_type,
    service_category,
    appointment_status,
    appointment_count,
    completed_appointment_count,
    cancellation_count,
    no_show_count,
    completion_eligible_count,
    service_order_id,
    technician_id,
    technician_name,
    payer_type,
    completed_on_time,
    turnaround_hours,
    labor_revenue,
    parts_revenue,
    discount_amount,
    service_revenue,
    service_cost,
    service_profit,
    service_cost_available
FROM analytics.vw_service_appointment_detail;

COMMENT ON VIEW analytics.vw_service_performance IS
    'Power BI service view at one row per appointment; repair-order revenue joins one-to-one and unavailable cost/profit remain NULL.';

CREATE OR REPLACE VIEW analytics.vw_customer_value AS
SELECT
    customer_id,
    customer_name,
    city,
    state,
    postal_code,
    customer_type,
    customer_since_date,
    as_of_date,
    sales_transaction_count,
    net_units_purchased,
    sales_revenue,
    first_sale_date,
    last_sale_date,
    service_order_count,
    service_revenue,
    first_service_date,
    last_service_date,
    qualifying_interaction_count,
    first_activity_date,
    last_activity_date,
    customer_revenue,
    customer_lifetime_value,
    clv_method,
    relationship_segment,
    lifecycle_segment,
    activity_segment,
    service_frequency_segment,
    service_frequency_per_year,
    average_days_between_services
FROM analytics.vw_customer_lifetime_detail;

COMMENT ON VIEW analytics.vw_customer_value IS
    'Power BI customer-value view at one current customer row; excludes direct email/phone and labels interim revenue-based CLV.';

-- Replaces the earlier sales-only view shape on existing project databases.
DROP VIEW IF EXISTS analytics.vw_dealership_performance;

CREATE OR REPLACE VIEW analytics.vw_dealership_performance AS
WITH sales AS (
    SELECT
        dealership_key,
        SUM(units_sold)::BIGINT AS units_sold,
        SUM(revenue)::NUMERIC(20, 2) AS sales_revenue,
        SUM(gross_profit)::NUMERIC(20, 2) AS sales_gross_profit,
        COUNT(*)::BIGINT AS sales_fact_rows
    FROM analytics.vw_sales_detail
    GROUP BY dealership_key
), latest_inventory_snapshot AS (
    SELECT MAX(snapshot_date_key) AS snapshot_date_key
    FROM analytics.vw_inventory_detail
), inventory AS (
    SELECT
        i.dealership_key,
        MAX(i.snapshot_date) AS inventory_snapshot_date,
        SUM(i.inventory_units)::BIGINT AS inventory_units,
        SUM(i.inventory_value)::NUMERIC(20, 2) AS inventory_value,
        ROUND(
            SUM(i.days_in_inventory * i.inventory_units)::NUMERIC
            / NULLIF(SUM(i.inventory_units), 0),
            2
        ) AS average_inventory_age_days,
        COALESCE(SUM(i.inventory_units) FILTER (WHERE i.is_slow_moving), 0)::BIGINT AS slow_moving_units,
        COALESCE(SUM(i.inventory_value) FILTER (WHERE i.is_slow_moving), 0)::NUMERIC(20, 2) AS slow_moving_value
    FROM analytics.vw_inventory_detail i
    JOIN latest_inventory_snapshot s ON s.snapshot_date_key = i.snapshot_date_key
    GROUP BY i.dealership_key
), service AS (
    SELECT
        dealership_key,
        SUM(appointment_count)::BIGINT AS appointments,
        SUM(completed_appointment_count)::BIGINT AS completed_appointments,
        SUM(cancellation_count)::BIGINT AS cancellations,
        SUM(no_show_count)::BIGINT AS no_shows,
        SUM(completion_eligible_count)::BIGINT AS completion_eligible_appointments,
        COUNT(service_order_id)::BIGINT AS repair_orders,
        SUM(service_revenue)::NUMERIC(20, 2) AS service_revenue,
        COUNT(*)::BIGINT AS service_detail_rows
    FROM analytics.vw_service_appointment_detail
    GROUP BY dealership_key
), customer_activity AS (
    SELECT dealership_key, customer_key FROM analytics.vw_sales_detail
    UNION
    SELECT dealership_key, customer_key FROM analytics.vw_service_appointment_detail
), customers AS (
    SELECT dealership_key, COUNT(*)::BIGINT AS unique_customers
    FROM customer_activity
    GROUP BY dealership_key
)
SELECT
    d.dealership_id,
    d.dealership_name,
    d.city,
    d.state,
    d.postal_code,
    d.region,
    COALESCE(s.units_sold, 0) AS units_sold,
    COALESCE(s.sales_revenue, 0)::NUMERIC(20, 2) AS sales_revenue,
    COALESCE(s.sales_gross_profit, 0)::NUMERIC(20, 2) AS sales_gross_profit,
    ROUND(s.sales_gross_profit / NULLIF(s.sales_revenue, 0) * 100, 2) AS sales_gross_margin_percent,
    ROUND(s.sales_revenue / NULLIF(s.units_sold, 0), 2) AS average_selling_price,
    COALESCE(s.sales_fact_rows, 0) AS sales_fact_rows,
    i.inventory_snapshot_date,
    COALESCE(i.inventory_units, 0) AS inventory_units,
    COALESCE(i.inventory_value, 0)::NUMERIC(20, 2) AS inventory_value,
    i.average_inventory_age_days,
    COALESCE(i.slow_moving_units, 0) AS slow_moving_units,
    COALESCE(i.slow_moving_value, 0)::NUMERIC(20, 2) AS slow_moving_value,
    COALESCE(v.appointments, 0) AS appointments,
    COALESCE(v.completed_appointments, 0) AS completed_appointments,
    COALESCE(v.cancellations, 0) AS cancellations,
    COALESCE(v.no_shows, 0) AS no_shows,
    ROUND(
        v.completed_appointments::NUMERIC
        / NULLIF(v.completion_eligible_appointments, 0) * 100,
        2
    ) AS service_completion_rate_percent,
    COALESCE(v.repair_orders, 0) AS repair_orders,
    COALESCE(v.service_revenue, 0)::NUMERIC(20, 2) AS service_revenue,
    ROUND(v.service_revenue / NULLIF(v.repair_orders, 0), 2) AS average_repair_order,
    COALESCE(v.service_detail_rows, 0) AS service_detail_rows,
    COALESCE(c.unique_customers, 0) AS unique_customers,
    (COALESCE(s.sales_revenue, 0) + COALESCE(v.service_revenue, 0))::NUMERIC(20, 2) AS total_revenue
FROM analytics.dim_dealership d
LEFT JOIN sales s ON s.dealership_key = d.dealership_key
LEFT JOIN inventory i ON i.dealership_key = d.dealership_key
LEFT JOIN service v ON v.dealership_key = d.dealership_key
LEFT JOIN customers c ON c.dealership_key = d.dealership_key
WHERE d.is_current;

COMMENT ON VIEW analytics.vw_dealership_performance IS
    'Power BI dealership scorecard; sales, latest inventory, service, and customers are aggregated independently before one-to-one dealership joins.';

COMMIT;
