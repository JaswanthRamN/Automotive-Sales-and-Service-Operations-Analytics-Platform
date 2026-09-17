/*
Customer analytics views.

Grain rule: analytics.vw_customer_lifetime_detail contains exactly one row per
current dim_customer.customer_key. Sales and service are aggregated separately
to customer grain before they are joined, preventing cross-product duplication.

Definitions:
  - New customer: exactly one lifetime qualifying interaction.
  - Repeat customer: two or more lifetime qualifying interactions.
  - Repeat rate: repeat customers / customers with at least one interaction.
  - Inactive customer: previously active, but no activity for more than 365 days
    relative to the latest sales/service activity in the warehouse.
  - Customer lifetime value: interim revenue-based CLV (sales + service revenue)
    because authoritative service cost/profit is not available.
*/

BEGIN;

CREATE OR REPLACE VIEW analytics.vw_customer_lifetime_detail AS
WITH sales_by_customer AS (
    SELECT
        f.customer_key,
        COUNT(*)::BIGINT AS sales_transaction_count,
        SUM(f.unit_quantity)::BIGINT AS net_units_purchased,
        SUM(f.sale_price * f.unit_quantity)::NUMERIC(18, 2) AS sales_revenue,
        MIN(d.full_date) AS first_sale_date,
        MAX(d.full_date) AS last_sale_date
    FROM analytics.fact_sales f
    JOIN analytics.dim_date d ON d.date_key = f.sale_date_key
    WHERE f.sale_status IN ('Completed', 'Returned')
    GROUP BY f.customer_key
), service_by_customer AS (
    SELECT
        f.customer_key,
        COUNT(*)::BIGINT AS service_order_count,
        SUM(f.service_revenue)::NUMERIC(18, 2) AS service_revenue,
        MIN(f.completed_at::DATE) AS first_service_date,
        MAX(f.completed_at::DATE) AS last_service_date
    FROM analytics.fact_service f
    WHERE f.order_status = 'Completed'
    GROUP BY f.customer_key
), warehouse_as_of AS (
    SELECT COALESCE(
        GREATEST(
            (SELECT MAX(d.full_date)
             FROM analytics.fact_sales f
             JOIN analytics.dim_date d ON d.date_key = f.sale_date_key
             WHERE f.sale_status IN ('Completed', 'Returned')),
            (SELECT MAX(completed_at::DATE)
             FROM analytics.fact_service
             WHERE order_status = 'Completed')
        ),
        CURRENT_DATE
    ) AS as_of_date
), customer_metrics AS (
    SELECT
        c.customer_key,
        c.customer_id,
        c.first_name,
        c.last_name,
        c.first_name || ' ' || c.last_name AS customer_name,
        c.email,
        c.phone,
        c.city,
        c.state,
        c.postal_code,
        c.customer_type,
        c.customer_since_date,
        a.as_of_date,
        COALESCE(s.sales_transaction_count, 0) AS sales_transaction_count,
        COALESCE(s.net_units_purchased, 0) AS net_units_purchased,
        COALESCE(s.sales_revenue, 0)::NUMERIC(18, 2) AS sales_revenue,
        s.first_sale_date,
        s.last_sale_date,
        COALESCE(v.service_order_count, 0) AS service_order_count,
        COALESCE(v.service_revenue, 0)::NUMERIC(18, 2) AS service_revenue,
        v.first_service_date,
        v.last_service_date,
        COALESCE(s.sales_transaction_count, 0)
            + COALESCE(v.service_order_count, 0) AS qualifying_interaction_count,
        LEAST(s.first_sale_date, v.first_service_date) AS first_activity_date,
        GREATEST(s.last_sale_date, v.last_service_date) AS last_activity_date
    FROM analytics.dim_customer c
    CROSS JOIN warehouse_as_of a
    LEFT JOIN sales_by_customer s ON s.customer_key = c.customer_key
    LEFT JOIN service_by_customer v ON v.customer_key = c.customer_key
    WHERE c.is_current
)
SELECT
    customer_key,
    customer_id,
    customer_name,
    email,
    phone,
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
    (sales_revenue + service_revenue)::NUMERIC(18, 2) AS customer_revenue,
    (sales_revenue + service_revenue)::NUMERIC(18, 2) AS customer_lifetime_value,
    'Revenue-based interim CLV'::TEXT AS clv_method,
    CASE
        WHEN sales_transaction_count > 0 AND service_order_count > 0 THEN 'Sales + Service'
        WHEN sales_transaction_count > 0 THEN 'Sales Only'
        WHEN service_order_count > 0 THEN 'Service Only'
        ELSE 'No Activity'
    END AS relationship_segment,
    CASE
        WHEN qualifying_interaction_count = 0 THEN 'Prospect'
        WHEN qualifying_interaction_count = 1 THEN 'New Customer'
        ELSE 'Repeat Customer'
    END AS lifecycle_segment,
    CASE
        WHEN last_activity_date IS NULL THEN 'Never Active'
        WHEN last_activity_date < as_of_date - INTERVAL '365 days' THEN 'Inactive'
        ELSE 'Active'
    END AS activity_segment,
    CASE
        WHEN service_order_count = 0 THEN 'No Service'
        WHEN service_order_count = 1 THEN 'One-time Service'
        WHEN service_order_count BETWEEN 2 AND 3 THEN 'Occasional Service'
        WHEN service_order_count BETWEEN 4 AND 6 THEN 'Frequent Service'
        ELSE 'Loyal Service'
    END AS service_frequency_segment,
    ROUND(
        service_order_count::NUMERIC
        / NULLIF(
            GREATEST(
                1::NUMERIC,
                (as_of_date - COALESCE(first_service_date, as_of_date) + 1)::NUMERIC / 365.25
            ),
            0
        ),
        2
    ) AS service_frequency_per_year,
    CASE
        WHEN service_order_count > 1 THEN ROUND(
            (last_service_date - first_service_date)::NUMERIC
            / NULLIF(service_order_count - 1, 0),
            2
        )
        ELSE NULL
    END AS average_days_between_services
