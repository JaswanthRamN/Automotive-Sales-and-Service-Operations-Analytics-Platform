"""Read-only snapshot/PostgreSQL KPI reconciliation; never executes DAX.

Default: offline snapshot checks. --postgres compares live warehouse totals
within one repeatable-read transaction. --dax-results accepts the single-row
CSV exported from powerbi/dax/measures.dax in Desktop (unfiltered only).
Nonzero exit on mismatch, invalid model/data, or unavailable requested engine.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
PROJECT = ROOT / 'powerbi/ExecutiveOverview'
MONEY = {'Revenue', 'Gross Profit', 'Inventory Value', 'Service Revenue',
         'Customer Lifetime Value'}
COUNTS = {'Units Sold', 'Inventory Units', 'Slow-Moving Vehicles',
          'Service Orders', 'Customers', 'Repeat Customers'}


def read_snapshot(project=PROJECT):
    return {p.stem: pd.read_json(p, convert_dates=False)
            for p in (project / 'local-data').glob('*.json')}


def validate_model(data, model):
    errors = []
    tables = {t['name']: t for t in model['tables']}
    catalogue = (ROOT / 'powerbi/dax/measures.dax').read_text()
    definitions = re.findall(r'^\s*MEASURE (\w+)\[([^]]+)\]\s*=\s*(.*?)(?=^\s*MEASURE |^EVALUATE)', catalogue, re.M | re.S)
    def normalize(expression):
        return re.sub(r'\s+', ' ', re.sub(r'//[^\n]*', '', expression)).strip()
    for home, name, expression in definitions:
        deployed = next((m['expression'] for m in tables[home].get('measures', []) if m['name'] == name), '')
        if normalize(expression) != normalize(deployed):
            errors.append(f'DAX catalogue/model drift: {name}')
    for rel in model['relationships']:
        one, many = data[rel['toTable']], data[rel['fromTable']]
        key = one[rel['toColumn']]
        if key.isna().any() or key.duplicated().any():
            errors.append(f"Nonunique/null dimension: {rel['name']}")
        values = many[rel['fromColumn']].dropna()
        if not values.isin(key).all():
            errors.append(f"Orphan relationship: {rel['name']}")
        if (rel['crossFilteringBehavior'], rel['fromCardinality'], rel['toCardinality']) != ('oneDirection', 'many', 'one'):
            errors.append(f"Unsafe relationship: {rel['name']}")
        types = []
        for table, column in ((rel['fromTable'], rel['fromColumn']), (rel['toTable'], rel['toColumn'])):
            types.append(next(c['dataType'] for c in tables[table]['columns'] if c['name'] == column))
        if types[0] != types[1]:
            errors.append(f"Relationship type mismatch: {rel['name']}")
    errors.extend(grain_errors(data))
    if errors:
        raise ValueError('; '.join(errors))


def grain_errors(data):
    errors = []
    for table, keys in [('FactSales', ['sale_id']), ('FactService', ['appointment_id']),
                        ('FactInventory', ['vehicle_key', 'dealership_key', 'snapshot_date_key'])]:
        if data[table].duplicated(keys).any() or data[table][keys].isna().any().any():
            errors.append(f'Duplicate/null grain: {table}')
    orders = data['FactService']['service_order_id'].dropna()
    if orders.duplicated().any():
        errors.append('Duplicate service order: revenue would multiply')
    return errors


def snapshot_kpis(data, *, start=None, end=None, dealership=None, brand=None, vehicle_type=None):
    """Independent Pandas implementation of documented filter/KPI contract."""
    def filtered(table, date_column=None):
        frame = data[table].copy()
        if dealership is not None:
            frame = frame[frame.dealership_key == dealership]
        vehicles = data['DimVehicle']
        if brand is not None:
            vehicles = vehicles[vehicles.brand == brand]
        if vehicle_type is not None:
            vehicles = vehicles[vehicles.vehicle_type == vehicle_type]
        frame = frame[frame.vehicle_key.isin(vehicles.vehicle_key)]
        if date_column:
            if start: frame = frame[frame[date_column] >= int(start.replace('-', ''))]
            if end: frame = frame[frame[date_column] <= int(end.replace('-', ''))]
        return frame

    sales = filtered('FactSales', 'sale_date_key')
    service = filtered('FactService', 'completed_date_key')
    service = service[service.order_status == 'Completed']
    appointments = filtered('FactService', 'appointment_date_key')
    inventory = filtered('FactInventory')
    available = data['FactInventory'].snapshot_date_key
    if end: available = available[available <= int(end.replace('-', ''))]
    snapshot = None if available.empty else int(available.max())
    inventory = inventory[inventory.snapshot_date_key == snapshot]

    def total(frame, column):
        return sum((Decimal(str(x)) for x in frame[column].dropna()), Decimal(0))

    def ratio(numerator, denominator):
        return numerator / denominator if denominator else None

    revenue, units, profit = [total(sales, col) for col in ('revenue', 'units_sold', 'gross_profit')]
    stock_units = total(inventory, 'inventory_units')
    service_revenue = total(service, 'service_revenue')
    orders = service.service_order_id.nunique()
    # Resolve surrogate versions to business IDs, combining facts without a
    # cross-fact join. Distinct IDs within each source avoid multiplied activity.
    customers = data['DimCustomer'].set_index('customer_key').customer_id
    activity = pd.concat([
        sales[sales.sale_status == 'Completed'][['customer_key', 'sale_id']].drop_duplicates().customer_key.map(customers),
        service[['customer_key', 'service_order_id']].drop_duplicates().customer_key.map(customers),
    ]).value_counts()
    result = {
        'Revenue': revenue, 'Units Sold': units, 'ASP': ratio(revenue, units),
        'Gross Profit': profit, 'Gross Margin %': ratio(profit, revenue),
        'Inventory Units': stock_units if snapshot else None,
        'Inventory Value': total(inventory, 'inventory_value') if snapshot else None,
        'Average Days in Inventory': ratio(total(inventory.assign(weighted=inventory.days_in_inventory * inventory.inventory_units), 'weighted'), stock_units),
        'Slow-Moving Vehicles': inventory[(inventory.days_in_inventory > 90) & (inventory.inventory_units > 0)].vehicle_key.nunique() if snapshot else None,
        'Service Revenue': service_revenue, 'Service Orders': orders,
        'Average Repair Order': ratio(service_revenue, orders),
        'Completion Rate': ratio(total(appointments, 'completed_appointment_count'), total(appointments, 'completion_eligible_count')),
        'Customers': data['DimCustomer'].customer_id.nunique(),
        'Repeat Customers': int((activity >= 2).sum()),
        'Repeat Rate': ratio(Decimal(int((activity >= 2).sum())), len(activity)),
    }
    # CLV removes the lower bound but preserves as-of and non-date filters.
    history_sales = filtered('FactSales')
    history_service = filtered('FactService')
    history_service = history_service[history_service.order_status == 'Completed']
    if end:
        key = int(end.replace('-', ''))
        history_sales = history_sales[history_sales.sale_date_key <= key]
        history_service = history_service[history_service.completed_date_key <= key]
    result['Customer Lifetime Value'] = total(history_sales, 'revenue') + total(history_service, 'service_revenue')
    return result


def compare(expected, actual):
    rows = []
    for name, value in expected.items():
        other = actual.get(name)
        tolerance = Decimal(0) if name in COUNTS else Decimal('0.01') if name in MONEY else Decimal('0.00000001')
        delta = None if value is None or other is None else Decimal(str(other)) - Decimal(str(value))
        passed = name in actual and ((value is None and other is None) or (delta is not None and abs(delta) <= tolerance))
        rows.append({'kpi': name, 'expected': value, 'actual': other, 'difference': delta, 'status': 'PASS' if passed else 'FAIL'})
    return rows


def typed_query(sql):
    # NULL bind parameters also need PostgreSQL types in IS NULL predicates.
    from sqlalchemy import text
    types = {'start':'text', 'end':'text', 'dealer':'bigint', 'brand':'text', 'vehicle_type':'text'}
    return text(re.sub(r'(?<!:):(start|end|dealer|brand|vehicle_type)\b',
                       lambda match: f'CAST(:{match[1]} AS {types[match[1]]})', sql))


def postgres_kpis(connection, filters):
    # Independent warehouse projections: no sales/service join and no revenue
    # aggregation after customer joins. Reference query combines scalar totals.
    params = {'start': filters.get('start'), 'end': filters.get('end'),
              'dealer': filters.get('dealership'), 'brand': filters.get('brand'),
              'vehicle_type': filters.get('vehicle_type')}
    predicates = """(:dealer IS NULL OR f.dealership_key=:dealer)
      AND (:brand IS NULL OR v.make=:brand)
      AND (:vehicle_type IS NULL OR v.body_type=:vehicle_type)"""
    period = lambda column: f"(:start IS NULL OR {column} >= CAST(replace(:start,'-','') AS integer)) AND (:end IS NULL OR {column} <= CAST(replace(:end,'-','') AS integer))"
    sql = f"""WITH sales_source AS (
      SELECT f.sale_id,f.customer_key,f.sale_status,f.sale_date_key,
        f.sale_price*f.unit_quantity revenue,f.unit_quantity units_sold,
        f.gross_profit*f.unit_quantity gross_profit
      FROM analytics.fact_sales f JOIN analytics.dim_vehicle v USING(vehicle_key)
      WHERE f.sale_status IN ('Completed','Returned') AND {predicates}
    ), sales_filtered AS (SELECT * FROM sales_source WHERE {period('sale_date_key')}),
    stock_source AS (
      SELECT f.snapshot_date_key,f.vehicle_key,f.on_hand_quantity inventory_units,
        f.carrying_cost inventory_value,f.days_in_inventory
      FROM analytics.fact_inventory f JOIN analytics.dim_vehicle v USING(vehicle_key)
      WHERE {predicates} AND f.snapshot_date_key=(SELECT max(snapshot_date_key)
        FROM analytics.fact_inventory WHERE :end IS NULL OR snapshot_date_key<=CAST(replace(:end,'-','') AS integer))
    ), service_source AS (
      SELECT f.* FROM analytics.fact_service f JOIN analytics.dim_vehicle v USING(vehicle_key)
      WHERE {predicates}
    ), service_filtered AS (SELECT * FROM service_source WHERE {period('completed_date_key')}),
    appointment_flags AS (
      SELECT a.service_fact_key,a.customer_key,a.service_order_id,a.service_revenue,
        a.completed_appointment_count,a.completion_eligible_count
      FROM analytics.vw_service_appointment_detail a
      JOIN analytics.dim_vehicle v ON v.vehicle_key=a.vehicle_key
      WHERE (:dealer IS NULL OR a.dealership_key=:dealer)
        AND (:brand IS NULL OR v.make=:brand) AND (:vehicle_type IS NULL OR v.body_type=:vehicle_type)
        AND {period('a.appointment_date_key')}
    ), service_semantic AS (
      SELECT f.service_fact_key,f.customer_key,f.service_order_id,f.service_revenue,
        0 completed_appointment_count,0 completion_eligible_count FROM service_filtered f
      UNION ALL SELECT NULL,customer_key,NULL,0,completed_appointment_count,completion_eligible_count FROM appointment_flags
    ) """
    reference = (ROOT / 'powerbi/documentation/dax_reference.sql').read_text()
    reference = reference[reference.index('WITH sales AS'):].replace('WITH sales AS', ', sales AS', 1)
    for source, replacement in [('analytics.vw_sales_detail', 'sales_filtered'),
                                ('analytics.vw_inventory_detail', 'stock_source'),
                                ('analytics.vw_service_appointment_detail', 'service_semantic'),
                                ('analytics.fact_service', 'service_filtered')]:
        reference = reference.replace(source, replacement)
    # No snapshot before selected end must be blank, not zero.
    result = dict(connection.execute(typed_query(sql + reference), params).mappings().one())
    snap = connection.execute(typed_query("SELECT max(snapshot_date_key) FROM analytics.fact_inventory WHERE :end IS NULL OR snapshot_date_key<=CAST(replace(:end,'-','') AS integer)"), params).scalar()
    if snap is None:
        for name in ('Inventory Units', 'Inventory Value', 'Average Days in Inventory', 'Slow-Moving Vehicles'): result[name] = None
    history = connection.execute(typed_query(sql + " SELECT (SELECT coalesce(sum(revenue),0) FROM sales_source WHERE :end IS NULL OR sale_date_key<=CAST(replace(:end,'-','') AS integer)) + (SELECT coalesce(sum(service_revenue),0) FROM service_source WHERE order_status='Completed' AND (:end IS NULL OR completed_date_key<=CAST(replace(:end,'-','') AS integer)))"), params).scalar()
    result['Customer Lifetime Value'] = history
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres', action='store_true')
    parser.add_argument('--dax-results', type=Path)
    args = parser.parse_args()
    data = read_snapshot()
    model = json.loads((PROJECT / 'ExecutiveOverview.SemanticModel/model.bim').read_text())['model']
    validate_model(data, model)
    scenarios = {'all': {}, 'empty': {'brand': '__NO_SUCH_BRAND__'},
                 'before_inventory': {'end': '1900-01-01'}}
    for dealer in data['DimDealership'].dealership_key:
        scenarios[f'dealer_{dealer}'] = {'dealership': int(dealer)}
    for brand in data['DimVehicle'].brand.unique(): scenarios[f'brand_{brand}'] = {'brand': brand}
    for kind in data['DimVehicle'].vehicle_type.unique(): scenarios[f'type_{kind}'] = {'vehicle_type': kind}
    months = sorted(data['FactService'].completed_date_key.dropna().astype(int).astype(str).str[:6].unique())
    import calendar
    for month in months:
        year, number = int(month[:4]), int(month[4:])
        scenarios[f'month_{month}'] = {'start': f'{year:04}-{number:02}-01', 'end': f'{year:04}-{number:02}-{calendar.monthrange(year,number)[1]}'}
    output = {'model_checks': 'PASS', 'snapshot_kpis': snapshot_kpis(data),
              'scenario_count': len(scenarios), 'postgres': 'NOT RUN', 'dax': 'NOT RUN'}
    failures = []
    if args.postgres:
        from sqlalchemy import create_engine
        from automotive_analytics.etl import ETLConfig
        config = ETLConfig.from_env(env_file=ROOT / '.env')
        engine = create_engine(config.database_url, connect_args={'connect_timeout': 5, 'options': '-c statement_timeout=30000'})
        try:
            with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
                conn.exec_driver_sql('SET TRANSACTION READ ONLY')
                results = {name: compare(snapshot_kpis(data, **filters), postgres_kpis(conn, filters)) for name, filters in scenarios.items()}
                output['postgres'] = results
                failures.extend(row for rows in results.values() for row in rows if row['status'] == 'FAIL')
        finally:
            engine.dispose()
    if args.dax_results:
        with args.dax_results.open(encoding='utf-8-sig', newline='') as handle:
            records = list(csv.DictReader(handle))
        if len(records) != 1: raise ValueError('Expected exactly one unfiltered DAX ROW export')
        actual = {key.strip('[]'): Decimal(value) if value.strip() else None for key, value in records[0].items()}
        output['dax'] = compare(output['snapshot_kpis'], actual)
        failures.extend(row for row in output['dax'] if row['status'] == 'FAIL')
    print(json.dumps(output, default=str, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'Reconciliation FAILED: {type(exc).__name__}: {exc}', file=sys.stderr)
        raise SystemExit(1)
