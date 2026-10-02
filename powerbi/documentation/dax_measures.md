# DAX measure catalogue

Source: [measures.dax](../dax/measures.dax). All 17 requested business measures
and three reusable helpers are defined with a named home table. This is a DAX
query: `DEFINE MEASURE` creates query-scoped definitions and the final `EVALUATE
ROW` returns all KPIs. In Desktop DAX Query View, load the model first, run the
query, and use the measure deployment features or copy each right-hand expression
into a permanent measure. Running the query alone does not persist measures.
Do not paste the entire file into a single New Measure formula.

## Model requirements

Use [the relationship registry](star_schema.md) and [Power Query projection](power_query.md).
In particular FactService must include order_status (the one-to-one enrichment),
completed_date_key and service_order_id. DimDate has the active appointment
relationship and inactive completion relationship; SnapshotDate is independent.
FactSales values are already signed and Cancelled is excluded by the source.
Facts are at sale, snapshot-vehicle-dealership, and appointment grain. Hide raw
numeric fields; use explicit measures and dimension attributes for slicers.
No pages, PBIX, database objects or ETL are created by this phase.
Revenue is hosted on DimCustomer to avoid a case-insensitive name collision
with FactSales[revenue]. The home table does not determine filter context;
group Revenue in a Sales display folder.

## Every measure: definition, filter behavior and formatting

| Measure (home table) | Definition and interpretation | Dates / filters | Format and no-data behavior |
|---|---|---|---|
| Revenue (DimCustomer) | Sum signed net vehicle revenue. Taxes/fees are not available and not added. Returned revenue reverses Completed revenue exactly once. | Sale date; retains all sales/dimension filters. | `#,0.00;(#,0.00)`; 0 when no rows. No currency symbol is assumed. |
| Units Sold (FactSales) | Sum signed units: Completed +1, Returned -1. Never distinct VIN count. | Sale date and current sales filters. | `#,0;(#,0)`; 0 when empty; may be negative. |
| ASP (FactSales) | Revenue / Units Sold, ratio of totals. | Same context as both sales measures. | `#,0.00;(#,0.00)`; blank when net units=0. Net-return-heavy periods can produce unusual/negative values. |
| Gross Profit (FactSales) | Sum signed gross_profit, already revenue minus signed vehicle cost. | Sale date; sales filters retained. | `#,0.00;(#,0.00)`; 0 when empty; negative profit permitted. |
| Gross Margin % (FactSales) | Gross Profit / Revenue, not average transaction margins. | Same sales context. | `0.00%`; blank if revenue=0. DAX returns a fraction, not fraction*100. |
| Inventory Units (FactInventory) | Sum inventory_units at one chosen snapshot. | Latest authorized global snapshot <= last visible SnapshotDate; retains vehicle/dealership/status filters for values. | `#,0`; blank if no snapshot exists before as-of, otherwise 0 for no matching rows. |
| Inventory Value (FactInventory) | Sum inventory_value at the same snapshot as Inventory Units. | Same snapshot and detail filters; never sum stock over a range. | `#,0.00`; no-snapshot blank, empty-at-existing-snapshot 0. |
| Average Days in Inventory (FactInventory) | Sum(age * units) / Inventory Units at the chosen snapshot. | Same snapshot/filters; unit-weighted, not average of dealership averages. | `0.0`; blank without a snapshot or units. |
| Slow-Moving Vehicles (FactInventory) | Distinct non-null vehicle_key at that snapshot, age >90, units >0. Day 90 excluded, 91 included. | Threshold intersects existing age/status/vehicle/dealership filters via KEEPFILTERS. | `#,0`; blank if no snapshot; otherwise 0 if none slow. Distinct vehicles are non-additive across dealerships. |
| Service Revenue (FactService) | Sum service_revenue only for Completed repair orders. Includes Customer Pay/Warranty/Internal unless payer_type is filtered. | Completion date via USERELATIONSHIP, not appointment date. Retains all non-date service filters. | `#,0.00`; 0 if empty. |
| Service Orders (FactService) | Distinct nonblank service_order_id, Completed only. Non-order appointments never count as an order. | Same completion date/status/payer/dimension filters as Service Revenue. | `#,0`; 0 if empty. |
| Average Repair Order (FactService) | Service Revenue / Service Orders, consistently scoped. | Completion date. | `#,0.00`; blank if zero orders. |
| Completion Rate (FactService) | Completed appointment flags / eligible appointment flags. Eligible = Completed + Cancelled + No Show; Scheduled excluded. | Active appointment date and appointment filters. Technician filters only match appointments with a technician/order, so avoid using this as an all-appointment rate in technician context. | `0.00%`; blank if no eligible appointments. |
| Customers (DimCustomer) | Distinct nonblank business customer_id across visible dimension rows; counts a business customer once even if versions exist. | Customer dimension filters apply. Single-direction facts cannot filter DimCustomer; Date/Dealer/Vehicle do not turn this into active customers. | `#,0`; registered customer population; use Qualifying Customers for transactional contexts. |
| Repeat Customers (DimCustomer) | Visible business customers with >=2 qualifying interactions in the selected period, combined across both facts. | Completed sales by sale date + completed service orders by completion date. One sale plus one service counts as repeat. Retains applicable dimension/fact filters. | `#,0`; 0 if none. Distinct people, non-additive across groups. |
| Repeat Rate (DimCustomer) | Repeat Customers / Qualifying Customers, not all registered Customers. | Same period and activity filters in numerator/denominator. | `0.00%`; blank with no qualifying customers. |
| Customer Lifetime Value (DimCustomer) | Interim **revenue-based historical CLV**: cumulative signed vehicle revenue + completed service revenue through as-of. No cost/profit estimate is used. | Last visible DimDate date; clears the whole date table's lower/month/year filters and reapplies <=as-of. Customer/Dealer/Vehicle/payer and other non-date filters remain. | `#,0.00;(#,0.00)`; at customer row that customer's value; total is combined value for visible customers, not average CLV. No date selection uses calendar end, including all observed history. Empty activity gives 0; empty date context blank. |

