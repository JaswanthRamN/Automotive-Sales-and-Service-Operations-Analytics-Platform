# Power Query import specification

These M templates define the import contract. The PBIP generator implements its
own equivalent source projections/types and connection parameters in model.bim.
The templates are not automatically executed, and live Desktop refresh/folding
remains an acceptance check; see ../../docs/dashboard_guide.md.

## Connection and load plan

Create Text parameters `pServer` = `localhost:5432`, `pDatabase` =
`automotive_analytics`. Store database credentials in Power BI Data Source
Settings, never M, Git or a report parameter. The Power BI Service requires an
appropriately configured gateway for this local database. Use a read-only
PostgreSQL account with SELECT on the named dimension/detail objects (and
fact_service for the status enrichment); do not grant write permissions.

Create one connection query `PostgresSource`, disable its load:

```powerquery
let
    Source = PostgreSQL.Database(pServer, pDatabase, [CreateNavigationProperties=false])
in
    Source
```

Create a function query `fxTable`, disable its load:

```powerquery
(objectName as text, columns as list) as table =>
let
    Source = PostgresSource{[Schema="analytics", Item=objectName]}[Data],
    Projected = Table.SelectColumns(Source, columns, MissingField.Error)
in
    Projected
```

Enable load only for the twelve model tables in star_schema.md: nine dimensions
(including SnapshotDate and the three employee roles) plus three facts.
An employee base query can be connection-only and referenced by each role.
Do not also load the base employee table or flattened business performance
views. Dimension projection lists follow the table registry; include both
surrogate and business IDs but never infer relationship keys from text labels.

Apply projection first, then types and role filters; verify folding with View
Native Query/query diagnostics where available. Native SQL can use
`Value.NativeQuery(PostgresSource, sql, null, [EnableFolding=true])`. Folding is
an implementation acceptance check, not assumed just because a template uses
EnableFolding. Avoid Table.Buffer, Python steps, merges of large facts or
row-by-row remote queries. Full refresh only: do not introduce RangeStart /
RangeEnd partitioning while identity keys are rebuilt by ETL.

## Transformations by table

| Query | Transformations |
|---|---|
| DimCustomer | Project customer_key/id/type/geography/registration/version fields; exclude first/last name/email/phone. Keys Int64, postal_code Text, dates Date, is_current Logical. Do not filter out older versions if they later exist. |
| DimVehicle | Project registry fields; rename make → Brand, body_type → Vehicle Type for display. Keys/model_year Int64, attributes Text. VIN omitted by default. Keep business IDs as Text. |
| DimDealership | Project registry fields; keys Int64; labels/geography/postal_code Text; opened_date Date. No relationship to employee roles. |
| EmployeeBase | Project key/id/first_name/last_name/role/status/hire/effective dates/is_current. Keys Int64; dates Date; add display name, remove name components; connection-only. |
| DimSalesperson / DimServiceAdvisor / DimTechnician | Reference EmployeeBase; filter role respectively to Sales Consultant / Service Advisor / Service Technician; do not filter Active employment_status (former employees may own facts). No new index/rekeying. |
| DimService | service_key Int64; service_type/category Text; is_active Logical; retain inactive types referenced by history. |
| FactSales | Project keys/IDs and numeric fields from vw_sales_detail; drop repeated dimension labels and date breakdowns; keys/units Int64, monetary values Currency.Type, attributes Text. Retain signed revenue/profit; no second sign operation. |
| FactInventory | Project keys, inventory_id, acquired_date, status, inventory_units/value, days_in_inventory, aging labels/sort/flag; add acquired_date_key; keys/age/sort/units Int64, money Currency.Type, dates Date, flag Logical. Preserve every snapshot. |
| FactService | Project appointment, dimension and order keys, flags/values from vw_service_appointment_detail; enrich order_status once as shown below. Keep nullable order/technician values. Add opened/promised/completed Date columns and YYYYMMDD keys; keys/flags/quantity Int64, timestamps DateTime, appointment_time Time, revenue/cost/profit Currency.Type, hours Decimal Number, boolean fields Logical. |
| DimDate / DimSnapshotDate | Use the full-year calendar below; mark date table; SnapshotDate references DimDate without joining it. Month labels/sorts and ISO-year consistency required. |

PostgreSQL NUMERIC amounts are two-decimal in these sources: Currency.Type
retains fixed precision suitable for money; derived rates/hours use Decimal
Number. Check actual ranges before refresh to prevent fixed-decimal overflow.
Never coerce missing service cost/profit to zero. Keep boolean true/false as
Logical. Preserve null vs blank vs zero. Do not silently remove duplicate rows
or replace failed numeric conversions: fail refresh and repair source data.
Whitespace/category cleanup already belongs to Python; do not normalize IDs in
Power Query independently of their foreign keys. Drop `loaded_at` and redundant
dimension strings from facts to reduce model size.

## Executable templates for future Desktop

FactSales query, with all relationship columns present:

```powerquery
let
    Source = fxTable("vw_sales_detail", {
        "sales_key", "sale_id", "sale_date_key", "customer_key", "vehicle_key",
        "dealership_key", "salesperson_key", "sales_channel", "payment_type",
        "sale_status", "units_sold", "list_price", "discount_amount", "revenue",
        "vehicle_cost", "gross_profit"}),
    Keys = Table.TransformColumnTypes(Source, {
        {"sales_key", Int64.Type}, {"sale_date_key", Int64.Type},
        {"customer_key", Int64.Type}, {"vehicle_key", Int64.Type},
        {"dealership_key", Int64.Type}, {"salesperson_key", Int64.Type},
        {"units_sold", Int64.Type}}),
    Amounts = Table.TransformColumnTypes(Keys, {
        {"list_price", Currency.Type}, {"discount_amount", Currency.Type},
        {"revenue", Currency.Type}, {"vehicle_cost", Currency.Type},
        {"gross_profit", Currency.Type}})
in
    Amounts
```

