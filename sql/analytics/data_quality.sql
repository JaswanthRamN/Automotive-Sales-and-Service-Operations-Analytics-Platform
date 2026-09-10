/*
Warehouse data-quality checks.

This script is read-only. It returns one row per check with:
  check_category, check_name, status, failed_count, details

The warehouse passes only when every row has status = 'PASS'.
Run after the ETL has populated the analytics schema.
*/

WITH quality_checks AS (
    -- Duplicate dimension business keys and current records.
    SELECT 'duplicates'::TEXT AS check_category,
           'dim_customer duplicate current customer_id'::TEXT AS check_name,
           COUNT(*)::BIGINT AS failed_count,
           'Keep exactly one current dimension row per customer_id.'::TEXT AS details
    FROM (
        SELECT customer_id
        FROM analytics.dim_customer
        WHERE is_current
        GROUP BY customer_id
        HAVING COUNT(*) > 1
    ) failures

    UNION ALL
    SELECT 'duplicates', 'dim_vehicle duplicate vehicle_id or vin', COUNT(*)::BIGINT,
           'Each vehicle_id and VIN must identify one vehicle.'
    FROM (
        SELECT vehicle_id FROM analytics.dim_vehicle GROUP BY vehicle_id HAVING COUNT(*) > 1
        UNION ALL
        SELECT vin FROM analytics.dim_vehicle GROUP BY vin HAVING COUNT(*) > 1
    ) failures

    UNION ALL
    SELECT 'duplicates', 'dim_employee duplicate current employee_id', COUNT(*)::BIGINT,
           'Keep exactly one current dimension row per employee_id.'
    FROM (
        SELECT employee_id
        FROM analytics.dim_employee
        WHERE is_current
        GROUP BY employee_id
        HAVING COUNT(*) > 1
    ) failures

    UNION ALL
    SELECT 'duplicates', 'dim_dealership duplicate dealership_id', COUNT(*)::BIGINT,
           'Each dealership_id must identify one dealership.'
    FROM (
        SELECT dealership_id FROM analytics.dim_dealership GROUP BY dealership_id HAVING COUNT(*) > 1
    ) failures

    UNION ALL
    SELECT 'duplicates', 'dim_service duplicate service_type', COUNT(*)::BIGINT,
           'Each service_type must identify one service dimension row.'
    FROM (
        SELECT service_type FROM analytics.dim_service GROUP BY service_type HAVING COUNT(*) > 1
    ) failures

    -- Duplicate facts at their declared grain.
    UNION ALL
    SELECT 'duplicate_facts', 'fact_sales duplicate sale_id', COUNT(*)::BIGINT,
           'fact_sales grain is one row per sale_id.'
    FROM (
        SELECT sale_id FROM analytics.fact_sales GROUP BY sale_id HAVING COUNT(*) > 1
    ) failures

    UNION ALL
    SELECT 'duplicate_facts', 'fact_inventory duplicate vehicle snapshot', COUNT(*)::BIGINT,
           'fact_inventory grain is one vehicle per dealership and snapshot date.'
    FROM (
        SELECT vehicle_key, dealership_key, snapshot_date_key
        FROM analytics.fact_inventory
        GROUP BY vehicle_key, dealership_key, snapshot_date_key
        HAVING COUNT(*) > 1
    ) failures

    UNION ALL
    SELECT 'duplicate_facts', 'fact_service duplicate order or appointment', COUNT(*)::BIGINT,
           'Each service_order_id and appointment_id must occur once.'
    FROM (
        SELECT service_order_id FROM analytics.fact_service GROUP BY service_order_id HAVING COUNT(*) > 1
        UNION ALL
        SELECT appointment_id FROM analytics.fact_service GROUP BY appointment_id HAVING COUNT(*) > 1
    ) failures

    -- Missing foreign-key values (separate from orphan checks for clearer diagnosis).
    UNION ALL
    SELECT 'missing_foreign_keys', 'fact_sales missing foreign keys', COUNT(*)::BIGINT,
           'Populate date, customer, vehicle, dealership, and salesperson keys.'
    FROM analytics.fact_sales
    WHERE sale_date_key IS NULL OR customer_key IS NULL OR vehicle_key IS NULL
       OR dealership_key IS NULL OR salesperson_key IS NULL

    UNION ALL
    SELECT 'missing_foreign_keys', 'fact_inventory missing foreign keys', COUNT(*)::BIGINT,
           'Populate snapshot date, vehicle, and dealership keys.'
    FROM analytics.fact_inventory
    WHERE snapshot_date_key IS NULL OR vehicle_key IS NULL OR dealership_key IS NULL

    UNION ALL
    SELECT 'missing_foreign_keys', 'fact_service missing foreign keys', COUNT(*)::BIGINT,
           'Populate date, customer, vehicle, dealership, advisor, technician, and service keys.'
    FROM analytics.fact_service
    WHERE completed_date_key IS NULL OR customer_key IS NULL OR vehicle_key IS NULL
       OR dealership_key IS NULL OR service_advisor_key IS NULL
       OR technician_key IS NULL OR service_key IS NULL

    -- Orphan records. These also detect disabled or NOT VALID constraints.
    UNION ALL
    SELECT 'orphan_records', 'dim_employee orphan dealership', COUNT(*)::BIGINT,
           'Every employee dealership_key must resolve to dim_dealership.'
    FROM analytics.dim_employee e
    LEFT JOIN analytics.dim_dealership d ON d.dealership_key = e.dealership_key
    WHERE d.dealership_key IS NULL

    UNION ALL
    SELECT 'orphan_records', 'fact_sales orphan dimension keys', COUNT(*)::BIGINT,
           'Every fact_sales foreign key must resolve to its conformed dimension.'
    FROM analytics.fact_sales f
    LEFT JOIN analytics.dim_date dt ON dt.date_key = f.sale_date_key
    LEFT JOIN analytics.dim_customer c ON c.customer_key = f.customer_key
    LEFT JOIN analytics.dim_vehicle v ON v.vehicle_key = f.vehicle_key
    LEFT JOIN analytics.dim_dealership d ON d.dealership_key = f.dealership_key
    LEFT JOIN analytics.dim_employee e ON e.employee_key = f.salesperson_key
    WHERE dt.date_key IS NULL OR c.customer_key IS NULL OR v.vehicle_key IS NULL
       OR d.dealership_key IS NULL OR e.employee_key IS NULL

    UNION ALL
    SELECT 'orphan_records', 'fact_inventory orphan dimension keys', COUNT(*)::BIGINT,
           'Every fact_inventory foreign key must resolve to its conformed dimension.'
    FROM analytics.fact_inventory f
    LEFT JOIN analytics.dim_date dt ON dt.date_key = f.snapshot_date_key
    LEFT JOIN analytics.dim_vehicle v ON v.vehicle_key = f.vehicle_key
    LEFT JOIN analytics.dim_dealership d ON d.dealership_key = f.dealership_key
    WHERE dt.date_key IS NULL OR v.vehicle_key IS NULL OR d.dealership_key IS NULL

    UNION ALL
    SELECT 'orphan_records', 'fact_service orphan dimension keys', COUNT(*)::BIGINT,
           'Every fact_service foreign key must resolve to its conformed dimension.'
    FROM analytics.fact_service f
    LEFT JOIN analytics.dim_date dt ON dt.date_key = f.completed_date_key
    LEFT JOIN analytics.dim_customer c ON c.customer_key = f.customer_key
    LEFT JOIN analytics.dim_vehicle v ON v.vehicle_key = f.vehicle_key
    LEFT JOIN analytics.dim_dealership d ON d.dealership_key = f.dealership_key
    LEFT JOIN analytics.dim_employee a ON a.employee_key = f.service_advisor_key
    LEFT JOIN analytics.dim_employee t ON t.employee_key = f.technician_key
    LEFT JOIN analytics.dim_service s ON s.service_key = f.service_key
    WHERE dt.date_key IS NULL OR c.customer_key IS NULL OR v.vehicle_key IS NULL
       OR d.dealership_key IS NULL OR a.employee_key IS NULL
       OR t.employee_key IS NULL OR s.service_key IS NULL

    -- Invalid business and fact dates.
    UNION ALL
    SELECT 'invalid_dates', 'dimension dates outside valid order', COUNT(*)::BIGINT,
           'Customer, dealership, and employee dates must not be in the future; effective ranges must be ordered.'
    FROM (
        SELECT customer_key::BIGINT AS row_key
        FROM analytics.dim_customer
        WHERE customer_since_date > CURRENT_DATE OR effective_from > effective_to
        UNION ALL
        SELECT dealership_key FROM analytics.dim_dealership
        WHERE opened_date > CURRENT_DATE OR effective_from > effective_to
        UNION ALL
        SELECT employee_key FROM analytics.dim_employee
        WHERE hire_date > CURRENT_DATE OR effective_from > effective_to
    ) failures

    UNION ALL
    SELECT 'invalid_dates', 'fact_sales invalid or future sale date', COUNT(*)::BIGINT,
           'The sale date key must resolve to a nonfuture calendar date.'
    FROM analytics.fact_sales f
    JOIN analytics.dim_date d ON d.date_key = f.sale_date_key
    WHERE d.full_date > CURRENT_DATE

    UNION ALL
    SELECT 'invalid_dates', 'fact_inventory invalid acquisition or snapshot date', COUNT(*)::BIGINT,
           'Acquisition must be on or before the inventory snapshot and days_in_inventory must match.'
    FROM analytics.fact_inventory f
    JOIN analytics.dim_date d ON d.date_key = f.snapshot_date_key
    WHERE f.acquired_date > d.full_date
       OR f.days_in_inventory <> (d.full_date - f.acquired_date)
       OR f.slow_moving_flag IS DISTINCT FROM ((d.full_date - f.acquired_date) > 90)

    UNION ALL
    SELECT 'invalid_dates', 'fact_service invalid timestamp order or date key', COUNT(*)::BIGINT,
           'Opened time must precede promised/completed time and completed_date_key must match completed_at.'
    FROM analytics.fact_service f
    JOIN analytics.dim_date d ON d.date_key = f.completed_date_key
    WHERE f.opened_at > f.promised_at OR f.opened_at > f.completed_at
       OR d.full_date <> f.completed_at::DATE OR f.completed_at::DATE > CURRENT_DATE

    -- Invalid prices and arithmetic.
    UNION ALL
    SELECT 'invalid_prices', 'fact_sales invalid price relationship', COUNT(*)::BIGINT,
           'Prices and costs must be nonnegative; discount cannot exceed list price; derived amounts must reconcile within two cents.'
    FROM analytics.fact_sales
    WHERE list_price < 0 OR discount_amount < 0 OR sale_price < 0 OR vehicle_cost < 0
       OR discount_amount > list_price
       OR ABS((list_price - discount_amount) - sale_price) > 0.02
       OR ABS((sale_price - vehicle_cost) - gross_profit) > 0.02

    UNION ALL
    SELECT 'invalid_prices', 'fact_inventory invalid carrying value or age', COUNT(*)::BIGINT,
           'Inventory carrying cost and age must be nonnegative.'
    FROM analytics.fact_inventory
    WHERE carrying_cost < 0 OR days_in_inventory < 0 OR on_hand_quantity <> 1

    UNION ALL
    SELECT 'invalid_prices', 'fact_service invalid revenue relationship', COUNT(*)::BIGINT,
           'Service components must be nonnegative and reconcile to service_revenue within two cents.'
    FROM analytics.fact_service
    WHERE labor_revenue < 0 OR parts_revenue < 0 OR discount_amount < 0
       OR discount_amount > labor_revenue + parts_revenue
       OR ABS((labor_revenue + parts_revenue - discount_amount) - service_revenue) > 0.02

    -- Negative recognized revenue is never valid in the current completed-fact model.
    UNION ALL
    SELECT 'negative_revenue', 'fact_sales negative revenue', COUNT(*)::BIGINT,
           'Investigate or model returns separately; completed sale revenue cannot be negative.'
    FROM analytics.fact_sales
    WHERE sale_price < 0

    UNION ALL
    SELECT 'negative_revenue', 'fact_service negative revenue', COUNT(*)::BIGINT,
           'Investigate refunds separately; completed service revenue cannot be negative.'
    FROM analytics.fact_service
    WHERE service_revenue < 0
)
SELECT
    check_category,
    check_name,
    CASE WHEN failed_count = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    failed_count,
    details
FROM quality_checks
ORDER BY check_category, check_name;
