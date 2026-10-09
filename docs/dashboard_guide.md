# Power BI dashboard guide

The checked-in report is powerbi/ExecutiveOverview/ExecutiveOverview.pbip, with
PBIR report definitions and an import-mode model.bim. It contains three visible
pages and one hidden vehicle/model drill-through page. This is a source project,
not a published Power BI Service dashboard or a visually accepted PBIX.

## Generate, open and refresh

After successful ETL and SQL gates, generate a fresh source snapshot/model:

```powershell
.\.venv\Scripts\python.exe scripts/check_sql.py
.\.venv\Scripts\python.exe scripts/build_executive_overview.py --rebuild
.\.venv\Scripts\python.exe scripts/validate_powerbi_report.py
```

Close Desktop before regenerating owned definitions. The generator overwrites
its report definitions and model; preserve manual report edits before rebuilding.
It imports a PostgreSQL snapshot into ignored local-data JSON and defaults the
model to UseLocalSnapshot=true. Its database connection comes from .env.

Open the PBIP in a current supported Power BI Desktop. For local snapshot refresh,
set SnapshotFolder to this clone's absolute powerbi/ExecutiveOverview/local-data
path; the generated path is machine-specific. For PostgreSQL refresh set
UseLocalSnapshot=false and configure Server/Database in Power Query (defaults
localhost:5432 / automotive_analytics); supply credentials via Desktop's data
source settings, not model source files. Clone-only workspaces have no snapshot
JSON and must first generate it or use PostgreSQL.

Refresh all tables from the same stable ETL generation. Do not import during a
full refresh or incrementally refresh only some tables, since surrogate keys
are restarted. Check privacy settings, connector availability and query folding
in Desktop. Registry/date roles are in [star_schema.md](../powerbi/documentation/star_schema.md).

## Pages and navigation

| Page | Contents | Reading guidance |
|---|---|---|
| Executive Overview | Revenue, units, gross profit/margin, service revenue, inventory value, monthly sales/service, brand/dealership sales, inventory aging | Inventory uses the last selected reporting date and displays the snapshot used |
| Sales & Inventory | Units, revenue, ASP, profit/margin, salesperson/brand/model performance, units/value/age/slow-moving stock, aging, vehicle/model matrix | Inventory is as-of stock; 90+ label means strictly >90, so day 90 is excluded |
| Service & Customer | Service revenue/orders/ARO/completion, technician/type performance, customers/repeat/rate/CLV, sales+service and service frequency | Financial service dates differ from appointment cohorts; Customers is registered population |
| Vehicle / Model Detail (hidden) | Vehicle/model/type context, sales and inventory detail, snapshot label | Right-click a source vehicle/model data point and choose drill-through; confirm propagated filters |

Visible pages have Date, Dealership, Brand and Vehicle Type slicers. Select
matching dimensions rather than fact columns. Power BI totals recompute measures
in the total context, not by adding displayed ratios, distinct customer counts
or stock across time. The drill-through fields are brand, model and vehicle_type;
vehicle ID appears in details and is not a separate bound drill-through parameter.

## KPI interpretation

Revenue/profit/units are net signed sales. Gross Margin %=total profit/revenue.
Stock value/units/weighted age share a global latest snapshot <= selected date.
Missing stock at that date is zero, not an older dealership snapshot. Slow-moving
counts distinct vehicles aged >90 with positive units; inventory includes all
statuses unless filtered. Buckets are non-overlapping, with 120 in 91–120.

Service Revenue/Orders/ARO require Completed repair orders and completion dates.
Completion Rate uses Completed/(Completed+Cancelled+No Show) by appointment date.
Technician-filtered completion is not the overall appointment cohort, since
appointments without orders have no technician. SQL/API appointment-month
revenue cannot be compared directly with DAX completion-month revenue.

Customers counts distinct registered business IDs; shared fact slicers do not
filter it through single-direction relationships. Repeat Customers requires
two qualifying Completed sales/orders within selection; Repeat Rate divides by
qualifying customers. CLV is cumulative historical revenue through as-of, not
average value or future predicted profit. Service Frequency is selected completed
orders per customer with service. See [DAX catalogue](../powerbi/documentation/dax_measures.md).

## Manual Power BI acceptance still required

1. Open and refresh the complete PBIP; confirm actual visual rendering, fonts,
   spacing, titles, chart units, labels, sorting, accessibility and readable
   percentage/money formats. JSON validation does not prove rendered usability.
2. Confirm relationship types/direction and active/inactive date roles, both
   marked calendars, hidden raw fields, explicit measures, chronological sort
   and disabled auto date/time. Avoid automatic bidirectional relationships.
3. Compile and run the unfiltered measures.dax query; export raw-precision CSV
   and compare with the same database/import generation using reconcile_kpis.py.
   Exercise all shared slicers and month-boundary appointment/completion dates.
4. Test returns, empty periods, zero denominators, no prior snapshot, day 90/91,
   one sale plus one service, non-additive repeat totals and CLV's removed lower
   date bound. Validate drill-through context and usable return navigation.
5. Review credential storage, permissions and RLS if publishing. Configure a
   gateway/scheduled refresh if a local PostgreSQL instance feeds Power BI
   Service. Publication, screenshots/PBIX export and tenant-specific security
   acceptance are manual and not claimed as complete.

[KPI reconciliation](kpi_reconciliation.md) records the live acceptance gap.
