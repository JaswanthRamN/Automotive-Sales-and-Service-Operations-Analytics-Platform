# Data dictionary

Generated from sql/002_create_staging_tables.sql, sql/003_create_dimensions.sql
and sql/004_create_facts.sql. Regenerate with `python scripts/build_data_dictionary.py`.

Raw/processed CSVs contain the source fields of their eight staging tables;
loaded_at is supplied by PostgreSQL and is not a CSV input.
Staging stores every field as TEXT; cleaned CSV date/number contracts are
enforced by Pandas preflight before PostgreSQL casting. Raw data is synthetic.
Nullability below describes physical SQL columns, not every reporting view.

Warehouse dimensions/facts live in analytics, not a separate warehouse schema.
Business dates are local dates; no dealership timezone or universal currency
is defined. Monetary amounts use numeric decimal types. Refer to DDL for
full CHECK, FK, UNIQUE and generated-column expressions and migration 006
for hardened return-unit validation.

## Physical tables and all columns

### staging.customers

Grain: One source customer / customer_id.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| customer_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| first_name | TEXT | Yes | Person given name; customer names excluded from Power BI; validated/cast from cleaned CSV |
| last_name | TEXT | Yes | Person family name; customer names excluded from Power BI; validated/cast from cleaned CSV |
| email | TEXT | Yes | Customer contact email; excluded from Power BI; validated/cast from cleaned CSV |
| phone | TEXT | Yes | Customer contact phone; excluded from Power BI; validated/cast from cleaned CSV |
| city | TEXT | Yes | City; validated/cast from cleaned CSV |
| state | TEXT | Yes | State; validated/cast from cleaned CSV |
| postal_code | TEXT | Yes | Postal code; validated/cast from cleaned CSV |
| customer_since_date | TEXT | Yes | Customer registration date, not first qualifying interaction date; validated/cast from cleaned CSV |
| customer_type | TEXT | Yes | Individual, Business or Fleet; validated/cast from cleaned CSV |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### staging.vehicles

Grain: One physical vehicle / vehicle_id; VIN unique.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| vehicle_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| vin | TEXT | Yes | 17-character vehicle identification number; restricted detail attribute; validated/cast from cleaned CSV |
| make | TEXT | Yes | Vehicle manufacturer, exposed as brand in reporting; validated/cast from cleaned CSV |
| model | TEXT | Yes | Model; validated/cast from cleaned CSV |
| model_year | TEXT | Yes | Model year; validated/cast from cleaned CSV |
| body_type | TEXT | Yes | Vehicle category, exposed as vehicle_type in Power BI; validated/cast from cleaned CSV |
| fuel_type | TEXT | Yes | Fuel type; validated/cast from cleaned CSV |
| color | TEXT | Yes | Color; validated/cast from cleaned CSV |
| vehicle_condition | TEXT | Yes | New or Used; validated/cast from cleaned CSV |
| mileage_at_acquisition | TEXT | Yes | Non-negative odometer value at acquisition; source has no explicit unit metadata; validated/cast from cleaned CSV |
| manufacturer_msrp | TEXT | Yes | Manufacturer reference list amount, non-negative; validated/cast from cleaned CSV |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### staging.dealerships

Grain: One dealership / dealership_id.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| dealership_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| dealership_name | TEXT | Yes | Dealership name; validated/cast from cleaned CSV |
| city | TEXT | Yes | City; validated/cast from cleaned CSV |
| state | TEXT | Yes | State; validated/cast from cleaned CSV |
| postal_code | TEXT | Yes | Postal code; validated/cast from cleaned CSV |
| region | TEXT | Yes | Region; validated/cast from cleaned CSV |
| opened_date | TEXT | Yes | ISO calendar date; business event or calendar attribute; validated/cast from cleaned CSV |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### staging.employees

