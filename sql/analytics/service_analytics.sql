/*
Service analytics views.

Grain rule: analytics.vw_service_appointment_detail contains exactly one row
per staging.service_appointments.appointment_id. fact_service is joined only by
its unique appointment_id, so repair-order revenue cannot be duplicated.

Completion rate denominator: completed + cancelled + no-show appointments.
Scheduled appointments are excluded until they reach a terminal status.

The current source model has revenue but no labor/parts cost. service_cost and
service_profit are therefore NULL (not estimated), and service_cost_available
is FALSE until authoritative cost is added to the warehouse.
*/

BEGIN;

CREATE OR REPLACE VIEW analytics.vw_service_appointment_detail AS
SELECT
    a.appointment_id,
    TO_CHAR(a.appointment_date::DATE, 'YYYYMMDD')::INTEGER AS appointment_date_key,
    d.full_date AS appointment_date,
    d.calendar_year,
    d.quarter_number,
    d.month_number,
    d.month_name,
    a.appointment_time::TIME AS appointment_time,
    c.customer_key,
    c.customer_id,
    v.vehicle_key,
    v.vehicle_id,
    v.vin,
    v.make AS vehicle_brand,
    v.model AS vehicle_model,
    dl.dealership_key,
    dl.dealership_id,
    dl.dealership_name,
    dl.region,
    dl.state,
    advisor.employee_key AS service_advisor_key,
    advisor.employee_id AS service_advisor_id,
    advisor.first_name || ' ' || advisor.last_name AS service_advisor_name,
    svc.service_key,
    svc.service_type,
    svc.service_category,
    a.appointment_status,
    1::SMALLINT AS appointment_count,
    CASE WHEN a.appointment_status = 'Completed' THEN 1 ELSE 0 END::SMALLINT AS completed_appointment_count,
    CASE WHEN a.appointment_status = 'Cancelled' THEN 1 ELSE 0 END::SMALLINT AS cancellation_count,
    CASE WHEN a.appointment_status = 'No Show' THEN 1 ELSE 0 END::SMALLINT AS no_show_count,
    CASE WHEN a.appointment_status IN ('Completed', 'Cancelled', 'No Show') THEN 1 ELSE 0 END::SMALLINT AS completion_eligible_count,
    fs.service_fact_key,
    fs.service_order_id,
    fs.repair_order_quantity,
    fs.technician_key,
    technician.employee_id AS technician_id,
    CASE
        WHEN technician.employee_key IS NULL THEN NULL
        ELSE technician.first_name || ' ' || technician.last_name
    END AS technician_name,
    fs.payer_type,
    fs.opened_at,
    fs.promised_at,
    fs.completed_at,
    fs.completed_on_time,
    fs.turnaround_hours,
    COALESCE(fs.labor_revenue, 0)::NUMERIC(16, 2) AS labor_revenue,
    COALESCE(fs.parts_revenue, 0)::NUMERIC(16, 2) AS parts_revenue,
    COALESCE(fs.discount_amount, 0)::NUMERIC(16, 2) AS discount_amount,
    COALESCE(fs.service_revenue, 0)::NUMERIC(16, 2) AS service_revenue,
    NULL::NUMERIC(16, 2) AS service_cost,
    NULL::NUMERIC(16, 2) AS service_profit,
    FALSE AS service_cost_available
FROM staging.service_appointments a
JOIN analytics.dim_date d
  ON d.full_date = a.appointment_date::DATE
JOIN analytics.dim_customer c
  ON c.customer_id = a.customer_id AND c.is_current
JOIN analytics.dim_vehicle v
  ON v.vehicle_id = a.vehicle_id
JOIN analytics.dim_dealership dl
  ON dl.dealership_id = a.dealership_id
JOIN analytics.dim_employee advisor
  ON advisor.employee_id = a.service_advisor_id AND advisor.is_current
JOIN analytics.dim_service svc
  ON svc.service_type = a.service_type
LEFT JOIN analytics.fact_service fs
  ON fs.appointment_id = a.appointment_id
LEFT JOIN analytics.dim_employee technician
  ON technician.employee_key = fs.technician_key;

COMMENT ON VIEW analytics.vw_service_appointment_detail IS
    'Canonical one-row-per-appointment service dataset; repair-order revenue joins one-to-one and cost/profit remain NULL until authoritative cost exists.';

CREATE OR REPLACE VIEW analytics.vw_service_kpis AS
SELECT
    SUM(appointment_count)::BIGINT AS appointments,
    SUM(completed_appointment_count)::BIGINT AS completed_appointments,
    SUM(cancellation_count)::BIGINT AS cancellations,
    SUM(no_show_count)::BIGINT AS no_shows,
    ROUND(
        SUM(completed_appointment_count)::NUMERIC
        / NULLIF(SUM(completion_eligible_count), 0) * 100,
        2
    ) AS completion_rate_percent,
    COUNT(service_order_id)::BIGINT AS repair_orders,
    SUM(service_revenue)::NUMERIC(18, 2) AS service_revenue,
    SUM(service_cost)::NUMERIC(18, 2) AS service_cost,
    SUM(service_profit)::NUMERIC(18, 2) AS service_profit,
    BOOL_AND(service_cost_available) AS service_cost_available,
    ROUND(
        SUM(service_revenue) / NULLIF(COUNT(service_order_id), 0),
        2
    ) AS average_repair_order,
    COUNT(*)::BIGINT AS detail_row_count,
    COUNT(DISTINCT appointment_id)::BIGINT AS distinct_appointment_count
