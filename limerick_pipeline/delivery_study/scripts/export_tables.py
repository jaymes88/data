import pandas as pd, json, numpy as np
T=pd.read_pickle('tables.pkl')
def fmt(v, dec=1):
    if v is None or (isinstance(v,float) and np.isnan(v)): return '–'
    if isinstance(v,(int,np.integer)): return f'{v:,}'
    if isinstance(v,float): return f'{int(v):,}' if float(v).is_integer() else f'{v:,.{dec}f}'
    if isinstance(v,pd.Timestamp): return v.strftime('%d/%m/%Y')
    return str(v)
pct=lambda v: '–' if pd.isna(v) else f'{int(v)}%'
out={}
t=T['2 Timeline by size']
out['timeline']=[['Size band (units)','Application to permission','Permission to start','Start to completion','Build rate (dpa)']]+[[r['Size band (units)'],f"{fmt(r['Approval: median'])} (n={r['Approval: n']})",f"{fmt(r['Grant to start: median'])} (n={r['Grant to start: n']})",f"{fmt(r['Start to completion: median'])} (n={r['Start to completion: n']})",fmt(r['Build rate (dpa): median'])] for _,r in t.iterrows()]
t=T['2b Timeline by sector']
out['sector_timeline']=[['Sector','Schemes','Units','Application to permission','Permission to start','Start to completion','Build rate (dpa)']]+[[r.Sector,fmt(r.Schemes),fmt(r.Units),fmt(r['Approval: median']),f"{fmt(r['Grant to start: median'])} (n={r['Grant to start: n']})",f"{fmt(r['Start to completion: median'])} (n={r['Start to completion: n']})",fmt(r['Build rate (dpa): median'])] for _,r in t.iterrows()]
t=T['5 Planning path']
out['path']=[['Planning path','Schemes','Median (yrs)','Lower quartile','Upper quartile']]+[[r['Planning path'],fmt(r.Schemes),fmt(r['Median approval (yrs)']),fmt(r.LQ),fmt(r.UQ)] for _,r in t.iterrows()]
def curve(name,key):
    t=T[name]
    return [[key]+[f'Within {k} yr' for k in range(1,6)]]+[[r[key]]+[('–' if pd.isna(r[f'Started within {k} yr (%)']) else f"{int(r[f'Started within {k} yr (%)'])}%")+f" ({int(r[f'n ({k} yr)'])})" for k in range(1,6)] for _,r in t.iterrows()]
out['started']=curve('3 Share started over time','Scheme size'); out['started_sector']=curve('3b Started over time by sector','Sector')
def impl(name,key,label):
    t=T[name]
    return [[label,'Schemes','Units permitted','Units started','% units started','Median permission to start (yrs)']]+[[r[key],fmt(r.Schemes),fmt(r['Units permitted']),fmt(r['Units started']),pct(r['Units started (%)']),fmt(r['Median grant to start (yrs)'])] for _,r in t.iterrows()]
out['lea']=impl('4a Implementation by LEA','lea','LEA'); out['route']=impl('4d Implementation by route','route','Route')
out['type']=impl('4c Implementation by type','dwelling_type','Type'); out['size']=impl('4b Implementation by size','band','Size band')
out['owner']=impl('4f Implementation by owner','owner','Owner'); out['nbhd_impl']=impl('4h Implementation by nbhd','nbhd','Neighbourhood')
t=T['12 Status by nbhd']
out['nbhd_status']=[['Neighbourhood','Schemes','Complete','Under construction','Not started (live)','Past expiry','Total units','Public share']]+[[r.Neighbourhood,fmt(r.Schemes),fmt(r['Complete']),fmt(r['Under construction']),fmt(r['Not started – permission live']),fmt(r['Not started – past expiry']),fmt(r['Total units']),pct(r['Public share (%)'])] for _,r in t.iterrows()]
t=T['6 Expiry of unstarted']; cols=[c for c in t.columns if c!='Expiry window']
out['expiry']=[['Expiry window']+cols]+[[r['Expiry window']]+[fmt(r[c]) for c in cols] for _,r in t.iterrows()]
t=T['9 Build rates']
out['build']=[['Group','Completed schemes','Median build period (yrs)','Median build rate (dpa)','Interquartile range (dpa)']]+[[r.Group,fmt(r['Completed schemes']),fmt(r['Median build period (yrs)']),fmt(r['Median build rate (dpa)']),f"{fmt(r['LQ dpa'])}–{fmt(r['UQ dpa'])}"] for _,r in t.iterrows()]
t=T['10 Barrier indicators']; out['barriers']=[['Indicator','Schemes / applications','Units']]+[[r.Indicator,fmt(r['Schemes / applications']),fmt(r.Units)] for _,r in t.iterrows()]
t=T['11 Data sources']; out['sources']=[['Item','Value']]+[[r.Item,fmt(r.Value)] for _,r in t.iterrows()]
w=T['7 Expiry watchlist']
w=w[(w.Units>=10)&w['Expiry window'].isin(['Already past expiry','Within 12 months','12–24 months'])].sort_values('Expiry')
area=lambda r: r.Neighbourhood if r.Neighbourhood not in ('Outside city neighbourhoods','Unknown') else r.LEA
out['watch']=[['Scheme (CIS heading)','Planning ref','Area','Owner','Units','Expiry']]+[[str(r.Scheme).split(' - ',1)[-1].strip(),str(r['Planning ref']) if pd.notna(r['Planning ref']) and str(r['Planning ref']) else '–',area(r),'Public' if str(r.Owner).startswith('Public') else 'Private',fmt(r.Units),r.Expiry.strftime('%d/%m/%Y') if pd.notna(r.Expiry) else '–'] for _,r in w.iterrows()]
u=pd.read_pickle('p8_undecided.pkl'); out['p8_undecided']=[[r.ref, f'{int(r.units)}'] for _,r in u.iterrows()]
json.dump(out,open('report_tables.json','w'),ensure_ascii=False,indent=1)
print({k:len(v) for k,v in out.items()})