Service source template: `order_status` is not in the canonical appointment
view, so retrieve it with this unique-key, one-to-zero-or-one enrichment. Keep
the specified flags and values; project away repeated dimension labels before
loading. The join does not change appointment grain.

```powerquery
let
    Source = Value.NativeQuery(PostgresSource,
        "SELECT a.*, ro.order_status,
                a.opened_at::date AS opened_date,
                a.promised_at::date AS promised_date,
                a.completed_at::date AS completed_date,
                to_char(a.opened_at::date, 'YYYYMMDD')::integer AS opened_date_key,
                to_char(a.promised_at::date, 'YYYYMMDD')::integer AS promised_date_key,
                to_char(a.completed_at::date, 'YYYYMMDD')::integer AS completed_date_key
         FROM analytics.vw_service_appointment_detail a
         LEFT JOIN analytics.fact_service ro ON ro.service_fact_key=a.service_fact_key",
        null, [EnableFolding=true])
in
    Source
```

Inventory acquired_date_key can be added in the native projection using
`to_char(acquired_date, 'YYYYMMDD')::integer`, or a nullable-aware M function:

```powerquery
(value as nullable date) as nullable number =>
    if value = null then null
    else Date.Year(value) * 10000 + Date.Month(value) * 100 + Date.Day(value)
```

Name this function `fxDateKey`; use Table.AddColumn with Int64.Type. Dates stay
null when there is no repair order. Do not manufacture zero date keys or fake
technicians; unmatched optional values are expected. Validate required keys
with anti-joins against dimensions before enabling model relationships.

Calendar source: obtain bounds in PostgreSQL, then create a small contiguous
calendar locally. This query never depends on DimDate or fact queries in M,
so it does not create a circular query dependency. Month fields are generated
below; add quarter/day attributes as needed using the same full_date.

```powerquery
let
    Bounds = Value.NativeQuery(PostgresSource,
        "SELECT min(d) AS min_date, max(d) AS max_date FROM (
           SELECT full_date AS d FROM analytics.dim_date
           UNION ALL SELECT promised_at::date FROM analytics.fact_service
           UNION ALL SELECT customer_since_date FROM analytics.dim_customer
         ) dates", null, [EnableFolding=true]),
    First = Date.StartOfYear(Date.From(Bounds{0}[min_date])),
    Last = Date.EndOfYear(Date.From(Bounds{0}[max_date])),
    Days = List.Dates(First, Duration.Days(Last-First)+1, #duration(1,0,0,0)),
    Calendar = Table.FromList(Days, Splitter.SplitByNothing(), {"full_date"}),
    Typed = Table.TransformColumnTypes(Calendar, {{"full_date", type date}}),
    Key = Table.AddColumn(Typed, "date_key", each fxDateKey([full_date]), Int64.Type),
    Year = Table.AddColumn(Key, "calendar_year", each Date.Year([full_date]), Int64.Type),
    Month = Table.AddColumn(Year, "month_number", each Date.Month([full_date]), Int64.Type),
    Name = Table.AddColumn(Month, "month_name", each Date.MonthName([full_date], "en-US"), type text),
    YearMonth = Table.AddColumn(Name, "year_month", each Date.ToText([full_date], "yyyy-MM"), type text),
    Sort = Table.AddColumn(YearMonth, "year_month_sort", each [calendar_year]*100+[month_number], Int64.Type),
    Thursday = Table.AddColumn(Sort, "iso_thursday", each Date.AddDays([full_date], 3-Date.DayOfWeek([full_date], Day.Monday)), type date),
    ISOYear = Table.AddColumn(Thursday, "iso_year", each Date.Year([iso_thursday]), Int64.Type),
    ISOWeek = Table.AddColumn(ISOYear, "iso_week", each 1 + Number.IntegerDivide(Duration.Days([iso_thursday] - Date.StartOfWeek(#date([iso_year],1,4),Day.Monday)),7), Int64.Type),
    Result = Table.RemoveColumns(ISOWeek, {"iso_thursday"})
in
    Result
```

Bounds must not be empty/null; stop refresh if warehouse is unpopulated.
The calendar's local generation intentionally does not fold; bounds and fact
projections should fold. Reference this query as DimSnapshotDate and enable
its load independently. No customer effective_to sentinel of 9999-12-31 goes
into calendar bounds. Data type conversion must use explicit culture when
parsing text; these database queries deliver native date/numeric types.

## Refresh and model validation

Use one PostgreSQL source/privacy classification for related queries; do not
mix CSV data or API pages during refresh. Verify row counts before/after each
projection and employee role filter. Full-year calendar may exceed warehouse
dim_date count by design. Date roles use Int64 date_key except the inactive
registration relationship, which uses Date-to-Date. Verify uniqueness on every
one-side key, not on display names. Hide auto-summarization of keys and raw
percentages, sort categorical labels, and create only the explicit registry.
Power Query error rows and missing required columns are refresh failures,
not data to discard. Gates precede model refresh; customer PII minimization
precedes load, not merely hiding columns in Model view.
