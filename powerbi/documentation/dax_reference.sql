/* Read-only unfiltered reference values for measures.dax.
   Compare after importing the complete model with no report filters.
   Ratios are fractions, not multiplied by 100. */
WITH sales AS (
    SELECT COALESCE(sum(revenue),0) revenue, COALESCE(sum(units_sold),0) units,
           COALESCE(sum(gross_profit),0) profit FROM analytics.vw_sales_detail
), stock AS (
    SELECT COALESCE(sum(inventory_units),0) units, COALESCE(sum(inventory_value),0) value,
           sum(days_in_inventory*inventory_units)::numeric weighted_days,
           count(DISTINCT vehicle_key) FILTER (WHERE days_in_inventory>90 AND inventory_units>0) slow
    FROM analytics.vw_inventory_detail
    WHERE snapshot_date_key=(SELECT max(snapshot_date_key) FROM analytics.vw_inventory_detail)
), service AS (
    SELECT COALESCE(sum(a.service_revenue) FILTER (WHERE ro.order_status='Completed'),0) revenue,
           count(DISTINCT a.service_order_id) FILTER (WHERE ro.order_status='Completed') orders,
           sum(a.completed_appointment_count)::numeric completed,
           sum(a.completion_eligible_count) eligible
    FROM analytics.vw_service_appointment_detail a
    LEFT JOIN analytics.fact_service ro ON ro.service_fact_key=a.service_fact_key
), interactions AS (
    SELECT c.customer_id,count(DISTINCT s.sale_id)::bigint quantity
    FROM analytics.vw_sales_detail s JOIN analytics.dim_customer c USING (customer_key)
    WHERE s.sale_status='Completed' GROUP BY c.customer_id
    UNION ALL
    SELECT c.customer_id,count(DISTINCT s.service_order_id)
    FROM analytics.vw_service_appointment_detail s
    JOIN analytics.fact_service ro ON ro.service_fact_key=s.service_fact_key
    JOIN analytics.dim_customer c ON c.customer_key=s.customer_key
    WHERE ro.order_status='Completed' GROUP BY c.customer_id
), customer_activity AS (
    SELECT customer_id,sum(quantity) quantity FROM interactions GROUP BY customer_id
), customers AS (
    SELECT count(*) FILTER (WHERE quantity>=1) qualifying,
           count(*) FILTER (WHERE quantity>=2) repeat FROM customer_activity
)
SELECT s.revenue AS "Revenue", s.units AS "Units Sold",
       s.revenue/NULLIF(s.units,0) AS "ASP", s.profit AS "Gross Profit",
       s.profit/NULLIF(s.revenue,0) AS "Gross Margin %",
       i.units AS "Inventory Units", i.value AS "Inventory Value",
       i.weighted_days/NULLIF(i.units,0) AS "Average Days in Inventory",
       i.slow AS "Slow-Moving Vehicles", v.revenue AS "Service Revenue",
       v.orders AS "Service Orders", v.revenue/NULLIF(v.orders,0) AS "Average Repair Order",
       v.completed/NULLIF(v.eligible,0) AS "Completion Rate",
       (SELECT count(DISTINCT customer_id) FROM analytics.dim_customer) AS "Customers",
       c.repeat AS "Repeat Customers", c.repeat::numeric/NULLIF(c.qualifying,0) AS "Repeat Rate",
       s.revenue+v.revenue AS "Customer Lifetime Value"
FROM sales s CROSS JOIN stock i CROSS JOIN service v CROSS JOIN customers c;
