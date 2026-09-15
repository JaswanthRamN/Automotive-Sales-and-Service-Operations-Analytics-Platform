/*
Read-only, snapshot-level reconciliation for inventory analytics views.
Every result must return PASS before downstream reporting is published.
*/

WITH fact_totals AS (
    SELECT
        snapshot_date_key,
        COUNT(*)::BIGINT AS fact_row_count,
        COUNT(DISTINCT inventory_key)::BIGINT AS distinct_inventory_count,
        SUM(on_hand_quantity)::BIGINT AS inventory_units,
        SUM(carrying_cost)::NUMERIC AS inventory_value,
        SUM(days_in_inventory * on_hand_quantity)::NUMERIC AS total_inventory_days
    FROM analytics.fact_inventory
    GROUP BY snapshot_date_key
), detail_totals AS (
    SELECT
        snapshot_date_key,
        COUNT(*)::BIGINT AS fact_row_count,
        COUNT(DISTINCT inventory_key)::BIGINT AS distinct_inventory_count,
        SUM(inventory_units)::BIGINT AS inventory_units,
        SUM(inventory_value)::NUMERIC AS inventory_value,
        SUM(days_in_inventory * inventory_units)::NUMERIC AS total_inventory_days
    FROM analytics.vw_inventory_detail
    GROUP BY snapshot_date_key
), grouped_totals AS (
    SELECT 'vw_inventory_aging_buckets'::TEXT AS view_name, snapshot_date_key,
           SUM(fact_row_count)::BIGINT AS fact_row_count,
           SUM(inventory_units)::BIGINT AS inventory_units,
           SUM(inventory_value)::NUMERIC AS inventory_value
    FROM analytics.vw_inventory_aging_buckets
    GROUP BY snapshot_date_key

    UNION ALL
    SELECT 'vw_brand_model_inventory', snapshot_date_key,
           SUM(fact_row_count), SUM(inventory_units), SUM(inventory_value)
    FROM analytics.vw_brand_model_inventory
    GROUP BY snapshot_date_key

    UNION ALL
    SELECT 'vw_dealership_inventory', snapshot_date_key,
           SUM(fact_row_count), SUM(inventory_units), SUM(inventory_value)
    FROM analytics.vw_dealership_inventory
    GROUP BY snapshot_date_key
), slow_detail AS (
    SELECT snapshot_date_key,
           COUNT(*)::BIGINT AS fact_row_count,
           SUM(inventory_units)::BIGINT AS inventory_units,
           SUM(inventory_value)::NUMERIC AS inventory_value
    FROM analytics.vw_inventory_detail
    WHERE days_in_inventory > 90
    GROUP BY snapshot_date_key
), slow_view AS (
    SELECT snapshot_date_key,
           COUNT(*)::BIGINT AS fact_row_count,
           SUM(inventory_units)::BIGINT AS inventory_units,
           SUM(inventory_value)::NUMERIC AS inventory_value
    FROM analytics.vw_slow_moving_vehicles
    GROUP BY snapshot_date_key
), checks AS (
    SELECT
        'detail_inventory_key_uniqueness'::TEXT AS check_name,
        COUNT(*)::BIGINT AS failed_count,
        'Each canonical inventory detail row must have a unique inventory_key.'::TEXT AS details
    FROM (
        SELECT inventory_key
        FROM analytics.vw_inventory_detail
        GROUP BY inventory_key
        HAVING COUNT(*) > 1
    ) failures

    UNION ALL
    SELECT 'detail_vs_fact_by_snapshot', COUNT(*),
           'Detail rows, units, value, and weighted days must match fact_inventory for every snapshot.'
    FROM fact_totals f
    FULL JOIN detail_totals d USING (snapshot_date_key)
    WHERE f.snapshot_date_key IS NULL OR d.snapshot_date_key IS NULL
       OR f.fact_row_count <> d.fact_row_count
       OR f.distinct_inventory_count <> d.distinct_inventory_count
       OR f.inventory_units <> d.inventory_units
       OR ABS(f.inventory_value - d.inventory_value) > 0.02
       OR f.total_inventory_days <> d.total_inventory_days

    UNION ALL
    SELECT 'kpis_vs_detail_by_snapshot', COUNT(*),
           'Inventory KPI rows must reconcile to canonical detail for every snapshot.'
    FROM detail_totals d
    FULL JOIN analytics.vw_inventory_kpis k USING (snapshot_date_key)
    WHERE d.snapshot_date_key IS NULL OR k.snapshot_date_key IS NULL
       OR d.fact_row_count <> k.fact_row_count
       OR d.distinct_inventory_count <> k.distinct_inventory_count
       OR d.inventory_units <> k.inventory_units
       OR ABS(d.inventory_value - k.inventory_value) > 0.02
       OR d.total_inventory_days <> k.total_inventory_days

    UNION ALL
    SELECT view_name || '_vs_detail_by_snapshot', COUNT(*),
           view_name || ' rows, units, and value must reconcile for every snapshot.'
    FROM grouped_totals g
    FULL JOIN detail_totals d USING (snapshot_date_key)
    WHERE g.snapshot_date_key IS NULL OR d.snapshot_date_key IS NULL
       OR g.fact_row_count <> d.fact_row_count
       OR g.inventory_units <> d.inventory_units
       OR ABS(g.inventory_value - d.inventory_value) > 0.02
    GROUP BY view_name

    UNION ALL
    SELECT 'slow_moving_view_vs_detail_by_snapshot', COUNT(*),
           'Slow-moving rows, units, and value must equal detail rows over 90 days for every snapshot.'
    FROM slow_detail d
    FULL JOIN slow_view v USING (snapshot_date_key)
    WHERE d.snapshot_date_key IS NULL OR v.snapshot_date_key IS NULL
       OR d.fact_row_count <> v.fact_row_count
       OR d.inventory_units <> v.inventory_units
       OR ABS(d.inventory_value - v.inventory_value) > 0.02

    UNION ALL
    SELECT 'aging_bucket_assignment', COUNT(*),
           'Every row must have the mutually exclusive bucket dictated by days_in_inventory.'
    FROM analytics.vw_inventory_detail
    WHERE aging_bucket IS DISTINCT FROM CASE
        WHEN days_in_inventory BETWEEN 0 AND 30 THEN '0-30'
        WHEN days_in_inventory BETWEEN 31 AND 60 THEN '31-60'
        WHEN days_in_inventory BETWEEN 61 AND 90 THEN '61-90'
        WHEN days_in_inventory BETWEEN 91 AND 120 THEN '91-120'
        ELSE '120+'
    END

    UNION ALL
    SELECT 'slow_moving_definition', COUNT(*),
           'is_slow_moving must be true exactly when days_in_inventory is greater than 90.'
    FROM analytics.vw_inventory_detail
    WHERE is_slow_moving IS DISTINCT FROM (days_in_inventory > 90)
)
SELECT
    check_name,
    CASE WHEN failed_count = 0 THEN 'PASS' ELSE 'FAIL' END AS status,
    failed_count,
    details
FROM checks
ORDER BY check_name;
