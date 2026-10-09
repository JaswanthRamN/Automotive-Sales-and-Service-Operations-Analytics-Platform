"""Generate the physical column dictionary from checked-in PostgreSQL DDL."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
GRAINS = {
    'customers':'One source customer / customer_id',
    'vehicles':'One physical vehicle / vehicle_id; VIN unique',
    'dealerships':'One dealership / dealership_id',
    'employees':'One employee / employee_id',
    'sales':'One transaction / sale_id',
    'inventory':'One inventory record / inventory_id and snapshot_date',
    'service_appointments':'One appointment / appointment_id',
    'service_orders':'One repair order / service_order_id; appointment_id unique',
    'dim_date':'One day / date_key; full_date unique',
    'dim_customer':'One business customer version / customer_key',
    'dim_vehicle':'One vehicle / vehicle_key; vehicle_id and VIN unique',
    'dim_dealership':'One dealership / dealership_key',
    'dim_employee':'One employee version / employee_key',
    'dim_service':'One service type / service_key',
    'fact_sales':'One transaction / sales_key; sale_id unique',
    'fact_inventory':'One vehicle/dealership/snapshot / inventory_key',
    'fact_service':'One repair order / service_fact_key; order/appointment IDs unique',
}
MEANINGS = {
    'vin':'17-character vehicle identification number; restricted detail attribute',
    'email':'Customer contact email; excluded from Power BI',
    'phone':'Customer contact phone; excluded from Power BI',
    'first_name':'Person given name; customer names excluded from Power BI',
    'last_name':'Person family name; customer names excluded from Power BI',
    'make':'Vehicle manufacturer, exposed as brand in reporting',
    'body_type':'Vehicle category, exposed as vehicle_type in Power BI',
    'unit_quantity':'Signed sale units: Completed +1, Returned -1; Cancelled excluded from reporting',
    'on_hand_quantity':'Snapshot stock units, currently constrained to one',
    'list_price':'Sale list amount before discount',
    'discount_amount':'Non-negative discount applied to sale or service revenue',
    'sale_price':'Unsigned sale amount after discount; multiply by unit_quantity once for reporting',
    'vehicle_cost':'Unsigned sale vehicle cost; sign once for reporting',
    'gross_profit':'Stored sale_price minus vehicle_cost; return sign applied once in canonical view; losses allowed',
    'labor_revenue':'Repair-order labor component before combined discount',
    'parts_revenue':'Repair-order parts component before combined discount',
    'service_revenue':'Labor plus parts minus discount; financial DAX qualifies Completed orders',
    'carrying_cost':'Vehicle carrying value at inventory snapshot, exposed as inventory_value',
    'days_in_inventory':'Snapshot date minus acquired_date in calendar days',
    'slow_moving_flag':'Derived source/warehouse flag: days_in_inventory >90',
    'completed_on_time':'Generated completed_at <= promised_at boolean',
    'turnaround_hours':'Generated elapsed completed_at minus opened_at, in hours',
    'repair_order_quantity':'Repair-order unit count, currently one',
    'customer_since_date':'Customer registration date, not first qualifying interaction date',
    'effective_from':'Version start; full-refresh model does not preserve prior versions',
    'effective_to':'Version end; 9999-12-31 default',
    'is_current':'Current-version marker; customer/employee uniqueness uses partial indexes',
    'loaded_at':'Database load timestamp with timezone, not a business event date',
    'sale_status':'Completed, Returned or Cancelled',
    'appointment_status':'Completed, Cancelled, No Show or Scheduled',
    'order_status':'Repair-order status; not interchangeable with appointment status',
    'inventory_status':'Available, Reserved, In Transit, Demonstrator, Sold Not Delivered or Unavailable',
    'payment_type':'Finance, Cash or Lease',
    'customer_type':'Individual, Business or Fleet',
    'vehicle_condition':'New or Used',
    'employment_status':'Active or Inactive',
    'role':'Sales Consultant, Service Advisor, Service Technician, Inventory Specialist or Manager',
    'payer_type':'Service payer category (Customer Pay, Warranty, Internal)',
    'manufacturer_msrp':'Manufacturer reference list amount, non-negative',
    'mileage_at_acquisition':'Non-negative odometer value at acquisition; source has no explicit unit metadata',
    'week_of_year':'ISO week number; pair with ISO year, not always calendar_year',
    'day_of_week':'ISO weekday 1–7',
}


def meaning(name):
    if name in MEANINGS: return MEANINGS[name]
    if name.endswith('_date_key') or name == 'date_key': return 'YYYYMMDD integer business calendar key'
    if name.endswith('_key'): return 'Surrogate primary key or dimension foreign key; see DDL constraints'
    if name.endswith('_id'): return 'Source business identifier; retain as text'
    if name.endswith('_at'): return 'Naive local business timestamp; no dealership timezone metadata'
    if name.endswith('_date') or name == 'full_date': return 'ISO calendar date; business event or calendar attribute'
    return name.replace('_', ' ').capitalize()


def build():
    lines = ['# Data dictionary', '',
        'Generated from sql/002_create_staging_tables.sql, sql/003_create_dimensions.sql',
        'and sql/004_create_facts.sql. Regenerate with `python scripts/build_data_dictionary.py`.', '',
        'Raw/processed CSVs contain the source fields of their eight staging tables;',
        'loaded_at is supplied by PostgreSQL and is not a CSV input.',
        'Staging stores every field as TEXT; cleaned CSV date/number contracts are',
        'enforced by Pandas preflight before PostgreSQL casting. Raw data is synthetic.',
        'Nullability below describes physical SQL columns, not every reporting view.', '',
        'Warehouse dimensions/facts live in analytics, not a separate warehouse schema.',
        'Business dates are local dates; no dealership timezone or universal currency',
        'is defined. Monetary amounts use numeric decimal types. Refer to DDL for',
        'full CHECK, FK, UNIQUE and generated-column expressions and migration 006',
        'for hardened return-unit validation.', '',
        '## Physical tables and all columns', '']
    count = 0
    for filename in ('002_create_staging_tables.sql', '003_create_dimensions.sql', '004_create_facts.sql'):
        sql = (ROOT / 'sql' / filename).read_text()
        for schema, table, body in re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)\.(\w+) \((.*?)\n\);', sql, re.S):
            lines.extend([f'### {schema}.{table}', '', f'Grain: {GRAINS[table]}.', '',
                          '| Column | SQL type | Nullable? | Meaning |', '|---|---|---|---|'])
            for line in body.splitlines():
                match = re.match(r'\s{4}(\w+)\s+((?:VARCHAR|CHAR|NUMERIC|BIGINT|INTEGER|SMALLINT|TEXT|DATE|TIMESTAMPTZ|TIMESTAMP|BOOLEAN)(?:\([^)]*\))?)\b(.*)', line)
                if not match: continue
                name, kind, tail = match.groups()
                # Word boundary above leaves parenthesized lengths in tail.
                if tail.startswith('('):
                    length = tail[:tail.index(')')+1]
                    kind += length
                    tail = tail[len(length):]
                nullable = 'No' if 'NOT NULL' in tail or 'PRIMARY KEY' in tail else 'Yes'
                desc = meaning(name)
                if schema == 'staging' and name != 'loaded_at': desc += '; validated/cast from cleaned CSV'
                if 'GENERATED ALWAYS AS (' in tail: desc += '; generated, not supplied by load'
                lines.append(f'| {name} | {kind} | {nullable} | {desc} |')
                count += 1
            lines.append('')
    lines.extend(['## Semantic/reporting fields', '',
        '| Reporting field | Source / rule |', '|---|---|',
        '| revenue, units_sold, vehicle_cost, gross_profit | Signed eligible sales; cancelled rows excluded |',
        '| inventory_units, inventory_value | on_hand_quantity, carrying_cost at one global as-of snapshot |',
        '| aging_bucket / sort | 0–30/1, 31–60/2, 61–90/3, 91–120/4, >120/5 |',
        '| is_slow_moving | age >90, distinct vehicles with positive stock for the DAX count |',
        '| appointment_count | One per staging appointment |',
        '| completed_appointment_count | One only for Completed appointments |',
        '| completion_eligible_count | Completed + Cancelled + No Show; excludes Scheduled |',
        '| service_cost, service_profit | NULL until authoritative cost inputs exist; service_cost_available false |',
        '| completed_date_key, opened_date_key, promised_date_key | Derived date roles in Power Query source projection |',
        '| relationship_segment | Sales Only, Service Only, Sales + Service, No Activity |',
        '| lifecycle_segment | Prospect (0 interactions), New Customer (1), Repeat Customer (2+) |',
        '| activity_segment | Active, Inactive (>365 days since activity relative to latest warehouse activity), Never Active |',
        '| customer_lifetime_value | Historical signed sales revenue + service revenue; context-specific qualifications documented below |',
        '', 'API/customer SQL and Power BI DAX have different date/status contexts.',
        'See [API contracts](api_documentation.md), [dashboard guide](dashboard_guide.md),',
        '[KPI reconciliation](kpi_reconciliation.md) and',
        '[DAX definitions](../powerbi/documentation/dax_measures.md).', '',
        'The six physical dimensions become twelve imported semantic tables:',
        'DimDate, DimSnapshotDate, DimCustomer, DimVehicle, DimDealership, DimService,',
        'DimSalesperson, DimServiceAdvisor, DimTechnician and the three semantic facts.',
        'Role-playing employee/date tables prevent ambiguous filter paths.', '',
        f'Physical column entries: {count}.', ''])
    return '\n'.join(lines)


if __name__ == '__main__':
    path = ROOT / 'docs/data_dictionary.md'
    path.write_text(build(), encoding='utf-8')
    print(path)
