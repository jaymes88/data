import sys, shapefile, pandas as pd, numpy as np
pd.set_option('display.width', 260); pd.set_option('display.max_colwidth', 60)
r = shapefile.Reader(sys.argv[1])
K = pd.DataFrame([x.as_dict() for x in r.records()])
K['pid'] = K['Project Id'].astype('Int64'); K['ref'] = K['Reference'].astype(str).str.strip()
full = pd.read_excel('lp.xlsx', sheet_name='Full Project Pipeline', dtype={'Reference': str})
lu = pd.read_excel('lp.xlsx', sheet_name='Latest Export Deduplicated') if False else None
app = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Applications', dtype={'CIS Reference': str})
D = pd.read_pickle('delivery.pkl')
reg = pd.read_pickle('reg.pkl'); reg['ref'] = reg.ApplicationNumber.astype(str); R = reg.drop_duplicates('ref').set_index('ref')
fullpid = set(full['Project Id']); apppid = app.set_index('Project Id'); Dpid = set(D.pid.astype(str))
fullref = set(full.Reference.dropna().str.strip()); Dref = set(D.ref.dropna()) | set(D.register_ref.dropna())
rows = []
for _, k in K.iterrows():
    pid = int(k.pid); ref = k.ref
    if str(pid) in Dpid or ref in Dref:
        why = 'In our study'
    elif pid in apppid.index:
        a = apppid.loc[pid]
        why = f"In tracker, not counted: {a['Final Relationship']}" + (f" ({a['Related Ref']})" if isinstance(a['Related Ref'], str) else '') + (f" – register {a['Register Outcome']}" if a['Final Relationship'] == 'Not live' else '')
        if a['Included in Pipeline'] == 'No':
            why = 'In tracker, excluded as non-residential: ' + str(a['Exclusion Reason'])
    elif ref in fullref:
        why = 'Same planning ref in tracker under another CIS project id'
    else:
        why = 'Not in our CIS exports'
    o = R.loc[ref] if ref in R.index else None
    rows.append(dict(pid=pid, ref=ref, heading=k['Project He'], stage=k['Detailed s'], units=k['Units'], la=k['Planning A'],
                     app_date=k['Applicatio'], last_upd=k['Last Updat'], promoter=k['Promoter'], nbhd=k['Neighbourh'], why=why,
                     reg_outcome=(o.ApplicationStatus + '/' + str(o.Decision)) if o is not None else ('not in register' if ref else ''),
                     reg_received=o.ReceivedDate.date() if o is not None and pd.notna(o.ReceivedDate) else None))
C = pd.DataFrame(rows)
C.to_pickle('kpmg_cmp.pkl')
print(C.why.str.split(':').str[0].value_counts())
print(C[C.why != 'In our study'][['pid', 'ref', 'heading', 'stage', 'units', 'la', 'app_date', 'last_upd', 'why', 'reg_outcome']].to_string())
