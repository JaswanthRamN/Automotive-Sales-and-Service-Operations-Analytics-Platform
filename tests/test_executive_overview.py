"""Offline checks for Page 1 layout, bindings and filter paths."""
import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]/'powerbi/ExecutiveOverview'


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def visuals():
    return [load(p) for p in (PROJECT/'ExecutiveOverview.Report/definition/pages/executive_overview/visuals').glob('*/visual.json')]


def test_single_page_requested_visuals_and_nonoverlapping_layout():
    base=PROJECT/'ExecutiveOverview.Report/definition/pages'
    assert load(base/'pages.json')['pageOrder']==['executive_overview']
    page=load(base/'executive_overview/page.json')
    items=visuals()
    assert len(items)==18
    assert {v['name'] for v in items if v['visual']['visualType']=='slicer'}=={'slicer_date','slicer_dealer','slicer_brand','slicer_type'}
    assert {'sales_trend','service_trend','brand_sales','dealer_sales','inventory_age'}<={v['name'] for v in items}
    for i,v in enumerate(items):
        a=v['position']
        assert 0<=a['x'] and 0<=a['y'] and a['x']+a['width']<=page['width'] and a['y']+a['height']<=page['height']
        for w in items[i+1:]:
            b=w['position']
            assert a['x']+a['width']<=b['x'] or b['x']+b['width']<=a['x'] or a['y']+a['height']<=b['y'] or b['y']+b['height']<=a['y']


def test_fields_resolve_and_date_relationships():
    model=load(PROJECT/'ExecutiveOverview.SemanticModel/model.bim')['model']
    tables={t['name']:t for t in model['tables']}
    assert len(tables)==12
    for v in visuals():
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
    wrappers={m['name']:m['expression'] for m in tables['FactInventory']['measures'] if m['name'].startswith('Executive ')}
    assert len(wrappers)==3
    assert all('DimDate[full_date]' in e and 'DimSnapshotDate[full_date]' in e for e in wrappers.values())


def test_slicer_interactions_and_credentials_excluded():
    page=load(PROJECT/'ExecutiveOverview.Report/definition/pages/executive_overview/page.json')
    targets={v['name'] for v in visuals() if v['visual']['visualType'] not in ('textbox','slicer')}
    for source in ['slicer_date','slicer_dealer','slicer_brand','slicer_type']:
        assert {r['target'] for r in page['visualInteractions'] if r['source']==source and r['type']=='DataFilter'}==targets
    model=load(PROJECT/'ExecutiveOverview.SemanticModel/model.bim')
    content=json.dumps(model).lower()
    assert 'postgres_password' not in content and 'password=' not in content
    for table in model['model']['tables']:
        assert not {'email','phone'} & {c['name'] for c in table['columns']}
