/*
Inventory analytics views.

Grain rule: analytics.vw_inventory_detail contains exactly one row per
fact_inventory.inventory_key (one vehicle at one dealership on one snapshot).
All aggregates retain snapshot_date so stock is never added across snapshots.

Aging buckets are mutually exclusive: 0-30, 31-60, 61-90, 91-120, and
120+ (implemented as more than 120 days because day 120 belongs to 91-120).
Slow-moving inventory is defined independently as more than 90 days.
*/

BEGIN;

CREATE OR REPLACE VIEW analytics.vw_inventory_detail AS
SELECT
    f.inventory_key,
    f.inventory_id,
    f.snapshot_date_key,
    d.full_date AS snapshot_date,
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
    f.acquired_date,
    f.inventory_status,
    f.on_hand_quantity AS inventory_units,
    f.carrying_cost AS inventory_value,
    f.days_in_inventory,
    CASE
        WHEN f.days_in_inventory BETWEEN 0 AND 30 THEN '0-30'
        WHEN f.days_in_inventory BETWEEN 31 AND 60 THEN '31-60'
        WHEN f.days_in_inventory BETWEEN 61 AND 90 THEN '61-90'
        WHEN f.days_in_inventory BETWEEN 91 AND 120 THEN '91-120'
        ELSE '120+'
    END AS aging_bucket,
    CASE
        WHEN f.days_in_inventory BETWEEN 0 AND 30 THEN 1
        WHEN f.days_in_inventory BETWEEN 31 AND 60 THEN 2
        WHEN f.days_in_inventory BETWEEN 61 AND 90 THEN 3
        WHEN f.days_in_inventory BETWEEN 91 AND 120 THEN 4
        ELSE 5
    END AS aging_bucket_sort,
    (f.days_in_inventory > 90) AS is_slow_moving
FROM analytics.fact_inventory f
JOIN analytics.dim_date d ON d.date_key = f.snapshot_date_key
JOIN analytics.dim_vehicle v ON v.vehicle_key = f.vehicle_key
JOIN analytics.dim_dealership dl ON dl.dealership_key = f.dealership_key;

COMMENT ON VIEW analytics.vw_inventory_detail IS
    'Canonical one-row-per-vehicle/dealership/snapshot inventory dataset; slow-moving means more than 90 days.';

CREATE OR REPLACE VIEW analytics.vw_inventory_kpis AS
SELECT
    snapshot_date_key,
    snapshot_date,
    SUM(inventory_units)::BIGINT AS inventory_units,
    SUM(inventory_value)::NUMERIC(18, 2) AS inventory_value,
    SUM(days_in_inventory * inventory_units)::BIGINT AS total_inventory_days,
    ROUND(
        SUM(days_in_inventory * inventory_units)::NUMERIC
        / NULLIF(SUM(inventory_units), 0),
        2
    ) AS average_age_days,
    COALESCE(SUM(inventory_units) FILTER (WHERE is_slow_moving), 0)::BIGINT AS slow_moving_units,
    COALESCE(SUM(inventory_value) FILTER (WHERE is_slow_moving), 0)::NUMERIC(18, 2) AS slow_moving_value,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT inventory_key)::BIGINT AS distinct_inventory_count
FROM analytics.vw_inventory_detail
GROUP BY snapshot_date_key, snapshot_date;

CREATE OR REPLACE VIEW analytics.vw_inventory_aging_buckets AS
SELECT
    snapshot_date_key,
    snapshot_date,
    aging_bucket,
    aging_bucket_sort,
    SUM(inventory_units)::BIGINT AS inventory_units,
    SUM(inventory_value)::NUMERIC(18, 2) AS inventory_value,
    ROUND(
        SUM(days_in_inventory * inventory_units)::NUMERIC
        / NULLIF(SUM(inventory_units), 0),
        2
    ) AS average_age_days,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT inventory_key)::BIGINT AS distinct_inventory_count
FROM analytics.vw_inventory_detail
GROUP BY snapshot_date_key, snapshot_date, aging_bucket, aging_bucket_sort;

CREATE OR REPLACE VIEW analytics.vw_brand_model_inventory AS
SELECT
    snapshot_date_key,
    snapshot_date,
    brand,
    model,
    model_year,
    SUM(inventory_units)::BIGINT AS inventory_units,
    SUM(inventory_value)::NUMERIC(18, 2) AS inventory_value,
    ROUND(
        SUM(days_in_inventory * inventory_units)::NUMERIC
        / NULLIF(SUM(inventory_units), 0),
        2
    ) AS average_age_days,
    COALESCE(SUM(inventory_units) FILTER (WHERE is_slow_moving), 0)::BIGINT AS slow_moving_units,
    COALESCE(SUM(inventory_value) FILTER (WHERE is_slow_moving), 0)::NUMERIC(18, 2) AS slow_moving_value,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT inventory_key)::BIGINT AS distinct_inventory_count
FROM analytics.vw_inventory_detail
GROUP BY snapshot_date_key, snapshot_date, brand, model, model_year;

CREATE OR REPLACE VIEW analytics.vw_dealership_inventory AS
SELECT
    snapshot_date_key,
    snapshot_date,
    dealership_key,
    dealership_id,
    dealership_name,
    region,
    state,
    SUM(inventory_units)::BIGINT AS inventory_units,
    SUM(inventory_value)::NUMERIC(18, 2) AS inventory_value,
    ROUND(
        SUM(days_in_inventory * inventory_units)::NUMERIC
        / NULLIF(SUM(inventory_units), 0),
        2
    ) AS average_age_days,
    COALESCE(SUM(inventory_units) FILTER (WHERE is_slow_moving), 0)::BIGINT AS slow_moving_units,
    COALESCE(SUM(inventory_value) FILTER (WHERE is_slow_moving), 0)::NUMERIC(18, 2) AS slow_moving_value,
    COUNT(*)::BIGINT AS fact_row_count,
    COUNT(DISTINCT inventory_key)::BIGINT AS distinct_inventory_count
FROM analytics.vw_inventory_detail
GROUP BY snapshot_date_key, snapshot_date, dealership_key, dealership_id,
         dealership_name, region, state;

CREATE OR REPLACE VIEW analytics.vw_slow_moving_vehicles AS
SELECT
    inventory_key,
    inventory_id,
    snapshot_date_key,
    snapshot_date,
    vehicle_key,
    vehicle_id,
    vin,
    brand,
    model,
    model_year,
    vehicle_type,
    fuel_type,
    vehicle_condition,
    dealership_key,
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
    aging_bucket_sort
FROM analytics.vw_inventory_detail
WHERE days_in_inventory > 90;

COMMIT;
