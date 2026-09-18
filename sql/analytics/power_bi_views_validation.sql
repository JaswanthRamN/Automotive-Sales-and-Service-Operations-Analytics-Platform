/* Read-only reconciliation tests for all five Power BI views. */

WITH latest_inventory_snapshot AS (
    SELECT MAX(snapshot_date_key) AS snapshot_date_key
    FROM analytics.vw_inventory_detail
), checks AS (
    SELECT 'vw_sales_performance_grain'::TEXT AS check_name,
           (COUNT(*) - COUNT(DISTINCT sale_id))::NUMERIC AS difference,
           'Power BI sales view must contain one row per eligible sale.'::TEXT AS details
    FROM analytics.vw_sales_performance

    UNION ALL
    SELECT 'vw_sales_performance_revenue',
           (SELECT COALESCE(SUM(revenue), 0) FROM analytics.vw_sales_performance)
           - (SELECT COALESCE(SUM(sale_price * unit_quantity), 0)
              FROM analytics.fact_sales WHERE sale_status IN ('Completed', 'Returned')),
           'Sales view revenue must reconcile to signed eligible fact_sales revenue.'

    UNION ALL
    SELECT 'vw_inventory_aging_grain',
           (COUNT(*) - COUNT(DISTINCT inventory_id || ':' || snapshot_date::TEXT))::NUMERIC,
           'Inventory view must contain one row per inventory_id and snapshot.'
    FROM analytics.vw_inventory_aging

    UNION ALL
    SELECT 'vw_inventory_aging_value',
           (SELECT COALESCE(SUM(inventory_value), 0) FROM analytics.vw_inventory_aging)
           - (SELECT COALESCE(SUM(carrying_cost), 0) FROM analytics.fact_inventory),
           'Inventory aging value must reconcile to fact_inventory.'

    UNION ALL
    SELECT 'vw_service_performance_grain',
           (COUNT(*) - COUNT(DISTINCT appointment_id))::NUMERIC,
           'Service view must contain one row per appointment.'
    FROM analytics.vw_service_performance

    UNION ALL
    SELECT 'vw_service_performance_revenue',
           (SELECT COALESCE(SUM(service_revenue), 0) FROM analytics.vw_service_performance)
           - (SELECT COALESCE(SUM(service_revenue), 0) FROM analytics.fact_service),
           'Service view revenue must reconcile to fact_service without duplication.'

    UNION ALL
    SELECT 'vw_customer_value_grain',
           (COUNT(*) - COUNT(DISTINCT customer_id))::NUMERIC,
           'Customer value view must contain one row per current customer.'
    FROM analytics.vw_customer_value

    UNION ALL
    SELECT 'vw_customer_value_revenue',
           (SELECT COALESCE(SUM(customer_revenue), 0) FROM analytics.vw_customer_value)
           - ((SELECT COALESCE(SUM(sale_price * unit_quantity), 0)
               FROM analytics.fact_sales WHERE sale_status IN ('Completed', 'Returned'))
              + (SELECT COALESCE(SUM(service_revenue), 0)
                 FROM analytics.fact_service WHERE order_status = 'Completed')),
           'Customer revenue must reconcile to eligible sales plus completed service revenue.'

    UNION ALL
    SELECT 'vw_dealership_performance_grain',
           (COUNT(*) - COUNT(DISTINCT dealership_id))::NUMERIC,
           'Dealership scorecard must contain one row per current dealership.'
    FROM analytics.vw_dealership_performance

    UNION ALL
    SELECT 'vw_dealership_performance_sales',
           (SELECT COALESCE(SUM(sales_revenue), 0) FROM analytics.vw_dealership_performance)
           - (SELECT COALESCE(SUM(revenue), 0) FROM analytics.vw_sales_detail),
           'Dealership sales revenue must reconcile to canonical sales detail.'

    UNION ALL
    SELECT 'vw_dealership_performance_inventory',
           (SELECT COALESCE(SUM(inventory_value), 0) FROM analytics.vw_dealership_performance)
           - (SELECT COALESCE(SUM(i.inventory_value), 0)
              FROM analytics.vw_inventory_detail i
              JOIN latest_inventory_snapshot s ON s.snapshot_date_key = i.snapshot_date_key),
           'Dealership inventory must reconcile to the latest canonical snapshot.'

    UNION ALL
    SELECT 'vw_dealership_performance_service',
           (SELECT COALESCE(SUM(service_revenue), 0) FROM analytics.vw_dealership_performance)
           - (SELECT COALESCE(SUM(service_revenue), 0) FROM analytics.vw_service_appointment_detail),
           'Dealership service revenue must reconcile to canonical appointment detail.'
)
SELECT
    check_name,
    CASE WHEN ABS(difference) <= 0.02 THEN 'PASS' ELSE 'FAIL' END AS status,
    difference,
    details
FROM checks
ORDER BY check_name;
