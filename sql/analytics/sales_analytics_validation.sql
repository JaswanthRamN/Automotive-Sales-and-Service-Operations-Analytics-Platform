/*
Read-only reconciliation for the sales analytics views.

Each row returns PASS when the view reconciles with the canonical eligible
fact grain. Any nonzero failed_count must be investigated before publishing.
*/

WITH fact_totals AS (
    SELECT
        COUNT(*)::BIGINT AS fact_row_count,
        COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count,
        COALESCE(SUM(unit_quantity), 0)::NUMERIC AS units_sold,
        COALESCE(SUM(sale_price * unit_quantity), 0)::NUMERIC AS revenue,
        COALESCE(SUM(gross_profit * unit_quantity), 0)::NUMERIC AS gross_profit
    FROM analytics.fact_sales
    WHERE sale_status IN ('Completed', 'Returned')
), detail_totals AS (
    SELECT
        COUNT(*)::BIGINT AS fact_row_count,
        COUNT(DISTINCT sale_id)::BIGINT AS distinct_sale_count,
        COALESCE(SUM(units_sold), 0)::NUMERIC AS units_sold,
        COALESCE(SUM(revenue), 0)::NUMERIC AS revenue,
        COALESCE(SUM(gross_profit), 0)::NUMERIC AS gross_profit
    FROM analytics.vw_sales_detail
), kpi_totals AS (
    SELECT fact_row_count, distinct_sale_count, units_sold::NUMERIC,
           revenue::NUMERIC, gross_profit::NUMERIC
    FROM analytics.vw_sales_kpis
), grouped_totals AS (
    SELECT 'vw_monthly_sales'::TEXT AS view_name,
           COALESCE(SUM(fact_row_count), 0)::BIGINT AS fact_row_count,
           COALESCE(SUM(units_sold), 0)::NUMERIC AS units_sold,
           COALESCE(SUM(revenue), 0)::NUMERIC AS revenue,
           COALESCE(SUM(gross_profit), 0)::NUMERIC AS gross_profit
    FROM analytics.vw_monthly_sales
    UNION ALL
    SELECT 'vw_brand_model_performance', COALESCE(SUM(fact_row_count), 0),
           COALESCE(SUM(units_sold), 0), COALESCE(SUM(revenue), 0), COALESCE(SUM(gross_profit), 0)
    FROM analytics.vw_brand_model_performance
    UNION ALL
    SELECT 'vw_salesperson_performance', COALESCE(SUM(fact_row_count), 0),
           COALESCE(SUM(units_sold), 0), COALESCE(SUM(revenue), 0), COALESCE(SUM(gross_profit), 0)
    FROM analytics.vw_salesperson_performance
    UNION ALL
    SELECT 'vw_dealership_performance', COALESCE(SUM(fact_row_count), 0),
           COALESCE(SUM(units_sold), 0), COALESCE(SUM(revenue), 0), COALESCE(SUM(gross_profit), 0)
    FROM analytics.vw_dealership_performance
    UNION ALL
    SELECT 'vw_vehicle_type_performance', COALESCE(SUM(fact_row_count), 0),
           COALESCE(SUM(units_sold), 0), COALESCE(SUM(revenue), 0), COALESCE(SUM(gross_profit), 0)
    FROM analytics.vw_vehicle_type_performance
    UNION ALL
    SELECT 'vw_payment_method_performance', COALESCE(SUM(fact_row_count), 0),
           COALESCE(SUM(units_sold), 0), COALESCE(SUM(revenue), 0), COALESCE(SUM(gross_profit), 0)
    FROM analytics.vw_payment_method_performance
), checks AS (
    SELECT
        'detail_sale_id_uniqueness'::TEXT AS check_name,
        (SELECT fact_row_count - distinct_sale_count FROM detail_totals)::NUMERIC AS difference,
        'vw_sales_detail must contain exactly one row per sale_id.'::TEXT AS details

    UNION ALL
    SELECT 'detail_vs_fact_row_count',
           (SELECT fact_row_count FROM detail_totals) - (SELECT fact_row_count FROM fact_totals),
           'Eligible fact rows and canonical detail rows must match.'

    UNION ALL
    SELECT 'detail_vs_fact_units_sold',
           (SELECT units_sold FROM detail_totals) - (SELECT units_sold FROM fact_totals),
           'Detail units sold must reconcile to signed fact units.'

    UNION ALL
    SELECT 'detail_vs_fact_revenue',
           (SELECT revenue FROM detail_totals) - (SELECT revenue FROM fact_totals),
           'Detail revenue must reconcile to signed fact revenue.'

    UNION ALL
    SELECT 'detail_vs_fact_gross_profit',
           (SELECT gross_profit FROM detail_totals) - (SELECT gross_profit FROM fact_totals),
           'Detail gross profit must reconcile to signed fact gross profit.'

    UNION ALL
    SELECT 'kpi_vs_detail_row_count',
           (SELECT fact_row_count FROM kpi_totals) - (SELECT fact_row_count FROM detail_totals),
           'KPI fact-row count must reconcile to canonical detail.'

    UNION ALL
    SELECT 'kpi_vs_detail_units_sold',
           (SELECT units_sold FROM kpi_totals) - (SELECT units_sold FROM detail_totals),
           'KPI units sold must reconcile to canonical detail.'

    UNION ALL
    SELECT 'kpi_vs_detail_revenue',
           (SELECT revenue FROM kpi_totals) - (SELECT revenue FROM detail_totals),
           'KPI revenue must reconcile to canonical detail.'

    UNION ALL
    SELECT 'kpi_vs_detail_gross_profit',
           (SELECT gross_profit FROM kpi_totals) - (SELECT gross_profit FROM detail_totals),
           'KPI gross profit must reconcile to canonical detail.'

    UNION ALL
    SELECT view_name || '_row_count',
           fact_row_count - (SELECT fact_row_count FROM detail_totals),
           view_name || ' fact-row counts must reconcile to canonical detail.'
    FROM grouped_totals

    UNION ALL
    SELECT view_name || '_units_sold',
           units_sold - (SELECT units_sold FROM detail_totals),
           view_name || ' units sold must reconcile to canonical detail.'
    FROM grouped_totals

    UNION ALL
    SELECT view_name || '_revenue',
           revenue - (SELECT revenue FROM detail_totals),
           view_name || ' revenue must reconcile to canonical detail.'
    FROM grouped_totals

    UNION ALL
    SELECT view_name || '_gross_profit',
           gross_profit - (SELECT gross_profit FROM detail_totals),
           view_name || ' gross profit must reconcile to canonical detail.'
    FROM grouped_totals
)
SELECT
    check_name,
    CASE WHEN ABS(difference) <= 0.02 THEN 'PASS' ELSE 'FAIL' END AS status,
    difference,
    details
FROM checks
ORDER BY check_name;