Grain: One employee / employee_id.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| employee_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| dealership_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| first_name | TEXT | Yes | Person given name; customer names excluded from Power BI; validated/cast from cleaned CSV |
| last_name | TEXT | Yes | Person family name; customer names excluded from Power BI; validated/cast from cleaned CSV |
| role | TEXT | Yes | Sales Consultant, Service Advisor, Service Technician, Inventory Specialist or Manager; validated/cast from cleaned CSV |
| hire_date | TEXT | Yes | ISO calendar date; business event or calendar attribute; validated/cast from cleaned CSV |
| employment_status | TEXT | Yes | Active or Inactive; validated/cast from cleaned CSV |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### staging.sales

Grain: One transaction / sale_id.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| sale_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| sale_date | TEXT | Yes | ISO calendar date; business event or calendar attribute; validated/cast from cleaned CSV |
| customer_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| vehicle_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| dealership_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| salesperson_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| sales_channel | TEXT | Yes | Sales channel; validated/cast from cleaned CSV |
| list_price | TEXT | Yes | Sale list amount before discount; validated/cast from cleaned CSV |
| discount_amount | TEXT | Yes | Non-negative discount applied to sale or service revenue; validated/cast from cleaned CSV |
| sale_price | TEXT | Yes | Unsigned sale amount after discount; multiply by unit_quantity once for reporting; validated/cast from cleaned CSV |
| vehicle_cost | TEXT | Yes | Unsigned sale vehicle cost; sign once for reporting; validated/cast from cleaned CSV |
| gross_profit | TEXT | Yes | Stored sale_price minus vehicle_cost; return sign applied once in canonical view; losses allowed; validated/cast from cleaned CSV |
| payment_type | TEXT | Yes | Finance, Cash or Lease; validated/cast from cleaned CSV |
| sale_status | TEXT | Yes | Completed, Returned or Cancelled; validated/cast from cleaned CSV |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### staging.inventory

Grain: One inventory record / inventory_id and snapshot_date.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| inventory_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| snapshot_date | TEXT | Yes | ISO calendar date; business event or calendar attribute; validated/cast from cleaned CSV |
| vehicle_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| dealership_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| acquired_date | TEXT | Yes | ISO calendar date; business event or calendar attribute; validated/cast from cleaned CSV |
| inventory_status | TEXT | Yes | Available, Reserved, In Transit, Demonstrator, Sold Not Delivered or Unavailable; validated/cast from cleaned CSV |
| carrying_cost | TEXT | Yes | Vehicle carrying value at inventory snapshot, exposed as inventory_value; validated/cast from cleaned CSV |
| days_in_inventory | TEXT | Yes | Snapshot date minus acquired_date in calendar days; validated/cast from cleaned CSV |
| slow_moving_flag | TEXT | Yes | Derived source/warehouse flag: days_in_inventory >90; validated/cast from cleaned CSV |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### staging.service_appointments

Grain: One appointment / appointment_id.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| appointment_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| customer_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| vehicle_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| dealership_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| service_advisor_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| appointment_date | TEXT | Yes | ISO calendar date; business event or calendar attribute; validated/cast from cleaned CSV |
| appointment_time | TEXT | Yes | Appointment time; validated/cast from cleaned CSV |
| service_type | TEXT | Yes | Service type; validated/cast from cleaned CSV |
| appointment_status | TEXT | Yes | Completed, Cancelled, No Show or Scheduled; validated/cast from cleaned CSV |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### staging.service_orders

