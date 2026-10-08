"""KPI edge cases and an independently executed SQL oracle."""
import importlib.util
import json
from pathlib import Path
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


reconcile = module('reconcile_kpis')


def fixture():
    return {
        'DimCustomer': pd.DataFrame({'customer_key': [1, 2, 3], 'customer_id': ['A', 'B', 'C']}),
        'DimVehicle': pd.DataFrame({'vehicle_key': [1, 2], 'brand': ['X', 'Y'], 'vehicle_type': ['SUV', 'Sedan']}),
        'FactSales': pd.DataFrame([
            dict(sale_id='S1', customer_key=1, vehicle_key=1, dealership_key=1, sale_date_key=20240131, sale_status='Completed', revenue=100., units_sold=1, gross_profit=10.),
            dict(sale_id='S2', customer_key=3, vehicle_key=2, dealership_key=2, sale_date_key=20240201, sale_status='Returned', revenue=-100., units_sold=-1, gross_profit=-10.),
        ]),
        'FactInventory': pd.DataFrame([
            dict(vehicle_key=1, dealership_key=1, snapshot_date_key=20240101, inventory_units=1, inventory_value=9999., days_in_inventory=500),
            dict(vehicle_key=1, dealership_key=1, snapshot_date_key=20240201, inventory_units=1, inventory_value=20., days_in_inventory=90),
            dict(vehicle_key=2, dealership_key=2, snapshot_date_key=20240201, inventory_units=1, inventory_value=30., days_in_inventory=91),
        ]),
        'FactService': pd.DataFrame([
            dict(appointment_id='A1', service_fact_key=1, service_order_id='O1', customer_key=1, vehicle_key=1, dealership_key=1, appointment_date_key=20240131, completed_date_key=20240201, order_status='Completed', service_revenue=30., completed_appointment_count=1, completion_eligible_count=1),
            dict(appointment_id='A2', service_fact_key=2, service_order_id='O2', customer_key=2, vehicle_key=2, dealership_key=2, appointment_date_key=20240201, completed_date_key=20240202, order_status='Completed', service_revenue=40., completed_appointment_count=1, completion_eligible_count=1),
            dict(appointment_id='A3', service_fact_key=None, service_order_id=None, customer_key=3, vehicle_key=2, dealership_key=2, appointment_date_key=20240201, completed_date_key=None, order_status=None, service_revenue=0., completed_appointment_count=0, completion_eligible_count=1),
        ]),
    }


def test_returns_dates_snapshots_and_combined_customers():
    data = fixture()
    all_kpis = reconcile.snapshot_kpis(data)
    assert all_kpis['Revenue'] == all_kpis['Units Sold'] == all_kpis['Gross Profit'] == 0
    assert all_kpis['Gross Margin %'] is None
    assert all_kpis['Inventory Value'] == 50
    assert all_kpis['Average Days in Inventory'] == Decimal('90.5')
    assert all_kpis['Slow-Moving Vehicles'] == 1
    assert all_kpis['Service Revenue'] == 70 and all_kpis['Service Orders'] == 2
    assert all_kpis['Repeat Customers'] == 1 and all_kpis['Repeat Rate'] == Decimal('0.5')
    january = reconcile.snapshot_kpis(data, start='2024-01-01', end='2024-01-31')
    assert january['Service Revenue'] == 0 and january['Completion Rate'] == 1
    assert january['Inventory Value'] == 9999
    assert january['Repeat Customers'] == 0
    february = reconcile.snapshot_kpis(data, start='2024-02-01', end='2024-02-29')
    assert february['Service Revenue'] == 70 and february['Repeat Customers'] == 0
    assert february['Customer Lifetime Value'] == 70
    empty = reconcile.snapshot_kpis(data, brand='UNKNOWN')
    assert empty['Revenue'] == empty['Repeat Customers'] == empty['Inventory Units'] == 0
    assert empty['Customers'] == 3  # Registered population, not activity count.
    assert reconcile.snapshot_kpis(data, end='1900-01-01')['Inventory Value'] is None


def test_independent_warehouse_sql_matches_filtered_snapshot():
    data = fixture()
    engine = create_engine('sqlite://')
    with engine.connect() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS analytics")
        data['DimCustomer'].to_sql('dim_customer', conn, schema='analytics', index=False)
        data['DimVehicle'].rename(columns={'brand':'make', 'vehicle_type':'body_type'}).to_sql('dim_vehicle', conn, schema='analytics', index=False)
        sales = data['FactSales'].rename(columns={'units_sold':'unit_quantity'}).copy()
        sales['sale_price'] = sales.revenue / sales.unit_quantity
        sales['gross_profit'] = sales.gross_profit / sales.unit_quantity
        sales.to_sql('fact_sales', conn, schema='analytics', index=False)
        data['FactInventory'].rename(columns={'inventory_units':'on_hand_quantity', 'inventory_value':'carrying_cost'}).to_sql('fact_inventory', conn, schema='analytics', index=False)
        data['FactService'].dropna(subset=['service_fact_key']).to_sql('fact_service', conn, schema='analytics', index=False)
        data['FactService'].to_sql('vw_service_appointment_detail', conn, schema='analytics', index=False)

        class SQLiteOracle:
            def execute(self, query, params):
                return conn.execute(text(str(query).replace('::numeric', '*1.0').replace('::bigint', '')), params)

        for filters in ({}, {'start':'2024-02-01', 'end':'2024-02-29'}, {'end':'2024-01-31'},
                        {'brand':'UNKNOWN'}, {'dealership':1}, {'brand':'Y'}, {'vehicle_type':'SUV'}, {'end':'1900-01-01'}):
            expected = reconcile.snapshot_kpis(data, **filters)
            actual = reconcile.postgres_kpis(SQLiteOracle(), filters)
            assert all(row['status'] == 'PASS' for row in reconcile.compare(expected, actual)), (filters, reconcile.compare(expected, actual))


def test_comparison_rejects_missing_counts_and_rounded_ratios():
    assert reconcile.compare({'Customers': 3}, {})[0]['status'] == 'FAIL'
    assert reconcile.compare({'Customers': 3}, {'Customers': 3.01})[0]['status'] == 'FAIL'
    assert reconcile.compare({'Revenue': 100}, {'Revenue': 100.005})[0]['status'] == 'PASS'
    assert reconcile.compare({'Gross Margin %': Decimal('0.13968')}, {'Gross Margin %': Decimal('0.14')})[0]['status'] == 'FAIL'


def test_snapshot_metadata_uses_non_null_values(tmp_path):
    builder = module('build_executive_overview')
    folder = tmp_path / 'local-data'
    folder.mkdir()
    rows = [{'completed_date_key':None, 'completed_at':None, 'service_cost':None},
            {'completed_date_key':20240201, 'completed_at':'2024-02-01T12:00:00', 'service_cost':None}]
    for table in builder.SOURCES:
        (folder / f'{table}.json').write_text(json.dumps(rows))
    types = dict(builder.metadata_from_snapshot(tmp_path)['FactService'])
    assert types == {'completed_date_key':23, 'completed_at':1114, 'service_cost':1700}


def test_duplicate_order_fails_gate():
    data = fixture()
    orders = data['FactService'].service_order_id.dropna()
    data['FactService'].loc[orders.index[1], 'service_order_id'] = orders.iloc[0]
    assert 'Duplicate service order: revenue would multiply' in reconcile.grain_errors(data)
