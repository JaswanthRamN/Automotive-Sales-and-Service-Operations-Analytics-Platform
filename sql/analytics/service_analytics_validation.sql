/*
Read-only reconciliation for service analytics views.
Every result must return PASS before downstream reporting is published.
*/

WITH source_appointments AS (
    SELECT
        COUNT(*)::BIGINT AS detail_row_count,
        COUNT(DISTINCT appointment_id)::BIGINT AS distinct_appointment_count,
        COUNT(*)::NUMERIC AS appointments,
        COUNT(*) FILTER (WHERE appointment_status = 'Completed')::NUMERIC AS completed_appointments,
        COUNT(*) FILTER (WHERE appointment_status = 'Cancelled')::NUMERIC AS cancellations,
        COUNT(*) FILTER (WHERE appointment_status = 'No Show')::NUMERIC AS no_shows
    FROM staging.service_appointments
), fact_totals AS (
    SELECT
        COUNT(*)::BIGINT AS repair_orders,
        COUNT(DISTINCT appointment_id)::BIGINT AS distinct_appointment_count,
        COALESCE(SUM(service_revenue), 0)::NUMERIC AS service_revenue
    FROM analytics.fact_service
), detail_totals AS (
    SELECT
        COUNT(*)::BIGINT AS detail_row_count,
        COUNT(DISTINCT appointment_id)::BIGINT AS distinct_appointment_count,
        SUM(appointment_count)::NUMERIC AS appointments,
        SUM(completed_appointment_count)::NUMERIC AS completed_appointments,
        SUM(cancellation_count)::NUMERIC AS cancellations,
        SUM(no_show_count)::NUMERIC AS no_shows,
        COUNT(service_order_id)::BIGINT AS repair_orders,
        COUNT(DISTINCT service_order_id)::BIGINT AS distinct_service_order_count,
        SUM(service_revenue)::NUMERIC AS service_revenue
    FROM analytics.vw_service_appointment_detail
), kpi_totals AS (
    SELECT detail_row_count, distinct_appointment_count,
           appointments::NUMERIC, completed_appointments::NUMERIC,
           cancellations::NUMERIC, no_shows::NUMERIC,
           repair_orders, service_revenue::NUMERIC
    FROM analytics.vw_service_kpis
), grouped_totals AS (
    SELECT 'vw_monthly_service_performance'::TEXT AS view_name,
           SUM(detail_row_count)::BIGINT AS detail_row_count,
           SUM(appointments)::NUMERIC AS appointments,
           SUM(completed_appointments)::NUMERIC AS completed_appointments,
           SUM(cancellations)::NUMERIC AS cancellations,
           SUM(no_shows)::NUMERIC AS no_shows,
           SUM(repair_orders)::BIGINT AS repair_orders,
           SUM(service_revenue)::NUMERIC AS service_revenue
    FROM analytics.vw_monthly_service_performance
    UNION ALL
    SELECT 'vw_service_type_performance', SUM(detail_row_count), SUM(appointments),
           SUM(completed_appointments), SUM(cancellations), SUM(no_shows),
           SUM(repair_orders), SUM(service_revenue)
    FROM analytics.vw_service_type_performance
    UNION ALL
    SELECT 'vw_dealership_service_performance', SUM(detail_row_count), SUM(appointments),
           SUM(completed_appointments), SUM(cancellations), SUM(no_shows),
           SUM(repair_orders), SUM(service_revenue)
    FROM analytics.vw_dealership_service_performance
), technician_totals AS (
    SELECT SUM(detail_row_count)::BIGINT AS detail_row_count,
           SUM(repair_orders)::BIGINT AS repair_orders,
           SUM(service_revenue)::NUMERIC AS service_revenue
    FROM analytics.vw_technician_service_performance
), checks AS (
    SELECT 'detail_appointment_uniqueness'::TEXT AS check_name,
           (SELECT detail_row_count - distinct_appointment_count FROM detail_totals)::NUMERIC AS difference,
           'Canonical detail must contain exactly one row per appointment_id.'::TEXT AS details

    UNION ALL
    SELECT 'detail_vs_source_appointments',
           (SELECT detail_row_count FROM detail_totals) - (SELECT detail_row_count FROM source_appointments),
           'Canonical detail row count must equal staging appointments.'

    UNION ALL
    SELECT 'detail_vs_source_completed',
           (SELECT completed_appointments FROM detail_totals) - (SELECT completed_appointments FROM source_appointments),
           'Completed appointment count must match staging.'

    UNION ALL
    SELECT 'detail_vs_source_cancellations',
           (SELECT cancellations FROM detail_totals) - (SELECT cancellations FROM source_appointments),
           'Cancellation count must match staging.'

    UNION ALL
    SELECT 'detail_vs_source_no_shows',
           (SELECT no_shows FROM detail_totals) - (SELECT no_shows FROM source_appointments),
           'No-show count must match staging.'

    UNION ALL
    SELECT 'detail_repair_order_uniqueness',
           (SELECT repair_orders - distinct_service_order_count FROM detail_totals)::NUMERIC,
           'Joining repair orders must not duplicate service_order_id.'

    UNION ALL
    SELECT 'detail_vs_fact_repair_orders',
           (SELECT repair_orders FROM detail_totals) - (SELECT repair_orders FROM fact_totals),
           'Canonical detail repair orders must match fact_service.'

    UNION ALL
    SELECT 'detail_vs_fact_service_revenue',
           (SELECT service_revenue FROM detail_totals) - (SELECT service_revenue FROM fact_totals),
           'Canonical detail service revenue must match fact_service without duplication.'

    UNION ALL
    SELECT 'kpis_vs_detail_appointments',
           (SELECT appointments FROM kpi_totals) - (SELECT appointments FROM detail_totals),
           'KPI appointments must reconcile to detail.'

    UNION ALL
    SELECT 'kpis_vs_detail_service_revenue',
           (SELECT service_revenue FROM kpi_totals) - (SELECT service_revenue FROM detail_totals),
           'KPI service revenue must reconcile to detail.'

    UNION ALL
    SELECT view_name || '_appointments',
           appointments - (SELECT appointments FROM detail_totals),
           view_name || ' appointments must reconcile to detail.'
    FROM grouped_totals

    UNION ALL
    SELECT view_name || '_completed_appointments',
           completed_appointments - (SELECT completed_appointments FROM detail_totals),
           view_name || ' completed appointments must reconcile to detail.'
    FROM grouped_totals

    UNION ALL
    SELECT view_name || '_cancellations',
           cancellations - (SELECT cancellations FROM detail_totals),
           view_name || ' cancellations must reconcile to detail.'
    FROM grouped_totals

    UNION ALL
    SELECT view_name || '_no_shows',
           no_shows - (SELECT no_shows FROM detail_totals),
           view_name || ' no-shows must reconcile to detail.'
    FROM grouped_totals

    UNION ALL
    SELECT view_name || '_service_revenue',
           service_revenue - (SELECT service_revenue FROM detail_totals),
           view_name || ' service revenue must reconcile to detail.'
    FROM grouped_totals

    UNION ALL
    SELECT 'technician_view_repair_orders',
           (SELECT repair_orders FROM technician_totals) - (SELECT repair_orders FROM fact_totals),
           'Technician repair orders must reconcile to fact_service.'

    UNION ALL
    SELECT 'technician_view_service_revenue',
           (SELECT service_revenue FROM technician_totals) - (SELECT service_revenue FROM fact_totals),
           'Technician service revenue must reconcile to fact_service.'

    UNION ALL
    SELECT 'completed_appointments_have_one_order', COUNT(*)::NUMERIC,
           'Each completed appointment must resolve to exactly one service order.'
    FROM analytics.vw_service_appointment_detail
    WHERE appointment_status = 'Completed' AND service_order_id IS NULL

    UNION ALL
    SELECT 'service_cost_not_fabricated', COUNT(*)::NUMERIC,
           'Cost and profit must remain NULL while authoritative service cost is unavailable.'
    FROM analytics.vw_service_appointment_detail
    WHERE service_cost IS NOT NULL OR service_profit IS NOT NULL OR service_cost_available
)
SELECT
    check_name,
    CASE WHEN ABS(difference) <= 0.02 THEN 'PASS' ELSE 'FAIL' END AS status,
    difference,
    details
FROM checks
ORDER BY check_name;
