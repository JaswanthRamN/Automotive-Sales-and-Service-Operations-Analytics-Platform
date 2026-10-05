"""Build Page 1 PBIP/PBIR and bootstrap its model from a PostgreSQL snapshot.

Snapshot JSON is local/ignored. Direct PostgreSQL refresh remains available via
the model's UseLocalSnapshot parameter. Never embeds database credentials.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sqlalchemy import create_engine, text
from automotive_analytics.etl import ETLConfig

PROJECT = ROOT / 'powerbi/ExecutiveOverview'
BASE = 'https://developer.microsoft.com/json-schemas/fabric/item/report/'
DEFINITION = BASE + 'definition/'
PAGE = 'executive_overview'

CALENDAR = """WITH bounds AS (
 SELECT date_trunc('year',min(d))::date lo,
 (date_trunc('year',max(d))+interval '1 year - 1 day')::date hi
 FROM (SELECT full_date d FROM analytics.dim_date
 UNION ALL SELECT promised_at::date FROM analytics.fact_service) events
), calendar AS (SELECT generate_series(lo,hi,interval '1 day')::date full_date FROM bounds)
SELECT to_char(full_date,'YYYYMMDD')::integer date_key, full_date,
 extract(year FROM full_date)::integer calendar_year,
 extract(month FROM full_date)::integer month_number,
 to_char(full_date,'Month') month_name, to_char(full_date,'YYYY-MM') year_month,
 to_char(full_date,'YYYYMM')::integer year_month_sort,
 extract(quarter FROM full_date)::integer quarter_number FROM calendar"""

SOURCES = {
 'DimDate': CALENDAR,
 'DimSnapshotDate': CALENDAR,
 'DimCustomer': 'SELECT customer_key,customer_id,customer_type,city,state,postal_code,customer_since_date,effective_from,effective_to,is_current FROM analytics.dim_customer',
 'DimVehicle': 'SELECT vehicle_key,vehicle_id,make AS brand,model,model_year,body_type AS vehicle_type,fuel_type,vehicle_condition,color FROM analytics.dim_vehicle',
 'DimDealership': 'SELECT dealership_key,dealership_id,dealership_name,city,state,region,postal_code,opened_date FROM analytics.dim_dealership',
 'DimService': 'SELECT service_key,service_type,service_category,is_active FROM analytics.dim_service',
 'FactSales': 'SELECT sales_key,sale_id,sale_date_key,customer_key,vehicle_key,dealership_key,salesperson_key,sales_channel,payment_type,sale_status,units_sold,list_price,discount_amount,revenue,vehicle_cost,gross_profit FROM analytics.vw_sales_detail',
 'FactInventory': "SELECT inventory_key,inventory_id,snapshot_date_key,vehicle_key,dealership_key,acquired_date,to_char(acquired_date,'YYYYMMDD')::integer acquired_date_key,inventory_status,inventory_units,inventory_value,days_in_inventory,aging_bucket,aging_bucket_sort,is_slow_moving FROM analytics.vw_inventory_detail",
 'FactService': """SELECT a.appointment_id,a.appointment_date_key,a.customer_key,a.vehicle_key,
 a.dealership_key,a.service_advisor_key,a.technician_key,a.service_key,a.service_order_id,
 a.appointment_status,a.appointment_count,a.completed_appointment_count,a.cancellation_count,
 a.no_show_count,a.completion_eligible_count,a.repair_order_quantity,a.payer_type,
 a.opened_at,a.promised_at,a.completed_at,
 to_char(a.opened_at::date,'YYYYMMDD')::integer opened_date_key,
 to_char(a.promised_at::date,'YYYYMMDD')::integer promised_date_key,
 to_char(a.completed_at::date,'YYYYMMDD')::integer completed_date_key,
 a.completed_on_time,a.turnaround_hours,a.labor_revenue,a.parts_revenue,a.discount_amount,
 a.service_revenue,a.service_cost,a.service_profit,a.service_cost_available,ro.order_status
 FROM analytics.vw_service_appointment_detail a
 LEFT JOIN analytics.fact_service ro ON ro.service_fact_key=a.service_fact_key""",
}
for table, role in [('DimSalesperson','Sales Consultant'),('DimServiceAdvisor','Service Advisor'),('DimTechnician','Service Technician')]:
    SOURCES[table] = f"SELECT employee_key,employee_id,first_name || ' ' || last_name AS employee_name,role,employment_status,hire_date,effective_from,effective_to,is_current FROM analytics.dim_employee WHERE role='{role}'"


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def serialize(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def literal(value):
    if isinstance(value, bool):
        value = str(value).lower()
    elif isinstance(value, str):
        value = "'" + value.replace("'", "''") + "'"
    else:
        value = str(value) + 'D'
    return {'expr': {'Literal': {'Value': value}}}


def color(value):
    return {'solid': {'color': literal(value)}}


def field(table, name, measure=False):
    return {'Measure' if measure else 'Column': {
        'Expression': {'SourceRef': {'Entity': table}}, 'Property': name}}


def projection(table, name, measure=False):
    return {'field': field(table, name, measure), 'queryRef': f'{table}.{name}', 'nativeQueryRef': name}


def formatting(**props):
    return [{'properties': props}]


def visual(name, visual_type, title, box, roles=None, objects=None):
    x,y,w,h = box
    config = {'visualType': visual_type, 'drillFilterOtherVisuals': True,
        'visualContainerObjects': {
            'title': formatting(show=literal(True), text=literal(title), fontSize=literal(12), fontColor=color('#152A42'), bold=literal(True)),
            'background': formatting(show=literal(True), color=color('#FFFFFF'), transparency=literal(0)),
            'border': formatting(show=literal(True), color=color('#E0E7EF'), radius=literal(6)),
            'general': formatting(altText=literal(title)),
        }}
    if roles:
        config['query'] = {'queryState': {role: {'projections': values} for role,values in roles.items()}}
    if objects:
        config['objects'] = objects
    return {'$schema': DEFINITION+'visualContainer/2.4.0/schema.json', 'name': name,
        'position': {'x':x,'y':y,'width':w,'height':h,'z':0,'tabOrder':0}, 'visual':config}


def build_report(project):
    report = project/'ExecutiveOverview.Report'
    definition = report/'definition'
    page_path = definition/'pages'/PAGE
    write_json(project/'ExecutiveOverview.pbip', {
        '$schema':'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json',
        'version':'1.0', 'artifacts':[{'report':{'path':'ExecutiveOverview.Report'}}],
        'settings':{'enableAutoRecovery':True}})
    write_json(report/'definition.pbir', {'$schema':BASE+'definitionProperties/2.0.0/schema.json','version':'4.0', 'datasetReference':{'byPath':{'path':'../ExecutiveOverview.SemanticModel'}}})
    write_json(definition/'version.json', {'$schema':DEFINITION+'versionMetadata/1.0.0/schema.json','version':'2.0.0'})
    write_json(report/'.platform', {'$schema':'https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json',
        'version':'2.0','metadata':{'type':'Report','displayName':'ExecutiveOverview'},
        'config':{'version':'2.0','logicalId':'d2737a23-71ed-4453-b461-c332146677c4'}})
    write_json(definition/'pages/pages.json', {'$schema':DEFINITION+'pagesMetadata/1.0.0/schema.json','pageOrder':[PAGE],'activePageName':PAGE})
    write_json(definition/'report.json', {'$schema':DEFINITION+'report/2.0.0/schema.json',
        'themeCollection':{'customTheme':{'name':'ExecutiveTheme','reportVersionAtImport':'5.55','type':'RegisteredResources'}},
        'resourcePackages':[{'name':'RegisteredResources','type':'RegisteredResources','items':[
            {'name':'ExecutiveTheme','path':'ExecutiveTheme.json','type':'CustomTheme'}]}]})
    write_json(report/'StaticResources/RegisteredResources/ExecutiveTheme.json', {
        'name':'Executive Overview','dataColors':['#0C7B83','#294C72','#D69934','#748DA6','#5E9971'],
        'background':'#F3F6FA','foreground':'#152A42','tableAccent':'#0C7B83',
        'textClasses':{'title':{'fontFace':'Segoe UI Semibold','fontSize':12},'label':{'fontFace':'Segoe UI','fontSize':10}}})
    visuals=[]
    def add(v):
        v['position']['z']=len(visuals)
        v['position']['tabOrder']=len(visuals)
        visuals.append(v)
    def text_box(name, content, box, size):
        v=visual(name,'textbox','',box,objects={'general':formatting(paragraphs=[{
            'textRuns':[{'value':content,'textStyle':{'fontFamily':'Segoe UI','fontSize':f'{size}pt','color':'#152A42'}}]}])})
        v['visual']['visualContainerObjects']['title']=formatting(show=literal(False))
        v['visual']['visualContainerObjects']['border']=formatting(show=literal(False))
        add(v)
    text_box('header','EXECUTIVE OVERVIEW  |  Automotive Sales & Service',(24,12,1232,48),22)
    slicers=[('date','Date','DimDate','full_date'),('dealer','Dealership','DimDealership','dealership_name'),
             ('brand','Brand','DimVehicle','brand'),('type','Vehicle Type','DimVehicle','vehicle_type')]
    for index,(name,title,table,column) in enumerate(slicers):
        add(visual('slicer_'+name,'slicer',title,(24+index*312,76,296,86),{'Values':[projection(table,column)]},
            {'data':formatting(mode=literal('Between' if name=='date' else 'Dropdown')),
             'selection':formatting(singleSelect=literal(False),selectAllCheckboxEnabled=literal(True))}))
    cards=[('Revenue','DimCustomer','Revenue'),('Units Sold','FactSales','Units Sold'),
           ('Gross Profit','FactSales','Gross Profit'),('Gross Margin','FactSales','Gross Margin %'),
           ('Service Revenue','FactService','Service Revenue'),('Inventory Value · as of date','FactInventory','Executive Inventory Value')]
    for index,(title,table,measure) in enumerate(cards):
        add(visual('kpi_'+str(index),'card',title,(24+index*208,182,192,108),{'Values':[projection(table,measure,True)]},
            {'labels':formatting(fontSize=literal(26),color=color('#0C7B83')),
             'categoryLabels':formatting(show=literal(False))}))
    def chart(name, kind, title, box, table, column, measures, sort='Ascending'):
        v=visual(name,kind,title,box,{'Category':[projection(table,column)],
            'Y':[projection(t,m,True) for t,m in measures]},
            {'categoryAxis':formatting(show=literal(True),fontSize=literal(10)),
             'valueAxis':formatting(show=literal(True),fontSize=literal(10)),
             'legend':formatting(show=literal(len(measures)>1)),
             'dataPoint':formatting(defaultColor=color('#0C7B83'))})
        v['visual']['query']['sortDefinition']={'sort':[{'field':field(table,column),'direction':sort}],'isDefaultSort':False}
        add(v)
    chart('sales_trend','lineChart','Monthly sales revenue and gross profit',(24,310,608,235),
        'DimDate','year_month',[('DimCustomer','Revenue'),('FactSales','Gross Profit')])
    chart('service_trend','columnChart','Monthly service revenue · completion date',(648,310,608,235),
        'DimDate','year_month',[('FactService','Service Revenue')])
    chart('brand_sales','barChart','Sales revenue by brand',(24,565,400,265),
        'DimVehicle','brand',[('DimCustomer','Revenue')])
    chart('dealer_sales','barChart','Sales revenue by dealership',(440,565,400,265),
        'DimDealership','dealership_name',[('DimCustomer','Revenue')])
    chart('inventory_age','columnChart','Inventory aging · units at as-of snapshot',(856,565,400,265),
        'FactInventory','aging_bucket',[('FactInventory','Executive Inventory Units')])
    add(visual('snapshot_label','card','Inventory snapshot used',(24,848,320,52),
        {'Values':[projection('FactInventory','Executive Snapshot Date',True)]},
        {'labels':formatting(fontSize=literal(12)), 'categoryLabels':formatting(show=literal(False))}))
    text_box('footer','Date filters sales / service periods; stock uses latest snapshot on or before period end. Amounts in source currency.',(360,848,896,52),10)
    targets=[v['name'] for v in visuals if v['visual']['visualType'] not in ('slicer','textbox')]
    write_json(page_path/'page.json', {'$schema':DEFINITION+'page/1.4.0/schema.json',
        'name':PAGE,'displayName':'Executive Overview','displayOption':'FitToPage','width':1280,'height':920,
        'objects':{'background':formatting(color=color('#F3F6FA'),transparency=literal(0))},
        'visualInteractions':[{'source':'slicer_'+s[0],'target':target,'type':'DataFilter'} for s in slicers for target in targets]})
    for v in visuals:
        write_json(page_path/'visuals'/v['name']/'visual.json',v)


def build_model(project, metadata):
    model_path=project/'ExecutiveOverview.SemanticModel'
    write_json(model_path/'definition.pbism', {'version':'1.0','settings':{}})
    tables=[]
    for name, columns in metadata.items():
        query=SOURCES[name].replace('"','""')
        types=[]
        model_columns=[]
        for column,oid in columns:
            if oid in (20,21,23): dtype,mtype='int64','Int64.Type'
            elif oid==1700: dtype,mtype='decimal','Currency.Type'
            elif oid in (700,701): dtype,mtype='double','type number'
            elif oid in (1082,1114,1184): dtype,mtype='dateTime','type date' if oid==1082 else 'type datetime'
            elif oid==16: dtype,mtype='boolean','type logical'
            else: dtype,mtype='string','type text'
            item={'name':column,'dataType':dtype,'sourceColumn':column,'summarizeBy':'none'}
            if column.endswith('_key') or name.startswith('Fact'):
                item['isHidden']=True
            if oid==1082:
                item.update(formatString='yyyy-MM-dd',annotations=[{'name':'UnderlyingDateTimeDataType','value':'Date'}])
            if name in ('DimDate','DimSnapshotDate') and column=='full_date': item['isKey']=True
            if column=='year_month': item['sortByColumn']='year_month_sort'
            if column=='aging_bucket': item['sortByColumn']='aging_bucket_sort'; item['isHidden']=False
            types.append('{"'+column+'", '+mtype+'}')
            model_columns.append(item)
        expression=[
            'let',
            f'    Source = if UseLocalSnapshot then Table.FromRecords(Json.Document(File.Contents(SnapshotFolder & "/{name}.json")))',
            f'        else Value.NativeQuery(PostgreSQL.Database(Server, Database, [CreateNavigationProperties=false]), "{query}", null, [EnableFolding=true]),',
            '    Typed = Table.TransformColumnTypes(Source, {'+', '.join(types)+'}, "en-US")',
            'in Typed']
        table={'name':name,'columns':model_columns,'partitions':[{'name':name,'mode':'import','source':{'type':'m','expression':expression}}]}
        if name in ('DimDate','DimSnapshotDate'): table['dataCategory']='Time'
        tables.append(table)
    dax=(ROOT/'powerbi/dax/measures.dax').read_text()
    definitions=re.findall(r'^\s*MEASURE (\w+)\[([^]]+)\]\s*=\s*(.*?)(?=^\s*MEASURE |^EVALUATE)',dax,re.M|re.S)
    by_name={t['name']:t for t in tables}
    for home,name,expression in definitions:
        expression=re.sub(r'//[^\n]*','',expression).strip()
        fmt='0.00%' if name in ('Gross Margin %','Completion Rate','Repeat Rate') else '#,0.00' if name in ('Revenue','ASP','Gross Profit','Inventory Value','Service Revenue','Average Repair Order','Customer Lifetime Value','Average Days in Inventory') else '#,0'
        by_name[home].setdefault('measures',[]).append({'name':name,'expression':expression,'formatString':fmt,
            'isHidden':name in ('Inventory Snapshot Key','Qualifying Interactions','Qualifying Customers')})
    for name,base in [('Executive Inventory Value','Inventory Value'),('Executive Inventory Units','Inventory Units')]:
        by_name['FactInventory']['measures'].append({'name':name,'expression':f'VAR AsOfDate = MAX(DimDate[full_date]) RETURN IF(NOT ISBLANK(AsOfDate), CALCULATE([{base}], REMOVEFILTERS(DimSnapshotDate), TREATAS({{AsOfDate}}, DimSnapshotDate[full_date])))',
            'formatString':'#,0.00' if 'Value' in name else '#,0'})
    by_name['FactInventory']['measures'].append({'name':'Executive Snapshot Date','expression':
        'VAR AsOfDate = MAX(DimDate[full_date]) VAR SnapshotKey = CALCULATE([Inventory Snapshot Key], REMOVEFILTERS(DimSnapshotDate), TREATAS({AsOfDate}, DimSnapshotDate[full_date])) RETURN IF(NOT ISBLANK(AsOfDate) && NOT ISBLANK(SnapshotKey), DATE(INT(SnapshotKey / 10000), INT(MOD(SnapshotKey, 10000) / 100), MOD(SnapshotKey, 100)))', 'formatString':'yyyy-MM-dd'})
    relationships=[]
    registry=(ROOT/'powerbi/documentation/star_schema.md').read_text()
    for one,col1,many,col2,active in re.findall(r'\| (Dim\w+)\.(\w+) \| (\w+)\.(\w+) \| (Yes|No) \|',registry):
        relationships.append({'name':f'{one}_{many}_{col2}','fromTable':many,'fromColumn':col2,
            'toTable':one,'toColumn':col1,'crossFilteringBehavior':'oneDirection',
            'fromCardinality':'many','toCardinality':'one','isActive':active=='Yes'})
    parameters=[('UseLocalSnapshot','true'),('SnapshotFolder',json.dumps(str((project/'local-data').resolve()).replace('\\','/'))),
        ('Server','"localhost:5432"'),('Database','"automotive_analytics"')]
    write_json(model_path/'model.bim', {'name':'ExecutiveOverview','compatibilityLevel':1600,
        'model':{'culture':'en-US','defaultPowerBIDataSourceVersion':'powerBI_V3',
            'annotations':[{'name':'PBI_TimeIntelligenceEnabled','value':'0'}],
            'expressions':[{'name':n,'kind':'m','expression':v} for n,v in parameters],
            'tables':tables,'relationships':relationships}})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild',action='store_true',help='Replace only the generated definition files; close Desktop first')
    args=parser.parse_args()
    if (PROJECT/'ExecutiveOverview.pbip').exists() and not args.rebuild:
        raise SystemExit('Project already exists; use --rebuild only to regenerate owned definitions.')
    engine=create_engine(ETLConfig.from_env().database_url,connect_args={'connect_timeout':10},isolation_level='REPEATABLE READ')
    metadata={}
    try:
        with engine.connect() as connection, connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            for gate in ['sql/analytics/data_quality.sql','powerbi/documentation/model_validation.sql']:
                rows=connection.execute(text((ROOT/gate).read_text())).mappings().all()
                if not rows or any(r['status']!='PASS' for r in rows): raise RuntimeError(f'Quality gate failed: {gate}')
            for table,query in SOURCES.items():
                result=connection.execute(text(query))
                metadata[table]=[(d.name,d.type_code) for d in result.cursor.description]
                data=[dict(row) for row in result.mappings()]
                if not data: raise RuntimeError(f'Empty source: {table}')
                path=PROJECT/'local-data'/f'{table}.json'
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(data,default=serialize),encoding='utf-8')
                print(f'{table}: {len(data):,} rows',flush=True)
        build_model(PROJECT,metadata)
        build_report(PROJECT)
    finally:
        engine.dispose()
    print(PROJECT/'ExecutiveOverview.pbip')


if __name__=='__main__': main()
