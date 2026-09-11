/*
Sales analytics views.

Grain rule: analytics.vw_sales_detail contains exactly one row per eligible
fact_sales.sale_id. Every aggregate view reads only from this canonical view,
which prevents dimension joins from multiplying sales.

Completed sales use unit_quantity = 1. Returns use unit_quantity = -1 so units,
revenue, vehicle cost, and gross profit reverse consistently. Cancelled facts
are excluded from sales KPIs.
*/

BEGIN;

CREATE OR REPLACE VIEW analytics.vw_sales_detail AS
SELECT
    f.sales_key,
    f.sale_id,
    f.sale_date_key,
    d.full_date AS sale_date,
    d.calendar_year,
    d.quarter_number,
    d.month_number,
    d.month_name,
    f.customer_key,
    f.vehicle_key,
    v.vehicle_id,
    v.vin,
    v.make AS brand,
    v.model,
    v.model_year,
    v.body_type AS vehicle_type,
    v.fuel_type,
    v.vehicle_condition,
    f.dealership_key,
    dl.dealership_id,
    dl.dealership_name,
    dl.region,
    dl.state,
    f.salesperson_key,
    e.employee_id AS salesperson_id,
    e.first_name || ' ' || e.last_name AS salesperson_name,
    f.sales_channel,
    f.payment_type,
    f.sale_status,
    f.unit_quantity AS units_sold,
    f.list_price,
    f.discount_amount,
    (f.sale_price * f.unit_quantity)::NUMERIC(16, 2) AS revenue,
    (f.vehicle_cost * f.unit_quantity)::NUMERIC(16, 2) AS vehicle_cost,
    (f.gross_profit * f.unit_quantity)::NUMERIC(16, 2) AS gross_profit
FROM analytics.fact_sales f
JOIN analytics.dim_date d ON d.date_key = f.sale_date_key
JOIN analytics.dim_vehicle v ON v.vehicle_key = f.vehicle_key
JOIN analytics.dim_dealership dl ON dl.dealership_key = f.dealership_key
JOIN analytics.dim_employee e ON e.employee_key = f.salesperson_key
WHERE f.sale_status IN ('Completed', 'Returned');

COMMENT ON VIEW analytics.vw_sales_detail IS
    'Canonical one-row-per-sale dataset for all sales analytics; cancelled sales excluded and returns signed.';

CREATE OR REPLACE VIEW analytics.vw_sales_kpis AS
SELECT
    COALESCE(SUM(units_sold), 0)::BIGINT AS units_sold,
    COALESCE(SUM(revenue), 0)::NUMERIC(18, 2) AS revenue,
    COALESCE(SUM(gross_profit), 0)::NUMERIC(18, 2) AS gross_profit,
    ROUND(
        COALESCE(SUM(gross_profit), 0) / NULLIF(SUM(revenue), 0) * 100,
        2
    ) AS gross_margin_percent,
    ROUND(
        COALESCE(SUM(revenue), 0) / NULLIF(SUM(units_sold), 0),
        2
    ) AS average_selling_price,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count
FROM analytics.vw_sales_detail;

CREATE OR REPLACE VIEW analytics.vw_monthly_sales AS
SELECT
    calendar_year,
    month_number,
    MIN(sale_date) AS month_start_date,
    month_name,
    SUM(units_sold)::BIGINT AS units_sold,
    SUM(revenue)::NUMERIC(18, 2) AS revenue,
    SUM(gross_profit)::NUMERIC(18, 2) AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(revenue), 0) * 100, 2) AS gross_margin_percent,
    ROUND(SUM(revenue) / NULLIF(SUM(units_sold), 0), 2) AS average_selling_price,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count
FROM analytics.vw_sales_detail
GROUP BY calendar_year, month_number, month_name;

CREATE OR REPLACE VIEW analytics.vw_brand_model_performance AS
SELECT
    brand,
    model,
    model_year,
    SUM(units_sold)::BIGINT AS units_sold,
    SUM(revenue)::NUMERIC(18, 2) AS revenue,
    SUM(gross_profit)::NUMERIC(18, 2) AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(revenue), 0) * 100, 2) AS gross_margin_percent,
    ROUND(SUM(revenue) / NULLIF(SUM(units_sold), 0), 2) AS average_selling_price,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count
FROM analytics.vw_sales_detail
GROUP BY brand, model, model_year;

CREATE OR REPLACE VIEW analytics.vw_salesperson_performance AS
SELECT
    salesperson_key,
    salesperson_id,
    salesperson_name,
    dealership_key,
    dealership_id,
    dealership_name,
    SUM(units_sold)::BIGINT AS units_sold,
    SUM(revenue)::NUMERIC(18, 2) AS revenue,
    SUM(gross_profit)::NUMERIC(18, 2) AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(revenue), 0) * 100, 2) AS gross_margin_percent,
    ROUND(SUM(revenue) / NULLIF(SUM(units_sold), 0), 2) AS average_selling_price,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count
FROM analytics.vw_sales_detail
GROUP BY salesperson_key, salesperson_id, salesperson_name,
         dealership_key, dealership_id, dealership_name;

CREATE OR REPLACE VIEW analytics.vw_dealership_performance AS
SELECT
    dealership_key,
    dealership_id,
    dealership_name,
    region,
    state,
    SUM(units_sold)::BIGINT AS units_sold,
    SUM(revenue)::NUMERIC(18, 2) AS revenue,
    SUM(gross_profit)::NUMERIC(18, 2) AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(revenue), 0) * 100, 2) AS gross_margin_percent,
    ROUND(SUM(revenue) / NULLIF(SUM(units_sold), 0), 2) AS average_selling_price,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count
FROM analytics.vw_sales_detail
GROUP BY dealership_key, dealership_id, dealership_name, region, state;

CREATE OR REPLACE VIEW analytics.vw_vehicle_type_performance AS
SELECT
    vehicle_type,
    vehicle_condition,
    fuel_type,
    SUM(units_sold)::BIGINT AS units_sold,
    SUM(revenue)::NUMERIC(18, 2) AS revenue,
    SUM(gross_profit)::NUMERIC(18, 2) AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(revenue), 0) * 100, 2) AS gross_margin_percent,
    ROUND(SUM(revenue) / NULLIF(SUM(units_sold), 0), 2) AS average_selling_price,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count
FROM analytics.vw_sales_detail
GROUP BY vehicle_type, vehicle_condition, fuel_type;

CREATE OR REPLACE VIEW analytics.vw_payment_method_performance AS
SELECT
    payment_type,
    SUM(units_sold)::BIGINT AS units_sold,
    SUM(revenue)::NUMERIC(18, 2) AS revenue,
    SUM(gross_profit)::NUMERIC(18, 2) AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(revenue), 0) * 100, 2) AS gross_margin_percent,
    ROUND(SUM(revenue) / NULLIF(SUM(units_sold), 0), 2) AS average_selling_price,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count
FROM analytics.vw_sales_detail
GROUP BY payment_type;

COMMIT;
