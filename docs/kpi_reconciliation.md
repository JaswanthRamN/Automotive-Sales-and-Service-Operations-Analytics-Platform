# Power BI / PostgreSQL KPI reconciliation

Validation date: October 8, 2026. Scope: existing report pages and semantic
model only; no new dashboard pages, database loads or ETL changes.

## Result and evidence limits

**Offline checks PASS; live reconciliation is BLOCKED, not certified.**
The saved Power BI import snapshot reproduces every display-rounded PostgreSQL
baseline recorded on October 2 in
[dax_measures.md](../powerbi/documentation/dax_measures.md). These are independently
computed Pandas values, not results from an executing DAX engine. Historical
PostgreSQL agreement does not prove that today's database or Desktop model has
the same data. No numerical KPI discrepancy was established in the available
evidence; the model type discrepancy below was corrected.

Today's read-only PostgreSQL connection and reconciliation attempts failed with
connection timeouts at localhost:5432, for both IPv4 and IPv6. `docker compose ps`
also failed because the Docker Desktop Linux engine pipe was absent. No
PBIDesktop, msmdsrv or postgres process was found. Therefore current PostgreSQL
queries, live SQL quality gates, DAX compilation and actual filter-context
equality remain pending. No PostgreSQL/DAX PASS is inferred from offline tests.

## Major KPI results

Every row below has status **OFFLINE MATCH / LIVE PENDING**: snapshot calculation
matches the historical SQL baseline at its documented display precision. Full
precision is printed by the reconciliation runner; monetary totals are exact
decimal sums of the saved values. No currency is assumed.

| KPI | Saved import snapshot | Reconciliation contract |
|---|---:|---|
| Revenue | 660,770,485.26 | Sum signed sales revenue; Completed positive, Returned negative, Cancelled excluded |
| Units Sold | 15,500 | Sum signed transaction units, not distinct vehicles |
| ASP | 42,630.353887742 | Revenue / net units; blank at zero denominator |
| Gross Profit | 92,300,745.92 | Sum signed sales profit |
| Gross Margin % | 13.9686544691% | Total profit / total revenue, never mean row margins |
| Inventory Units | 4,500 | One latest global snapshot on/before as-of date |
| Inventory Value | 181,117,174.03 | Sum carrying value at that same snapshot |
| Average Days in Inventory | 118.6213333333 | Sum(age × units) / units at the snapshot |
| Slow-Moving Vehicles | 2,771 | Distinct vehicles with age >90 and units >0 at the snapshot |
| Service Revenue | 32,502,627.54 | Completed repair orders, by completion date |
| Service Orders | 15,500 | Distinct non-null Completed order IDs |
| Average Repair Order | 2,096.9437122581 | Completed service revenue / completed orders |
| Completion Rate | 93.8427075135% | Completed appointments / (Completed + Cancelled + No Show), by appointment date |
| Customers | 12,000 | Registered business customer IDs, distinct across dimension versions |
| Repeat Customers | 8,705 | Customers with at least two Completed sale/order interactions combined |
| Repeat Rate | 78.8853647485% | Repeat / qualifying active customers, not registered population |
| Customer Lifetime Value | 693,273,112.80 | Cumulative signed sales plus completed service revenue through as-of; total, not average |

The snapshot contains 15,500 eligible sales, 4,500 inventory rows and 17,000
appointments. Orders and appointments are different grains. Snapshot files are
ignored local data and are required for offline execution; they are not added
to Git by this task.

## Relationships, DAX and filter review

- All 20 model relationships passed one-to-many, single-direction, matching
  key type, unique/non-null dimension key and non-null FK membership checks
  against the snapshot. Nullable order/technician/date keys remain valid.
- Sales, inventory snapshot/vehicle/dealership and appointment grains passed
  duplicate/null checks. Non-null service order IDs are unique, so revenue is
  not multiplied by the appointment/order enrichment.
- All catalogue DAX expressions match their deployed model expressions.
  Existing report tests verify field bindings, date relationship activation
  and the four slicers' interactions across the three pages.
- Date uses sale date for sales, inactive completion date activated by
  `USERELATIONSHIP` for financial service measures, and appointment date for
  completion rate. Appointment-month SQL revenue is not a valid comparator for
  completion-month DAX revenue; the runner explicitly uses completion dates.
- Page inventory wrappers transfer the last selected DimDate date to
  DimSnapshotDate. Snapshot selection clears business filters to choose a common
  date, then retains dealership/vehicle/status filters for the values. An empty
  slice at an existing snapshot is zero; a date before any snapshot is blank.
  Inventory is never summed across snapshots. Day 90 is not slow-moving.
- Dealership, Brand and Vehicle Type filter facts through dimensions. They do
  **not** prune the customer dimension under single-direction relationships.
  Consequently the Customers card remains the registered population under those
  slicers, while Repeat Customers and Qualifying Customers respond to activity.
  This is the documented definition, not a reason to introduce bidirectional
  relationships. Use Qualifying Customers when comparing active customer counts.
- Repeat calculations combine per-business-customer distinct sales and orders,
  rather than joining two facts and multiplying activity. Repeat totals are
  non-additive across dealerships/brands. One sale plus one service qualifies.