FROM customer_metrics;

COMMENT ON VIEW analytics.vw_customer_lifetime_detail IS
    'One row per current customer; separate sales/service aggregates prevent duplicate revenue and CLV is revenue-based until service cost is authoritative.';

CREATE OR REPLACE VIEW analytics.vw_customer_kpis AS
SELECT
    COUNT(*)::BIGINT AS total_customers,
    COUNT(*) FILTER (WHERE qualifying_interaction_count > 0)::BIGINT AS active_lifetime_customers,
    COUNT(*) FILTER (WHERE lifecycle_segment = 'New Customer')::BIGINT AS new_customers,
    COUNT(*) FILTER (WHERE lifecycle_segment = 'Repeat Customer')::BIGINT AS repeat_customers,
    ROUND(
        COUNT(*) FILTER (WHERE lifecycle_segment = 'Repeat Customer')::NUMERIC
        / NULLIF(COUNT(*) FILTER (WHERE qualifying_interaction_count > 0), 0) * 100,
        2
    ) AS repeat_rate_percent,
    COUNT(*) FILTER (WHERE relationship_segment = 'Sales Only')::BIGINT AS sales_only_customers,
    COUNT(*) FILTER (WHERE relationship_segment = 'Service Only')::BIGINT AS service_only_customers,
    COUNT(*) FILTER (WHERE relationship_segment = 'Sales + Service')::BIGINT AS sales_and_service_customers,
    COUNT(*) FILTER (WHERE activity_segment = 'Inactive')::BIGINT AS inactive_customers,
    COUNT(*) FILTER (WHERE activity_segment = 'Never Active')::BIGINT AS never_active_customers,
    SUM(sales_revenue)::NUMERIC(20, 2) AS sales_revenue,
    SUM(service_revenue)::NUMERIC(20, 2) AS service_revenue,
    SUM(customer_revenue)::NUMERIC(20, 2) AS customer_revenue,
    SUM(customer_lifetime_value)::NUMERIC(20, 2) AS total_customer_lifetime_value,
    ROUND(AVG(customer_lifetime_value), 2) AS average_customer_lifetime_value,
    SUM(service_order_count)::BIGINT AS service_orders,
    ROUND(AVG(service_frequency_per_year), 2) AS average_service_frequency_per_year,
    COUNT(DISTINCT customer_key)::BIGINT AS distinct_customer_count
FROM analytics.vw_customer_lifetime_detail;

CREATE OR REPLACE VIEW analytics.vw_customer_segment_summary AS
SELECT
    relationship_segment,
    lifecycle_segment,
    activity_segment,
    COUNT(*)::BIGINT AS customers,
    SUM(sales_transaction_count)::BIGINT AS sales_transactions,
    SUM(service_order_count)::BIGINT AS service_orders,
    SUM(sales_revenue)::NUMERIC(20, 2) AS sales_revenue,
    SUM(service_revenue)::NUMERIC(20, 2) AS service_revenue,
    SUM(customer_revenue)::NUMERIC(20, 2) AS customer_revenue,
    SUM(customer_lifetime_value)::NUMERIC(20, 2) AS customer_lifetime_value,
    ROUND(AVG(customer_lifetime_value), 2) AS average_customer_lifetime_value,
    ROUND(AVG(service_frequency_per_year), 2) AS average_service_frequency_per_year,
    COUNT(DISTINCT customer_key)::BIGINT AS distinct_customer_count
FROM analytics.vw_customer_lifetime_detail
GROUP BY relationship_segment, lifecycle_segment, activity_segment;

CREATE OR REPLACE VIEW analytics.vw_customer_service_frequency AS
SELECT
    service_frequency_segment,
    CASE service_frequency_segment
        WHEN 'No Service' THEN 1
        WHEN 'One-time Service' THEN 2
        WHEN 'Occasional Service' THEN 3
        WHEN 'Frequent Service' THEN 4
        ELSE 5
    END AS service_frequency_sort,
    COUNT(*)::BIGINT AS customers,
    SUM(service_order_count)::BIGINT AS service_orders,
    SUM(service_revenue)::NUMERIC(20, 2) AS service_revenue,
    SUM(customer_revenue)::NUMERIC(20, 2) AS customer_revenue,
    ROUND(AVG(service_frequency_per_year), 2) AS average_service_frequency_per_year,
    ROUND(AVG(average_days_between_services), 2) AS average_days_between_services,
    COUNT(DISTINCT customer_key)::BIGINT AS distinct_customer_count
FROM analytics.vw_customer_lifetime_detail
GROUP BY service_frequency_segment;

COMMIT;
