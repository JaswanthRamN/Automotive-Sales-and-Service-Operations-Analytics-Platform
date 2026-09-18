# Power BI PostgreSQL Views

These views provide stable, business-friendly datasets for Power BI. Execute the domain analytics scripts first, followed by `sql/analytics/power_bi_views.sql`.

| View | Grain | Purpose |
|---|---|---|
| `analytics.vw_sales_performance` | One eligible sale | Sales trends, units, revenue, profit, margin, vehicle, salesperson, dealership, channel, and payment analysis |
| `analytics.vw_inventory_aging` | One vehicle per dealership and snapshot | Inventory units/value, age, ordered aging bucket, and slow-moving analysis |
| `analytics.vw_service_performance` | One appointment | Appointment outcomes, completion, repair orders, technicians, service revenue, and turnaround analysis |
| `analytics.vw_customer_value` | One current customer | Revenue-based CLV, sales/service activity, lifecycle, relationship, inactivity, and service-frequency segments |
| `analytics.vw_dealership_performance` | One current dealership | Combined sales, latest-snapshot inventory, service, and unique-customer scorecard |

## Modeling guidance

- Use `vw_sales_performance`, `vw_inventory_aging`, and `vw_service_performance` as fact-like tables.
- Use `vw_customer_value` and `vw_dealership_performance` as customer and dealership scorecards.
- Inventory visuals must filter or group by `snapshot_date`; never sum stock across snapshots.
- Sort `aging_bucket` by `aging_bucket_sort`.
- Service cost and profit remain null until authoritative cost data exists.
- Customer email and phone are intentionally excluded from the Power BI customer view.
- Run `sql/analytics/power_bi_views_validation.sql`; every result must be `PASS` before refresh or publication.