## Helpers (hide from casual report authors)

| Helper | Definition / role | Format / edge cases |
|---|---|---|
| Inventory Snapshot Key (FactInventory) | MAX snapshot_date_key <= last visible SnapshotDate. Clears report filters to pick one common snapshot across dealerships/vehicles; RLS still restricts authorized data. | Whole number YYYYMMDD, hidden; blank before earliest snapshot or empty date context. |
| Qualifying Interactions (DimCustomer) | Distinct Completed sale_id + Service Orders. Completed-status predicates intersect status filters. Returns do not qualify as a new interaction, but still reverse revenue in Revenue/CLV. | Whole number; 0 when no activity. Used inside per-customer context transition. |
| Qualifying Customers (DimCustomer) | Iterate unique DimCustomer.customer_id and count IDs whose context-transformed Qualifying Interactions >=1. | Whole number; 0 when empty. Explicit denominator for Repeat Rate. |

## Deliberate filter rules and limitations

Inventory uses **as-of** behavior: a selected month/range or date axis takes its
last date and uses the latest available snapshot on/before it. An exact date
without a snapshot therefore uses an earlier snapshot, not an invented stock
row. With no SnapshotDate filter, use the latest snapshot. All dealerships use
that same chosen snapshot; missing stock for a dealership at that date is zero,
not its older local snapshot. Do not sum inventory measure values down a time
axis; the total recomputes stock at the last as-of date. DimDate does not affect
inventory. A Slow-Moving Vehicles total can be less than the sum of dealer rows
if the source repeats the same vehicle across locations.

Service financial measures intentionally differ from existing appointment-month
SQL aggregates: SQL validation must group orders by completion date. Completed
orders only is an explicit financial qualification rule, intersected with user
status selections; selecting Reopened returns zero instead of silently resetting
the slicer. Completion Rate is an appointment outcome rate, so a Completed-only
appointment-status selection produces 100%, not an unfiltered overall rate.
Remove/avoid that filter in an overall rate visual rather than changing its
denominator behind the user. No BLANK order ID is counted.