FROM analytics.vw_service_appointment_detail;

CREATE OR REPLACE VIEW analytics.vw_monthly_service_performance AS
SELECT
    calendar_year,
    month_number,
    MIN(appointment_date) AS month_start_date,
    month_name,
    SUM(appointment_count)::BIGINT AS appointments,
    SUM(completed_appointment_count)::BIGINT AS completed_appointments,
    SUM(cancellation_count)::BIGINT AS cancellations,
    SUM(no_show_count)::BIGINT AS no_shows,
    ROUND(
        SUM(completed_appointment_count)::NUMERIC
        / NULLIF(SUM(completion_eligible_count), 0) * 100,
        2
    ) AS completion_rate_percent,
    COUNT(service_order_id)::BIGINT AS repair_orders,
    SUM(service_revenue)::NUMERIC(18, 2) AS service_revenue,
    SUM(service_cost)::NUMERIC(18, 2) AS service_cost,
    SUM(service_profit)::NUMERIC(18, 2) AS service_profit,
    ROUND(SUM(service_revenue) / NULLIF(COUNT(service_order_id), 0), 2) AS average_repair_order,
    COUNT(*)::BIGINT AS detail_row_count,
    COUNT(DISTINCT appointment_id)::BIGINT AS distinct_appointment_count
FROM analytics.vw_service_appointment_detail
GROUP BY calendar_year, month_number, month_name;

CREATE OR REPLACE VIEW analytics.vw_service_type_performance AS
SELECT
    service_key,
    service_type,
    service_category,
    SUM(appointment_count)::BIGINT AS appointments,
    SUM(completed_appointment_count)::BIGINT AS completed_appointments,
    SUM(cancellation_count)::BIGINT AS cancellations,
    SUM(no_show_count)::BIGINT AS no_shows,
    ROUND(
        SUM(completed_appointment_count)::NUMERIC
        / NULLIF(SUM(completion_eligible_count), 0) * 100,
        2
    ) AS completion_rate_percent,
    COUNT(service_order_id)::BIGINT AS repair_orders,
    SUM(service_revenue)::NUMERIC(18, 2) AS service_revenue,
    SUM(service_cost)::NUMERIC(18, 2) AS service_cost,
    SUM(service_profit)::NUMERIC(18, 2) AS service_profit,
    ROUND(SUM(service_revenue) / NULLIF(COUNT(service_order_id), 0), 2) AS average_repair_order,
    COUNT(*)::BIGINT AS detail_row_count,
    COUNT(DISTINCT appointment_id)::BIGINT AS distinct_appointment_count
FROM analytics.vw_service_appointment_detail
GROUP BY service_key, service_type, service_category;

CREATE OR REPLACE VIEW analytics.vw_dealership_service_performance AS
SELECT
    dealership_key,
    dealership_id,
    dealership_name,
    region,
    state,
    SUM(appointment_count)::BIGINT AS appointments,
    SUM(completed_appointment_count)::BIGINT AS completed_appointments,
    SUM(cancellation_count)::BIGINT AS cancellations,
    SUM(no_show_count)::BIGINT AS no_shows,
    ROUND(
        SUM(completed_appointment_count)::NUMERIC
        / NULLIF(SUM(completion_eligible_count), 0) * 100,
        2
    ) AS completion_rate_percent,
    COUNT(service_order_id)::BIGINT AS repair_orders,
    SUM(service_revenue)::NUMERIC(18, 2) AS service_revenue,
    SUM(service_cost)::NUMERIC(18, 2) AS service_cost,
    SUM(service_profit)::NUMERIC(18, 2) AS service_profit,
    ROUND(SUM(service_revenue) / NULLIF(COUNT(service_order_id), 0), 2) AS average_repair_order,
    COUNT(*)::BIGINT AS detail_row_count,
    COUNT(DISTINCT appointment_id)::BIGINT AS distinct_appointment_count
FROM analytics.vw_service_appointment_detail
GROUP BY dealership_key, dealership_id, dealership_name, region, state;

CREATE OR REPLACE VIEW analytics.vw_technician_service_performance AS
SELECT
    technician_key,
    technician_id,
    technician_name,
    dealership_key,
    dealership_id,
    dealership_name,
    COUNT(service_order_id)::BIGINT AS repair_orders,
    SUM(service_revenue)::NUMERIC(18, 2) AS service_revenue,
    SUM(service_cost)::NUMERIC(18, 2) AS service_cost,
    SUM(service_profit)::NUMERIC(18, 2) AS service_profit,
    ROUND(SUM(service_revenue) / NULLIF(COUNT(service_order_id), 0), 2) AS average_repair_order,
    ROUND(AVG(turnaround_hours), 2) AS average_turnaround_hours,
    ROUND(
        COUNT(*) FILTER (WHERE completed_on_time)::NUMERIC
        / NULLIF(COUNT(service_order_id), 0) * 100,
        2
    ) AS on_time_completion_rate_percent,
    COUNT(*)::BIGINT AS detail_row_count,
    COUNT(DISTINCT service_order_id)::BIGINT AS distinct_service_order_count
FROM analytics.vw_service_appointment_detail
WHERE service_order_id IS NOT NULL
GROUP BY technician_key, technician_id, technician_name,
         dealership_key, dealership_id, dealership_name;

COMMIT;
