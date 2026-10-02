"""Catalogue consistency checks, not a DAX execution substitute."""
from pathlib import Path
import re
import sqlite3

import pytest

ROOT = Path(__file__).resolve().parents[1]
REQUESTED = {
    'Revenue', 'Units Sold', 'ASP', 'Gross Profit', 'Gross Margin %',
    'Inventory Units', 'Inventory Value', 'Average Days in Inventory',
    'Slow-Moving Vehicles', 'Service Revenue', 'Service Orders',
    'Average Repair Order', 'Completion Rate', 'Customers', 'Repeat Customers',
    'Repeat Rate', 'Customer Lifetime Value',
}


def test_every_measure_documented_and_in_reference_query():
    dax = (ROOT / 'powerbi/dax/measures.dax').read_text(encoding='utf-8')
    definitions = re.findall(r'MEASURE (\w+)\[([^]]+)\]', dax)
    names = [name for _, name in definitions]
    assert len(names) == len(set(names)) == 20
    assert REQUESTED <= set(names)
    doc = (ROOT / 'powerbi/documentation/dax_measures.md').read_text(encoding='utf-8')
    sql = (ROOT / 'powerbi/documentation/dax_reference.sql').read_text(encoding='utf-8')
    for home, name in definitions:
        assert f'| {name} ({home}) |' in doc
    for name in REQUESTED:
        assert f'AS "{name}"' in sql
        assert f'"{name}", [{name}]' in dax


def test_dependencies_defined_before_use_and_delimiters_balanced():
    dax = (ROOT / 'powerbi/dax/measures.dax').read_text(encoding='utf-8')
    dax = re.sub(r'//[^\n]*', '', dax)
    parts = re.split(r'MEASURE (\w+)\[([^]]+)\]\s*=', dax)
    known = set()
    for index in range(1, len(parts), 3):
        _, name, expression = parts[index:index+3]
        references = re.findall(r'(?<![\w\]])\[([^]]+)\]', expression)
        # The last expression includes EVALUATE, which can refer to itself.
        assert set(references) <= known | ({name} if 'EVALUATE' in expression else set())
        known.add(name)
    stack = []
    clean = re.sub(r'"[^"]*"', '', dax)
    pairs = {')': '(', ']': '[', '}': '{'}
    for char in clean:
        if char in '([{':
            stack.append(char)
        elif char in ')]}':
            assert stack and stack.pop() == pairs[char]
    assert not stack


def test_model_column_references_have_declared_sources():
    dax = (ROOT / 'powerbi/dax/measures.dax').read_text(encoding='utf-8')
    sources = {
        'FactSales': (ROOT / 'sql/analytics/sales_analytics.sql').read_text(),
        'FactInventory': (ROOT / 'sql/analytics/inventory_analytics.sql').read_text(),
        'FactService': (ROOT / 'sql/analytics/service_analytics.sql').read_text() +
                       (ROOT / 'powerbi/documentation/power_query.md').read_text(),
        'DimCustomer': (ROOT / 'sql/003_create_dimensions.sql').read_text(),
        'DimDate': (ROOT / 'sql/003_create_dimensions.sql').read_text(),
        'DimSnapshotDate': (ROOT / 'sql/003_create_dimensions.sql').read_text(),
    }
    declarations = set(re.findall(r'MEASURE (\w+)\[([^]]+)\]', dax))
    for table, column in re.findall(r'(\w+)\[([^]]+)\]', dax):
        if (table, column) not in declarations:
            assert table in sources
            assert re.search(r'\b' + re.escape(column) + r'\b', sources[table])


def test_reference_contract_handles_returns_snapshots_and_cross_fact_customers():
    # Execute the SQL oracle with a controlled fixture. This tests the business
    # contract independently; actual DAX filter-context execution needs Power BI.
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        ATTACH DATABASE ':memory:' AS analytics;
        CREATE TABLE analytics.dim_customer(customer_key INTEGER,customer_id TEXT);
        INSERT INTO analytics.dim_customer VALUES(1,'A'),(2,'B'),(3,'C');
        CREATE TABLE analytics.vw_sales_detail(sale_id TEXT,customer_key INTEGER,
            sale_status TEXT,revenue REAL,units_sold INTEGER,gross_profit REAL);
        INSERT INTO analytics.vw_sales_detail VALUES
            ('S1',1,'Completed',100,1,10),('S2',3,'Returned',-100,-1,-10);
        CREATE TABLE analytics.vw_inventory_detail(snapshot_date_key INTEGER,
            vehicle_key INTEGER,inventory_units INTEGER,inventory_value REAL,days_in_inventory INTEGER);
        INSERT INTO analytics.vw_inventory_detail VALUES
            (20240101,1,1,9999,500),(20240201,1,1,20,90),(20240201,2,1,30,91);
        CREATE TABLE analytics.fact_service(service_fact_key INTEGER,order_status TEXT);
        INSERT INTO analytics.fact_service VALUES(1,'Completed'),(2,'Completed'),(3,'Reopened');
        CREATE TABLE analytics.vw_service_appointment_detail(service_fact_key INTEGER,
            customer_key INTEGER,service_order_id TEXT,service_revenue REAL,
            completed_appointment_count INTEGER,completion_eligible_count INTEGER);
        INSERT INTO analytics.vw_service_appointment_detail VALUES
            (1,1,'O1',30,1,1),(2,2,'O2',40,1,1),
            (NULL,3,NULL,0,0,1),(NULL,3,NULL,0,0,0),(3,3,'O3',500,0,0);
    """)
    sql = (ROOT / 'powerbi/documentation/dax_reference.sql').read_text()
    sql = sql.replace('::numeric', '*1.0').replace('::bigint', '')
    try:
        row = connection.execute(sql).fetchone()
        assert row['Revenue'] == row['Units Sold'] == row['Gross Profit'] == 0
        assert row['ASP'] is None and row['Gross Margin %'] is None
        assert row['Inventory Units'] == 2 and row['Inventory Value'] == 50
        assert row['Average Days in Inventory'] == pytest.approx(90.5)
        assert row['Slow-Moving Vehicles'] == 1
        assert row['Service Revenue'] == 70 and row['Service Orders'] == 2
        assert row['Average Repair Order'] == 35
        assert row['Completion Rate'] == pytest.approx(2/3)
        assert row['Customers'] == 3 and row['Repeat Customers'] == 1
        assert row['Repeat Rate'] == pytest.approx(0.5)
        assert row['Customer Lifetime Value'] == 70
        connection.execute('DELETE FROM analytics.vw_service_appointment_detail')
        connection.execute('DELETE FROM analytics.vw_sales_detail')
        empty = connection.execute(sql).fetchone()
        assert empty['Service Orders'] == empty['Repeat Customers'] == 0
        assert empty['Completion Rate'] is None and empty['Repeat Rate'] is None
        assert empty['Average Repair Order'] is None
    finally:
        connection.close()
