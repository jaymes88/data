import json, urllib.request, urllib.parse, pandas as pd, time
base="https://services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/IrishPlanningApplications/FeatureServer/0/query"
rows=[];off=0
while True:
    q=urllib.parse.urlencode(dict(where="PlanningAuthority like 'Limerick%'",outFields="*",returnGeometry="true",outSR=4326,resultOffset=off,resultRecordCount=2000,orderByFields="OBJECTID",f="json"))
    d=json.load(urllib.request.urlopen(base+"?"+q,timeout=120))
    fs=d.get('features',[])
    for f in fs:
        a=f['attributes']; g=f.get('geometry') or {}
        a['lon']=g.get('x'); a['lat']=g.get('y'); rows.append(a)
    print(off,len(fs),d.get('exceededTransferLimit'))
    if not fs or not d.get('exceededTransferLimit'): break
    off+=len(fs)
df=pd.DataFrame(rows)
for c in [c for c in df.columns if c.endswith('Date') or c=='ETL_DATE']:
    df[c]=pd.to_datetime(df[c],unit='ms',errors='coerce')
df.to_pickle('reg.pkl'); print(df.shape); print(df.PlanningAuthority.value_counts())
