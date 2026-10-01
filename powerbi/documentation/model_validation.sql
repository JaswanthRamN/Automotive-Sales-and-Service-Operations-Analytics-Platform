/* Read-only acceptance checks for the proposed model's PostgreSQL sources.
   This does not validate Power BI relationship settings or execute M/DAX. */
WITH dimension_keys AS (
    SELECT 'Customer' AS dimension, customer_key::bigint AS key FROM analytics.dim_customer
    UNION ALL SELECT 'Vehicle', vehicle_key FROM analytics.dim_vehicle
    UNION ALL SELECT 'Dealership', dealership_key FROM analytics.dim_dealership
    UNION ALL SELECT 'Salesperson', employee_key FROM analytics.dim_employee WHERE role='Sales Consultant'
    UNION ALL SELECT 'Advisor', employee_key FROM analytics.dim_employee WHERE role='Service Advisor'
    UNION ALL SELECT 'Technician', employee_key FROM analytics.dim_employee WHERE role='Service Technician'
    UNION ALL SELECT 'Service', service_key FROM analytics.dim_service
    UNION ALL SELECT 'Date', date_key FROM analytics.dim_date
), fact_keys AS (
    SELECT 'Sales' AS fact, sales_key::text AS key FROM analytics.vw_sales_detail
    UNION ALL SELECT 'Inventory', inventory_key::text FROM analytics.vw_inventory_detail
    UNION ALL SELECT 'Service', appointment_id FROM analytics.vw_service_appointment_detail
), foreign_keys AS (
    SELECT 'Sales' AS fact, v.dimension, v.key, false AS optional
    FROM analytics.vw_sales_detail f
    CROSS JOIN LATERAL (VALUES ('Customer',f.customer_key), ('Vehicle',f.vehicle_key),
        ('Dealership',f.dealership_key), ('Salesperson',f.salesperson_key),
        ('Date',f.sale_date_key::bigint)) v(dimension,key)
    UNION ALL
    SELECT 'Inventory',v.dimension,v.key,false
    FROM analytics.vw_inventory_detail f
    CROSS JOIN LATERAL (VALUES ('Vehicle',f.vehicle_key),('Dealership',f.dealership_key),
        ('Date',f.snapshot_date_key::bigint)) v(dimension,key)
    UNION ALL
    SELECT 'Service',v.dimension,v.key,v.dimension='Technician'
    FROM analytics.vw_service_appointment_detail f
    CROSS JOIN LATERAL (VALUES ('Customer',f.customer_key), ('Vehicle',f.vehicle_key),
        ('Dealership',f.dealership_key), ('Advisor',f.service_advisor_key),
        ('Technician',f.technician_key), ('Service',f.service_key::bigint),
        ('Date',f.appointment_date_key::bigint)) v(dimension,key)
), dimension_duplicates AS (
    SELECT dimension,key FROM dimension_keys GROUP BY dimension,key HAVING count(*)>1 OR key IS NULL
), fact_duplicates AS (
    SELECT fact,key FROM fact_keys GROUP BY fact,key HAVING count(*)>1 OR key IS NULL
), event_dates AS (
    SELECT full_date AS d FROM analytics.dim_date
    UNION ALL SELECT promised_at::date FROM analytics.fact_service
    UNION ALL SELECT customer_since_date FROM analytics.dim_customer
), bounds AS (
    SELECT date_trunc('year', min(d))::date AS first,
           (date_trunc('year',max(d))+interval '1 year - 1 day')::date AS last
    FROM event_dates
), checks AS (
    SELECT 'dimension_key_uniqueness' AS check_name,count(*)::bigint AS failed_count FROM dimension_duplicates
    UNION ALL SELECT 'fact_grain_uniqueness',count(*) FROM fact_duplicates
    UNION ALL SELECT 'required_foreign_keys_and_role_alignment',count(*)
    FROM foreign_keys f LEFT JOIN dimension_keys d ON d.dimension=f.dimension AND d.key=f.key
    WHERE (f.key IS NULL AND NOT f.optional) OR (f.key IS NOT NULL AND d.key IS NULL)
    UNION ALL SELECT 'inventory_composite_grain',count(*) FROM (
        SELECT vehicle_key,dealership_key,snapshot_date_key
        FROM analytics.vw_inventory_detail GROUP BY 1,2,3 HAVING count(*)>1) duplicates
    UNION ALL SELECT 'repair_order_unique_within_appointments',count(*) FROM (
        SELECT service_order_id FROM analytics.vw_service_appointment_detail
        WHERE service_order_id IS NOT NULL GROUP BY 1 HAVING count(*)>1) duplicates
    UNION ALL SELECT 'service_status_enrichment_preserves_grain',abs(
        (SELECT count(*) FROM analytics.vw_service_appointment_detail a
         LEFT JOIN analytics.fact_service ro ON ro.service_fact_key=a.service_fact_key)
        -(SELECT count(*) FROM analytics.vw_service_appointment_detail))
    UNION ALL SELECT 'appointments_not_lost',abs(
        (SELECT count(*) FROM staging.service_appointments)
        -(SELECT count(*) FROM analytics.vw_service_appointment_detail))
    UNION ALL SELECT 'sales_eligible_rows_preserved',abs(
        (SELECT count(*) FROM analytics.fact_sales WHERE sale_status IN ('Completed','Returned'))
        -(SELECT count(*) FROM analytics.vw_sales_detail))
    UNION ALL SELECT 'inventory_rows_preserved',abs(
        (SELECT count(*) FROM analytics.fact_inventory)
        -(SELECT count(*) FROM analytics.vw_inventory_detail))
    UNION ALL SELECT 'calendar_source_unique_contiguous',
        CASE WHEN count(*)>0 AND count(*)=count(DISTINCT full_date)
          AND count(*)=max(full_date)-min(full_date)+1 THEN 0 ELSE 1 END
        FROM analytics.dim_date
    UNION ALL SELECT 'full_year_calendar_bounds_cover_event_dates',count(*) FROM event_dates e
        CROSS JOIN bounds b WHERE e.d<b.first OR e.d>b.last
    UNION ALL SELECT 'calendar_bounds_available',CASE WHEN first IS NULL OR last IS NULL THEN 1 ELSE 0 END FROM bounds
    UNION ALL SELECT 'date_key_matches_date',count(*) FROM analytics.dim_date
        WHERE date_key<>to_char(full_date,'YYYYMMDD')::integer
    UNION ALL SELECT 'signed_return_values',count(*) FROM analytics.vw_sales_detail
        WHERE (sale_status='Returned' AND (units_sold<>-1 OR revenue>0 OR vehicle_cost>0))
           OR (sale_status='Completed' AND (units_sold<>1 OR revenue<0 OR vehicle_cost<0))
    UNION ALL SELECT 'service_costs_not_fabricated',count(*) FROM analytics.vw_service_appointment_detail
        WHERE NOT service_cost_available AND (service_cost IS NOT NULL OR service_profit IS NOT NULL)
    UNION ALL SELECT 'slow_moving_and_bucket_boundaries',count(*) FROM analytics.vw_inventory_detail
        WHERE is_slow_moving<>(days_in_inventory>90)
           OR aging_bucket_sort<>CASE WHEN days_in_inventory<=30 THEN 1
               WHEN days_in_inventory<=60 THEN 2 WHEN days_in_inventory<=90 THEN 3
               WHEN days_in_inventory<=120 THEN 4 ELSE 5 END
)
SELECT check_name,failed_count,CASE WHEN failed_count=0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks ORDER BY check_name;