- ASP, margin, ARO and repeat rate are ratios of totals with blank zero
  denominators. CLV removes only date history restrictions and preserves its
  upper bound and non-date filters. Returned sales reduce revenue but do not
  create a qualifying repeat interaction.

These structural reviews and SQL fixtures do not execute DAX or certify RLS.

## Discrepancy fixed

`metadata_from_snapshot` previously inspected only the first record. If that
record had null service dates/keys, rebuilding could type those columns as text.
Additionally the actual saved model typed all-null service_cost/service_profit
as text, despite their numeric PostgreSQL contract.

The generator now uses the first non-null value per column and supplies numeric
key, timestamp and service cost/profit fallbacks where all values are null.
The regenerated model retains numeric unavailable costs as null decimal values;
no service costs or profits were fabricated. A fixture with a null first record
tests date/key inference. All existing page definitions remain equivalent.

## Reproducible validation

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/reconcile_kpis.py
.\.venv\Scripts\python.exe scripts/reconcile_kpis.py --postgres
.\.venv\Scripts\python.exe -m pytest tests/test_kpi_reconciliation.py tests/test_executive_overview.py tests/test_dax_catalogue.py tests/test_sales_analytics_sql.py tests/test_inventory_analytics_sql.py tests/test_service_analytics_sql.py tests/test_customer_analytics_sql.py tests/test_power_bi_views_sql.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe scripts/validate_powerbi_report.py
```

`--postgres` reads configuration from .env using existing ETLConfig, opens a
read-only repeatable-read transaction, and compares an independent warehouse
projection against snapshot calculations. It uses five-second connection and
30-second statement timeouts. The 81 prepared scenarios cover overall totals,
all dealerships, brands, vehicle types, service completion months, empty filters
and a date before inventory. The live scenario comparisons did not run today
because connection establishment failed. Sales/service/inventory are aggregated
separately and customer interactions combined with UNION ALL; there is no
cross-fact revenue join. Parameters are bound and explicitly typed for nulls.

To finish the actual DAX comparison, start Docker/PostgreSQL and Power BI Desktop,
ensure the complete model is refreshed from the same stable ETL generation, and
run the unfiltered `powerbi/dax/measures.dax` query in DAX Query View. Export its
single ROW result as CSV with raw numbers and blank values for BLANK. Then run:

```powershell
.\.venv\Scripts\python.exe scripts/reconcile_kpis.py --postgres --dax-results path\to\dax-results.csv
```

Counts must agree exactly; currency totals within 0.01; ratios, ASP/ARO and age
within 1e-8. Export enough numeric precision; display-rounded percentages cannot
pass ratio comparison. Missing fields, mismatches and unavailable requested
engines cause a nonzero exit. The CSV option validates the unfiltered export
only: actual DAX month/dealer/brand/type checks must also be executed in Desktop
using those same contexts. Remove all report/query filters for the unfiltered
export, and verify both snapshots and PostgreSQL belong to that refresh.

## Tests executed today

- **60 tests passed** across KPI reconciliation, Power BI model/report, DAX
  catalogue and sales/inventory/service/customer/Power BI SQL tests.
- New controlled-fixture SQL comparisons passed eight filter scenarios, using
  SQLite with minimal PostgreSQL cast adaptation. They exercise the independent
  warehouse query versus Pandas, including returns, zero denominators, global
  snapshots, day 90/91, appointment/completion month differences, empty filters,
  combined customer interactions and CLV history. This is not PostgreSQL execution.
- **84 report files passed** validation against Microsoft report JSON schemas.
- Offline snapshot grain, FK, relationship types and DAX catalogue consistency
  checks passed. Live PostgreSQL attempt failed with the timeout recorded above.

Changed files: this document, scripts/reconcile_kpis.py,
tests/test_kpi_reconciliation.py, scripts/build_executive_overview.py and
powerbi/ExecutiveOverview/ExecutiveOverview.SemanticModel/model.bim.
No commit or push was requested for this task; no next-day work was started.

## Final-review addendum — October 9, 2026

The subsequent complete review found that customer SQL counted Returned rows
as qualifying sales interactions, whereas DAX counts only Completed purchases.
This could classify a sale followed by a return as repeat, or a returns-only
customer as a buyer. The customer SQL now counts only Completed sale events and
uses those events for first/last purchase dates while retaining signed returned
revenue and net units. Its independent validation reference was changed to the
same event contract. A controlled SQL fixture proves that a purchase plus return
has one purchase interaction and zero net revenue, and a returns-only customer
has zero qualifying purchases but negative revenue. No current PostgreSQL view
was changed because the live database is unavailable; apply the updated view
script/bootstrap and rerun all gates after startup.

The original business requirements contain aspirational history-based repeat
and repair-order completion definitions. Implemented Repeat Customers counts
>=2 qualifying events in the selected period; Completion Rate uses terminal
appointments. These documented implementation decisions require business
approval before production and are not presented as identical definitions.

Full tests and dependency checks were rerun; see [final review](final_review.md).
Docker config passed, but build/up/ps could not reach Docker's engine; PostgreSQL
timed out and the live API refused connection. Saved snapshot totals remain
unchanged. Actual DAX and live PostgreSQL equality are still pending; the final
local commit packages review fixes and documentation rather than certifying
end-to-end runtime or publishing to GitHub.
