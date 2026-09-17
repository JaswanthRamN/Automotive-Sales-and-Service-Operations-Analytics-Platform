/*
Read-only reconciliation for customer analytics views.
Every result must return PASS before downstream reporting is published.
*/

WITH source_customers AS (
    SELECT COUNT(*)::BIGINT AS customers,
           COUNT(DISTINCT customer_key)::BIGINT AS distinct_customers
    FROM analytics.dim_customer
    WHERE is_current
), source_sales AS (
    SELECT COUNT(*)::BIGINT AS sales_transactions,
           COALESCE(SUM(sale_price * unit_quantity), 0)::NUMERIC AS sales_revenue
    FROM analytics.fact_sales
    WHERE sale_status IN ('Completed', 'Returned')
), source_service AS (
    SELECT COUNT(*)::BIGINT AS service_orders,
           COALESCE(SUM(service_revenue), 0)::NUMERIC AS service_revenue
    FROM analytics.fact_service
    WHERE order_status = 'Completed'
), detail_totals AS (
    SELECT COUNT(*)::BIGINT AS customers,
           COUNT(DISTINCT customer_key)::BIGINT AS distinct_customers,
           SUM(sales_transaction_count)::BIGINT AS sales_transactions,
           SUM(service_order_count)::BIGINT AS service_orders,
           SUM(sales_revenue)::NUMERIC AS sales_revenue,
           SUM(service_revenue)::NUMERIC AS service_revenue,
           SUM(customer_revenue)::NUMERIC AS customer_revenue,
           SUM(customer_lifetime_value)::NUMERIC AS customer_lifetime_value,
           COUNT(*) FILTER (WHERE lifecycle_segment = 'New Customer')::BIGINT AS new_customers,
           COUNT(*) FILTER (WHERE lifecycle_segment = 'Repeat Customer')::BIGINT AS repeat_customers,
           COUNT(*) FILTER (WHERE relationship_segment = 'Sales Only')::BIGINT AS sales_only_customers,
           COUNT(*) FILTER (WHERE relationship_segment = 'Service Only')::BIGINT AS service_only_customers,
           COUNT(*) FILTER (WHERE relationship_segment = 'Sales + Service')::BIGINT AS sales_and_service_customers,
           COUNT(*) FILTER (WHERE activity_segment = 'Inactive')::BIGINT AS inactive_customers
    FROM analytics.vw_customer_lifetime_detail
), segment_totals AS (
    SELECT SUM(customers)::BIGINT AS customers,
           SUM(sales_transactions)::BIGINT AS sales_transactions,
           SUM(service_orders)::BIGINT AS service_orders,
           SUM(sales_revenue)::NUMERIC AS sales_revenue,
           SUM(service_revenue)::NUMERIC AS service_revenue,
           SUM(customer_revenue)::NUMERIC AS customer_revenue,
           SUM(customer_lifetime_value)::NUMERIC AS customer_lifetime_value
    FROM analytics.vw_customer_segment_summary
), frequency_totals AS (
    SELECT SUM(customers)::BIGINT AS customers,
           SUM(service_orders)::BIGINT AS service_orders,
           SUM(service_revenue)::NUMERIC AS service_revenue,
           SUM(customer_revenue)::NUMERIC AS customer_revenue
    FROM analytics.vw_customer_service_frequency
), kpi_totals AS (
    SELECT total_customers AS customers,
           distinct_customer_count AS distinct_customers,
           new_customers,
           repeat_customers,
           sales_only_customers,
           service_only_customers,
           sales_and_service_customers,
           inactive_customers,
           sales_revenue::NUMERIC,
           service_revenue::NUMERIC,
           customer_revenue::NUMERIC,
           total_customer_lifetime_value::NUMERIC AS customer_lifetime_value,
           service_orders
    FROM analytics.vw_customer_kpis
), checks AS (
    SELECT 'detail_customer_uniqueness'::TEXT AS check_name,
           (SELECT customers - distinct_customers FROM detail_totals)::NUMERIC AS difference,
           'Canonical customer detail must contain one row per current customer.'::TEXT AS details

    UNION ALL
    SELECT 'detail_vs_current_customers',
           (SELECT customers FROM detail_totals) - (SELECT customers FROM source_customers),
           'Customer detail count must match current dim_customer rows.'

    UNION ALL
    SELECT 'detail_vs_fact_sales_transactions',
           (SELECT sales_transactions FROM detail_totals) - (SELECT sales_transactions FROM source_sales),
           'Customer sales transactions must reconcile without cross-product duplication.'

    UNION ALL
    SELECT 'detail_vs_fact_sales_revenue',
           (SELECT sales_revenue FROM detail_totals) - (SELECT sales_revenue FROM source_sales),
           'Customer sales revenue must reconcile to signed fact_sales revenue.'

    UNION ALL
    SELECT 'detail_vs_fact_service_orders',
           (SELECT service_orders FROM detail_totals) - (SELECT service_orders FROM source_service),
           'Customer service orders must reconcile without cross-product duplication.'

    UNION ALL
    SELECT 'detail_vs_fact_service_revenue',
           (SELECT service_revenue FROM detail_totals) - (SELECT service_revenue FROM source_service),
           'Customer service revenue must reconcile to fact_service.'

    UNION ALL
    SELECT 'customer_revenue_formula', COUNT(*)::NUMERIC,
           'Customer revenue must equal sales revenue plus service revenue.'
    FROM analytics.vw_customer_lifetime_detail
    WHERE ABS(customer_revenue - (sales_revenue + service_revenue)) > 0.02

    UNION ALL
    SELECT 'revenue_based_clv_formula', COUNT(*)::NUMERIC,
           'Interim customer lifetime value must equal customer revenue and use the declared method.'
    FROM analytics.vw_customer_lifetime_detail
    WHERE ABS(customer_lifetime_value - customer_revenue) > 0.02
       OR clv_method <> 'Revenue-based interim CLV'

    UNION ALL
    SELECT 'lifecycle_segments_are_exclusive', COUNT(*)::NUMERIC,
           'Prospect, New Customer, and Repeat Customer must follow lifetime interaction counts.'
    FROM analytics.vw_customer_lifetime_detail
    WHERE lifecycle_segment IS DISTINCT FROM CASE
        WHEN qualifying_interaction_count = 0 THEN 'Prospect'
        WHEN qualifying_interaction_count = 1 THEN 'New Customer'
        ELSE 'Repeat Customer'
    END

    UNION ALL
    SELECT 'relationship_segments_are_exclusive', COUNT(*)::NUMERIC,
           'Sales Only, Service Only, Sales + Service, and No Activity must be mutually exclusive.'
    FROM analytics.vw_customer_lifetime_detail
    WHERE relationship_segment IS DISTINCT FROM CASE
        WHEN sales_transaction_count > 0 AND service_order_count > 0 THEN 'Sales + Service'
        WHEN sales_transaction_count > 0 THEN 'Sales Only'
        WHEN service_order_count > 0 THEN 'Service Only'
        ELSE 'No Activity'
    END

    UNION ALL
    SELECT 'inactive_customer_definition', COUNT(*)::NUMERIC,
           'Inactive customers must be previously active and idle for more than 365 days as of warehouse activity.'
    FROM analytics.vw_customer_lifetime_detail
    WHERE (activity_segment = 'Inactive') IS DISTINCT FROM (
        last_activity_date IS NOT NULL
        AND last_activity_date < as_of_date - INTERVAL '365 days'
    )

    UNION ALL
    SELECT 'kpis_vs_detail_customer_count',
           (SELECT customers FROM kpi_totals) - (SELECT customers FROM detail_totals),
           'KPI total customers must reconcile to detail.'

    UNION ALL
    SELECT 'kpis_vs_detail_new_customers',
           (SELECT new_customers FROM kpi_totals) - (SELECT new_customers FROM detail_totals),
           'KPI new customers must reconcile to detail.'

    UNION ALL
    SELECT 'kpis_vs_detail_repeat_customers',
           (SELECT repeat_customers FROM kpi_totals) - (SELECT repeat_customers FROM detail_totals),
           'KPI repeat customers must reconcile to detail.'

    UNION ALL
    SELECT 'kpis_vs_detail_customer_revenue',
           (SELECT customer_revenue FROM kpi_totals) - (SELECT customer_revenue FROM detail_totals),
           'KPI customer revenue must reconcile to detail.'

    UNION ALL
    SELECT 'kpis_vs_detail_clv',
           (SELECT customer_lifetime_value FROM kpi_totals) - (SELECT customer_lifetime_value FROM detail_totals),
           'KPI customer lifetime value must reconcile to detail.'

    UNION ALL
    SELECT 'segment_summary_vs_detail_customers',
           (SELECT customers FROM segment_totals) - (SELECT customers FROM detail_totals),
           'Customer segment summary must reconcile to detail customer count.'

    UNION ALL
    SELECT 'segment_summary_vs_detail_revenue',
           (SELECT customer_revenue FROM segment_totals) - (SELECT customer_revenue FROM detail_totals),
           'Customer segment summary revenue must reconcile to detail.'

    UNION ALL
    SELECT 'frequency_summary_vs_detail_customers',
           (SELECT customers FROM frequency_totals) - (SELECT customers FROM detail_totals),
           'Service frequency segments must reconcile to detail customer count.'

    UNION ALL
    SELECT 'frequency_summary_vs_detail_service_orders',
           (SELECT service_orders FROM frequency_totals) - (SELECT service_orders FROM detail_totals),
           'Service frequency segment orders must reconcile to detail.'
)
SELECT
    check_name,
    CASE WHEN ABS(difference) <= 0.02 THEN 'PASS' ELSE 'FAIL' END AS status,
    difference,
    details
FROM checks
ORDER BY check_name;