Grain: One repair order / service_order_id; appointment_id unique.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| service_order_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| appointment_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| customer_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| vehicle_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| dealership_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| service_advisor_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| technician_id | TEXT | Yes | Source business identifier; retain as text; validated/cast from cleaned CSV |
| opened_at | TEXT | Yes | Naive local business timestamp; no dealership timezone metadata; validated/cast from cleaned CSV |
| promised_at | TEXT | Yes | Naive local business timestamp; no dealership timezone metadata; validated/cast from cleaned CSV |
| completed_at | TEXT | Yes | Naive local business timestamp; no dealership timezone metadata; validated/cast from cleaned CSV |
| order_status | TEXT | Yes | Repair-order status; not interchangeable with appointment status; validated/cast from cleaned CSV |
| payer_type | TEXT | Yes | Service payer category (Customer Pay, Warranty, Internal); validated/cast from cleaned CSV |
| labor_revenue | TEXT | Yes | Repair-order labor component before combined discount; validated/cast from cleaned CSV |
| parts_revenue | TEXT | Yes | Repair-order parts component before combined discount; validated/cast from cleaned CSV |
| discount_amount | TEXT | Yes | Non-negative discount applied to sale or service revenue; validated/cast from cleaned CSV |
| service_revenue | TEXT | Yes | Labor plus parts minus discount; financial DAX qualifies Completed orders; validated/cast from cleaned CSV |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### analytics.dim_date

Grain: One day / date_key; full_date unique.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| date_key | INTEGER | No | YYYYMMDD integer business calendar key |
| full_date | DATE | No | ISO calendar date; business event or calendar attribute |
| day_of_week | SMALLINT | No | ISO weekday 1–7 |
| day_name | VARCHAR(9) | No | Day name |
| day_of_month | SMALLINT | No | Day of month |
| day_of_year | SMALLINT | No | Day of year |
| week_of_year | SMALLINT | No | ISO week number; pair with ISO year, not always calendar_year |
| month_number | SMALLINT | No | Month number |
| month_name | VARCHAR(9) | No | Month name |
| quarter_number | SMALLINT | No | Quarter number |
| calendar_year | SMALLINT | No | Calendar year |
| is_weekend | BOOLEAN | No | Is weekend |

### analytics.dim_dealership

Grain: One dealership / dealership_key.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| dealership_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| dealership_id | VARCHAR(20) | No | Source business identifier; retain as text |
| dealership_name | VARCHAR(150) | No | Dealership name |
| city | VARCHAR(100) | No | City |
| state | VARCHAR(50) | No | State |
| postal_code | VARCHAR(20) | No | Postal code |
| region | VARCHAR(50) | No | Region |
| opened_date | DATE | No | ISO calendar date; business event or calendar attribute |
| effective_from | DATE | No | Version start; full-refresh model does not preserve prior versions |
| effective_to | DATE | No | Version end; 9999-12-31 default |
| is_current | BOOLEAN | No | Current-version marker; customer/employee uniqueness uses partial indexes |

### analytics.dim_customer

Grain: One business customer version / customer_key.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| customer_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| customer_id | VARCHAR(20) | No | Source business identifier; retain as text |
| first_name | VARCHAR(100) | No | Person given name; customer names excluded from Power BI |
| last_name | VARCHAR(100) | No | Person family name; customer names excluded from Power BI |
| email | VARCHAR(320) | Yes | Customer contact email; excluded from Power BI |
| phone | VARCHAR(30) | Yes | Customer contact phone; excluded from Power BI |
| city | VARCHAR(100) | Yes | City |
| state | VARCHAR(50) | Yes | State |
| postal_code | VARCHAR(20) | Yes | Postal code |
| customer_since_date | DATE | No | Customer registration date, not first qualifying interaction date |
| customer_type | VARCHAR(20) | No | Individual, Business or Fleet |
| effective_from | DATE | No | Version start; full-refresh model does not preserve prior versions |
| effective_to | DATE | No | Version end; 9999-12-31 default |
| is_current | BOOLEAN | No | Current-version marker; customer/employee uniqueness uses partial indexes |

### analytics.dim_vehicle