Period Repeat Customers is not the static lifetime repeat segment from
vw_customer_value; that SQL view currently counts Returned sales as interactions.
The approved model design's qualifying Completed-only, period-based rule is
implemented here. Registration-cohort New Customers is outside today's list.
Cross-fact filters are inherently asymmetric: a salesperson filters sales, an
advisor/technician/service type filters service, and a shared customer/vehicle/
dealership filters both facts. A salesperson selection does not silently exclude
service activity. Use clear context labels; never add bidirectional relationships
to force unrelated filters to propagate. CLV retains these same scope rules.

CLV clears DimDate only. Do not use direct fact date-key slicers or active
customer registration-date filters when requesting unrestricted lifetime value.
Use DimDate for dates and customer_id for customer scope. Values are nominal,
single-source currency amounts: no currency conversion/discount rate or profit
CLV exists. Service costs remain unavailable. Full-refresh current-state
dimensions mean historical attribution is limited as documented in the model.

## Testing and deployment checklist

Run the PostgreSQL reference query in this folder to obtain unfiltered expected
values, then run measures.dax in the loaded Power BI model and compare all 17
fields (money to cents, ratios to an agreed tolerance). This query includes the
same one-to-one order status enrichment as Power Query. PostgreSQL source gates
must also PASS. Catalogue tests check coverage, references, dependency ordering
and structural balance; they are not a DAX compiler or execution engine.

In Desktop additionally check: empty period; zero revenue/net units; returns;
one/multiple snapshots; a date before earliest snapshot; day 90/91; Completed vs
Scheduled outcomes; empty/Completed/Reopened order selections; one sale + one
service for the same customer; repeat totals across dealers; month boundaries
where appointment/completion differ; CLV lower date bound removed while upper
bound retained; a customer with only returned activity; Customer/Dealer/Vehicle
and employee role filters. Confirm RLS in a future security-enabled model because
inactive relationship behavior cannot be certified from SQL alone.

## Validation record — October 2, 2026

Repository suite: **125 passed, one skipped** (host Airflow installation absent).
All four catalogue/edge-contract tests passed. The read-only PostgreSQL reference
query executed successfully and returned these 17 unfiltered baselines:

| Measure | PostgreSQL baseline (display-rounded) |
|---|---|
| Revenue | 660,770,485.26 |
| Units Sold | 15,500 |
| ASP | 42,630.35 |
| Gross Profit | 92,300,745.92 |
| Gross Margin % | 13.97% |
| Inventory Units | 4,500 |
| Inventory Value | 181,117,174.03 |
| Average Days in Inventory | 118.6 |
| Slow-Moving Vehicles | 2,771 |
| Service Revenue | 32,502,627.54 |
| Service Orders | 15,500 |
| Average Repair Order | 2,096.94 |
| Completion Rate | 93.84% |
| Customers | 12,000 |
| Repeat Customers | 8,705 |
| Repeat Rate | 78.89% |
| Customer Lifetime Value | 693,273,112.80 |

These are PostgreSQL results, **not executed DAX results**. No loaded Power BI
semantic model exists in the repository, so DAX compilation, filter-context
execution and equality against these baselines remain pending in Desktop.
The fixture validates the SQL contract for returns/zero denominators, latest
snapshot, day 90/91, completed/non-completed/null orders, combined customer
activity and empty activity. It does not emulate DAX. When executing this SQL
through SQLAlchemy, use `connection.execute(text(sql))`; driver-level SQL with
parameter handling can interpret the literal `%` in the output alias as a
placeholder. In psql the file runs directly without that adaptation.

Reference semantics: [DIVIDE](https://learn.microsoft.com/en-us/dax/divide-function-dax),
[USERELATIONSHIP](https://learn.microsoft.com/en-us/dax/userelationship-function-dax),
[KEEPFILTERS](https://learn.microsoft.com/en-us/dax/keepfilters-function-dax),
[CALCULATE](https://learn.microsoft.com/en-us/dax/calculate-function-dax), and
[REMOVEFILTERS](https://learn.microsoft.com/en-us/dax/removefilters-function-dax).
