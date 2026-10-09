# API reference

Start using Compose or `python -m uvicorn api.main:app --host 127.0.0.1 --port 8000`.
Base URL: http://localhost:8000. Interactive Swagger: /docs, ReDoc: /redoc,
OpenAPI: /openapi.json. The generated OpenAPI document is the authoritative
parameter/response schema. All application routes below are GET and read-only.

## Routes and filters

| Route | Response / grain | Supported filters beyond pagination |
|---|---|---|
| /health | Database readiness, SELECT 1 | None |
| /sales | Sale detail page | None |
| /inventory | Stock snapshot detail page | None |
| /service | Appointment detail page | None |
| /customers | Customer lifetime/segment page | None |
| /dealerships | Dealership scorecard page | None |
| /sales/summary | Scalar sales totals | date_from, date_to, dealership_id, brand, payment_type, sale_status |
| /sales/performance | Sale detail page | Same sales filters |
| /inventory/aging | Stock detail page | date_from, date_to, dealership_id, brand, aging_bucket, inventory_status |
| /inventory/slow-moving | Stock detail page, age >90 | Same inventory filters |
| /service/revenue | Scalar appointment/service totals | date_from, date_to, dealership_id, service_type, appointment_status |
| /service/performance | Appointment detail page | Same service filters |
| /customers/value | Customer detail page | state, relationship_segment, lifecycle_segment, activity_segment, minimum_value |
| /dealerships/performance | Dealership scorecard page | region, state, minimum_revenue |

Page routes use limit (default 100, 1–500) and offset (default 0, non-negative).
Summary/health routes are not paginated. Date bounds are inclusive ISO YYYY-MM-DD;
date_from must not exceed date_to. Dealership IDs/brand are exact values, not
substring searches. There is no blanket brand/date filter on customer/scorecard
routes and no vehicle-type parameter; consult the table instead of assuming
every route supports the same filters. Base resource routes only paginate.

## Responses and errors

Pages return `{items: [...], limit: 100, offset: 0, returned: n}`. `returned`
counts this page only, not total matches; empty pages have items=[]/returned=0.
Stable ORDER BY keys prevent overlapping pages when data is unchanged; concurrent
full ETL refreshes do not guarantee an offset-pagination snapshot.

Dates serialize as ISO strings. Pydantic Decimal values serialize as JSON
strings to retain decimal precision. Summary field names include revenue,
units_sold, gross_profit, gross_margin_percent, average_selling_price;
service fields include appointments, completed_appointments, repair_orders,
service_revenue, completion_rate_percent, average_repair_order.
Percent fields use 0–100 values, unlike DAX 0–1 ratios. Zero denominators return
null for ratio/average fields. Nullable service-order/technician values are valid.

200 means success, including an empty selection; 422 covers malformed dates,
reversed bounds, unsupported enums, negative thresholds/offsets and invalid
limits. An unknown valid brand/dealership produces an empty result, not 422.
Database failures return 503 with the sanitized detail
`The analytics database is temporarily unavailable.` SQL filters are bound
parameters; response contracts are in api/models.py.

## Domain values and metric contexts

Sales status: Completed/Returned; payment: Finance/Cash/Lease. Buckets:
0-30, 31-60, 61-90, 91-120, 120+ (>120). Stock statuses: Available, Reserved,
In Transit, Demonstrator, Sold Not Delivered, Unavailable. Service type:
Maintenance, Repair, Inspection, Recall, Tires; appointment status: Completed,
Cancelled, No Show, Scheduled. Customer segment enums are listed in the dictionary.

Sales summary excludes Cancelled and signs returns. Inventory endpoints expose
rows in the requested snapshot-date range: they do not automatically choose
one latest snapshot, so clients must not sum stock over time. Service API revenue
is the appointment-cohort view's revenue with order IDs counted at that grain;
it is not the Power BI completion-date/Completed-order financial measure.
Customer lifetime/segments are precomputed across lifetime activity and use
the SQL view's qualification rules; filter semantics are not interchangeable
with period-sensitive DAX. Dealership scorecards independently aggregate each
domain and use the latest global inventory snapshot.

## Example requests and tests

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod 'http://localhost:8000/sales/performance?brand=Toyota&limit=10&offset=0'
Invoke-RestMethod 'http://localhost:8000/inventory/slow-moving?aging_bucket=91-120&limit=10'
Invoke-RestMethod 'http://localhost:8000/service/revenue?date_from=2026-01-01&date_to=2026-08-31'
.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_api_database.py --cov=api --cov-report=term-missing --cov-fail-under=80
.\.venv\Scripts\python.exe scripts/verify_runtime.py
```

The test suite covers response schemas, validation, errors, empty selections,
pagination and parameter binding with controlled fake connections. The live
verifier separately checks populated PostgreSQL, routes, totals and OpenAPI.
No authentication/rate limiting is implemented; Compose loopback binding is
for local portfolio use. Public deployment requires access control and a
dedicated SQL read-only role before exposing customer details.