Grain: One vehicle / vehicle_key; vehicle_id and VIN unique.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| vehicle_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| vehicle_id | VARCHAR(20) | No | Source business identifier; retain as text |
| vin | CHAR(17) | No | 17-character vehicle identification number; restricted detail attribute |
| make | VARCHAR(60) | No | Vehicle manufacturer, exposed as brand in reporting |
| model | VARCHAR(60) | No | Model |
| model_year | SMALLINT | No | Model year |
| body_type | VARCHAR(30) | No | Vehicle category, exposed as vehicle_type in Power BI |
| fuel_type | VARCHAR(30) | No | Fuel type |
| color | VARCHAR(30) | Yes | Color |
| vehicle_condition | VARCHAR(10) | No | New or Used |
| mileage_at_acquisition | INTEGER | No | Non-negative odometer value at acquisition; source has no explicit unit metadata |
| manufacturer_msrp | NUMERIC(14, 2) | No | Manufacturer reference list amount, non-negative |

### analytics.dim_employee

Grain: One employee version / employee_key.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| employee_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| employee_id | VARCHAR(20) | No | Source business identifier; retain as text |
| dealership_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| first_name | VARCHAR(100) | No | Person given name; customer names excluded from Power BI |
| last_name | VARCHAR(100) | No | Person family name; customer names excluded from Power BI |
| role | VARCHAR(40) | No | Sales Consultant, Service Advisor, Service Technician, Inventory Specialist or Manager |
| hire_date | DATE | No | ISO calendar date; business event or calendar attribute |
| employment_status | VARCHAR(10) | No | Active or Inactive |
| effective_from | DATE | No | Version start; full-refresh model does not preserve prior versions |
| effective_to | DATE | No | Version end; 9999-12-31 default |
| is_current | BOOLEAN | No | Current-version marker; customer/employee uniqueness uses partial indexes |

### analytics.dim_service

Grain: One service type / service_key.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| service_key | SMALLINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| service_type | VARCHAR(50) | No | Service type |
| service_category | VARCHAR(50) | No | Service category |
| is_active | BOOLEAN | No | Is active |

### analytics.fact_sales

Grain: One transaction / sales_key; sale_id unique.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| sales_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| sale_id | VARCHAR(20) | No | Source business identifier; retain as text |
| sale_date_key | INTEGER | No | YYYYMMDD integer business calendar key |
| customer_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| vehicle_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| dealership_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| salesperson_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| sales_channel | VARCHAR(20) | No | Sales channel |
| list_price | NUMERIC(14, 2) | No | Sale list amount before discount |
| discount_amount | NUMERIC(14, 2) | No | Non-negative discount applied to sale or service revenue |
| sale_price | NUMERIC(14, 2) | No | Unsigned sale amount after discount; multiply by unit_quantity once for reporting |
| vehicle_cost | NUMERIC(14, 2) | No | Unsigned sale vehicle cost; sign once for reporting |
| gross_profit | NUMERIC(14, 2) | No | Stored sale_price minus vehicle_cost; return sign applied once in canonical view; losses allowed |
| unit_quantity | SMALLINT | No | Signed sale units: Completed +1, Returned -1; Cancelled excluded from reporting |
| payment_type | VARCHAR(20) | No | Finance, Cash or Lease |
| sale_status | VARCHAR(20) | No | Completed, Returned or Cancelled |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### analytics.fact_inventory

Grain: One vehicle/dealership/snapshot / inventory_key.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| inventory_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| inventory_id | VARCHAR(20) | No | Source business identifier; retain as text |
| snapshot_date_key | INTEGER | No | YYYYMMDD integer business calendar key |
| vehicle_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| dealership_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| acquired_date | DATE | No | ISO calendar date; business event or calendar attribute |
| inventory_status | VARCHAR(30) | No | Available, Reserved, In Transit, Demonstrator, Sold Not Delivered or Unavailable |
| carrying_cost | NUMERIC(14, 2) | No | Vehicle carrying value at inventory snapshot, exposed as inventory_value |
| days_in_inventory | INTEGER | No | Snapshot date minus acquired_date in calendar days |
| slow_moving_flag | BOOLEAN | No | Derived source/warehouse flag: days_in_inventory >90 |
| on_hand_quantity | SMALLINT | No | Snapshot stock units, currently constrained to one |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

