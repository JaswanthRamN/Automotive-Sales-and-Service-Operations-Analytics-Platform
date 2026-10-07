"""Offline checks for Power BI report layout, bindings and filter paths."""
import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]/'powerbi/ExecutiveOverview'


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def page_visuals(page):
    return [load(p) for p in (PROJECT/f'ExecutiveOverview.Report/definition/pages/{page}/visuals').glob('*/visual.json')]


def assert_nonoverlapping(page, items):
    for i,v in enumerate(items):
        a=v['position']
        assert 0<=a['x'] and 0<=a['y'] and a['x']+a['width']<=page['width'] and a['y']+a['height']<=page['height']
        for w in items[i+1:]:
            b=w['position']
            assert a['x']+a['width']<=b['x'] or b['x']+b['width']<=a['x'] or a['y']+a['height']<=b['y'] or b['y']+b['height']<=a['y']


def test_requested_pages_visuals_and_nonoverlapping_layout():
    base=PROJECT/'ExecutiveOverview.Report/definition/pages'
    assert load(base/'pages.json')['pageOrder']==['executive_overview','sales_inventory','service_customer','vehicle_model_detail']
    page=load(base/'executive_overview/page.json')
    items=page_visuals('executive_overview')
    assert len(items)==18
    assert {v['name'] for v in items if v['visual']['visualType']=='slicer'}=={'slicer_date','slicer_dealer','slicer_brand','slicer_type'}
    assert {'sales_trend','service_trend','brand_sales','dealer_sales','inventory_age'}<={v['name'] for v in items}
    assert_nonoverlapping(page, items)

    page2=load(base/'sales_inventory/page.json')
    page2_items=page_visuals('sales_inventory')
    assert len(page2_items)==21
    assert {v['name'] for v in page2_items if v['visual']['visualType']=='slicer'}=={'slicer_date','slicer_dealer','slicer_brand','slicer_type'}
    assert {'monthly_sales','salesperson_perf','brand_model_perf','inventory_aging','inventory_by_model','vehicle_model_matrix'}<={v['name'] for v in page2_items}
    assert_nonoverlapping(page2, page2_items)

    page3=load(base/'service_customer/page.json')
    page3_items=page_visuals('service_customer')
    assert len(page3_items)==22
    assert {v['name'] for v in page3_items if v['visual']['visualType']=='slicer'}=={'slicer_date','slicer_dealer','slicer_brand','slicer_type'}
    assert {'service_monthly','technician_perf','service_type_perf','customer_value_by_type',
        'customer_region_repeat','customer_service_matrix'}<={v['name'] for v in page3_items}
    assert_nonoverlapping(page3, page3_items)

    drill=load(base/'vehicle_model_detail/page.json')
    drill_items=page_visuals('vehicle_model_detail')
    assert drill['type']=='Drillthrough'
    assert drill['visibility']=='HiddenInViewMode'
    assert drill['pageBinding']['type']=='Drillthrough'
    assert {p['fieldExpr']['Column']['Property'] for p in drill['pageBinding']['parameters']}=={'brand','model','vehicle_type'}
    assert {p['boundFilter'] for p in drill['pageBinding']['parameters']}=={'DimVehicle.brand','DimVehicle.model','DimVehicle.vehicle_type'}
    assert {'detail_table','brand_card','model_card','type_card','snapshot_card'}<={v['name'] for v in drill_items}
    assert_nonoverlapping(drill, drill_items)


def test_fields_resolve_and_date_relationships():
    model=load(PROJECT/'ExecutiveOverview.SemanticModel/model.bim')['model']
    tables={t['name']:t for t in model['tables']}
    assert len(tables)==12
    for page in ['executive_overview','sales_inventory','service_customer','vehicle_model_detail']:
      for v in page_visuals(page):
        for role in v['visual'].get('query',{}).get('queryState',{}).values():
            for p in role['projections']:
                kind,expr=next(iter(p['field'].items()))
                table=tables[expr['Expression']['SourceRef']['Entity']]
                fields=table.get('measures',[]) if kind=='Measure' else table['columns']
                assert expr['Property'] in {f['name'] for f in fields}
    assert len(model['relationships'])==20
    for r in model['relationships']:
        assert r['crossFilteringBehavior']=='oneDirection'
        assert r['fromCardinality']=='many' and r['toCardinality']=='one'
        assert r['fromColumn'] in {c['name'] for c in tables[r['fromTable']]['columns']}
        assert r['toColumn'] in {c['name'] for c in tables[r['toTable']]['columns']}
        if r['fromTable']=='FactService' and r['fromColumn']=='completed_date_key': assert not r['isActive']
    wrappers={m['name']:m['expression'] for m in tables['FactInventory']['measures'] if m['name'].startswith('Executive ') or m['name'].startswith('As-Of ')}
    assert {'Executive Inventory Value','Executive Inventory Units','Executive Snapshot Date',
        'As-Of Inventory Value','As-Of Inventory Units','As-Of Average Days in Inventory',
        'As-Of Slow-Moving Vehicles','As-Of Snapshot Date'} <= set(wrappers)
    assert all('DimDate[full_date]' in e and 'DimSnapshotDate[full_date]' in e for e in wrappers.values())
    customer_measures={m['name']:m for m in tables['DimCustomer']['measures']}
    assert {'Customers','Repeat Customers','Repeat Rate','Customer Lifetime Value',
        'Customers with Sales','Customers with Service','Sales + Service Customers','Service Frequency'} <= set(customer_measures)
    assert customer_measures['Customers with Sales']['isHidden']
    assert customer_measures['Customers with Service']['isHidden']


def test_slicer_interactions_and_credentials_excluded():
    page=load(PROJECT/'ExecutiveOverview.Report/definition/pages/executive_overview/page.json')
    targets={v['name'] for v in page_visuals('executive_overview') if v['visual']['visualType'] not in ('textbox','slicer')}
    for source in ['slicer_date','slicer_dealer','slicer_brand','slicer_type']:
        assert {r['target'] for r in page['visualInteractions'] if r['source']==source and r['type']=='DataFilter'}==targets
    page2=load(PROJECT/'ExecutiveOverview.Report/definition/pages/sales_inventory/page.json')
    targets={v['name'] for v in page_visuals('sales_inventory') if v['visual']['visualType'] not in ('textbox','slicer')}
    for source in ['slicer_date','slicer_dealer','slicer_brand','slicer_type']:
        assert {r['target'] for r in page2['visualInteractions'] if r['source']==source and r['type']=='DataFilter'}==targets
    page3=load(PROJECT/'ExecutiveOverview.Report/definition/pages/service_customer/page.json')
    targets={v['name'] for v in page_visuals('service_customer') if v['visual']['visualType'] not in ('textbox','slicer')}
    for source in ['slicer_date','slicer_dealer','slicer_brand','slicer_type']:
        assert {r['target'] for r in page3['visualInteractions'] if r['source']==source and r['type']=='DataFilter'}==targets
    model=load(PROJECT/'ExecutiveOverview.SemanticModel/model.bim')
    content=json.dumps(model).lower()
    assert 'postgres_password' not in content and 'password=' not in content
    for table in model['model']['tables']:
        assert not {'email','phone'} & {c['name'] for c in table['columns']}