### analytics.fact_service

Grain: One repair order / service_fact_key; order/appointment IDs unique.

| Column | SQL type | Nullable? | Meaning |
|---|---|---|---|
| service_fact_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| service_order_id | VARCHAR(20) | No | Source business identifier; retain as text |
| appointment_id | VARCHAR(20) | No | Source business identifier; retain as text |
| completed_date_key | INTEGER | No | YYYYMMDD integer business calendar key |
| customer_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| vehicle_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| dealership_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| service_advisor_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| technician_key | BIGINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| service_key | SMALLINT | No | Surrogate primary key or dimension foreign key; see DDL constraints |
| opened_at | TIMESTAMP | No | Naive local business timestamp; no dealership timezone metadata |
| promised_at | TIMESTAMP | No | Naive local business timestamp; no dealership timezone metadata |
| completed_at | TIMESTAMP | No | Naive local business timestamp; no dealership timezone metadata |
| order_status | VARCHAR(20) | No | Repair-order status; not interchangeable with appointment status |
| payer_type | VARCHAR(20) | No | Service payer category (Customer Pay, Warranty, Internal) |
| labor_revenue | NUMERIC(14, 2) | No | Repair-order labor component before combined discount |
| parts_revenue | NUMERIC(14, 2) | No | Repair-order parts component before combined discount |
| discount_amount | NUMERIC(14, 2) | No | Non-negative discount applied to sale or service revenue |
| service_revenue | NUMERIC(14, 2) | No | Labor plus parts minus discount; financial DAX qualifies Completed orders |
| repair_order_quantity | SMALLINT | No | Repair-order unit count, currently one |
| completed_on_time | BOOLEAN | Yes | Generated completed_at <= promised_at boolean; generated, not supplied by load |
| turnaround_hours | NUMERIC(12, 2) | Yes | Generated elapsed completed_at minus opened_at, in hours; generated, not supplied by load |
| loaded_at | TIMESTAMPTZ | No | Database load timestamp with timezone, not a business event date |

## Semantic/reporting fields

| Reporting field | Source / rule |
|---|---|
| revenue, units_sold, vehicle_cost, gross_profit | Signed eligible sales; cancelled rows excluded |
| inventory_units, inventory_value | on_hand_quantity, carrying_cost at one global as-of snapshot |
| aging_bucket / sort | 0–30/1, 31–60/2, 61–90/3, 91–120/4, >120/5 |
| is_slow_moving | age >90, distinct vehicles with positive stock for the DAX count |
| appointment_count | One per staging appointment |
| completed_appointment_count | One only for Completed appointments |
| completion_eligible_count | Completed + Cancelled + No Show; excludes Scheduled |
| service_cost, service_profit | NULL until authoritative cost inputs exist; service_cost_available false |
| completed_date_key, opened_date_key, promised_date_key | Derived date roles in Power Query source projection |
| relationship_segment | Sales Only, Service Only, Sales + Service, No Activity |
| lifecycle_segment | Prospect (0 interactions), New Customer (1), Repeat Customer (2+) |
| activity_segment | Active, Inactive (>365 days since activity relative to latest warehouse activity), Never Active |
| customer_lifetime_value | Historical signed sales revenue + service revenue; context-specific qualifications documented below |

API/customer SQL and Power BI DAX have different date/status contexts.
See [API contracts](api_documentation.md), [dashboard guide](dashboard_guide.md),
[KPI reconciliation](kpi_reconciliation.md) and
[DAX definitions](../powerbi/documentation/dax_measures.md).

The six physical dimensions become twelve imported semantic tables:
DimDate, DimSnapshotDate, DimCustomer, DimVehicle, DimDealership, DimService,
DimSalesperson, DimServiceAdvisor, DimTechnician and the three semantic facts.
Role-playing employee/date tables prevent ambiguous filter paths.

Physical column entries: 207.
