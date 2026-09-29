import pandas as pd, numpy as np, re
pd.set_option('display.width',260); pd.set_option('display.max_colwidth',60)
s=pd.read_excel('shcp.xlsx',sheet_name='Projects')
ST=list(s.columns[6:])
s['stage']=s[ST].apply(lambda r: next((c for c in reversed(ST) if pd.notna(r[c])),None),axis=1)
s['stage_q']=s[ST].apply(lambda r: next((r[c] for c in reversed(ST) if pd.notna(r[c])),None),axis=1)
s['newbuild']=~s['Funding Programme'].str.contains('Buy and Renew|Remedial')
D=pd.read_pickle('delivery.pkl')
app=pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx',sheet_name='Applications',dtype={'CIS Reference':str})
reg=pd.read_pickle('reg.pkl'); reg['ref']=reg.ApplicationNumber.astype(str); R=reg.drop_duplicates('ref').set_index('ref')
STOP=set('limerick co county city road street st no units unit phase lot the of and at in park avenue ave rd site sites development housing scheme new house houses dwellings apartments'.split())
def toks(t):
    t=re.sub(r"[’'`]", '', str(t).lower()); t=re.sub(r'[^a-z0-9 ]',' ',t)
    return {w for w in t.split() if len(w)>2 and w not in STOP and not w.isdigit()}
# candidate text per scheme: heading + address (CIS) + register address
full=pd.read_excel('lp.xlsx',sheet_name='Full Project Pipeline').set_index('Project Id')
def addr(pid):
    if pid in full.index:
        f=full.loc[pid]; return ' '.join(str(f[f'Project Site Address Line {i}']) for i in range(1,6) if pd.notna(f[f'Project Site Address Line {i}']))
    return ''
D['text']=[ ' '.join([str(h), addr(p), str(R.loc[r,'DevelopmentAddress']) if r in R.index else '']) for h,p,r in zip(D.heading,D.pid,D.register_ref)]
D['tk']=D.text.map(toks)
rows=[]
for _,x in s[s.newbuild].iterrows():
    tk=toks(x['Scheme / Project Name'])
    best=None
    for i,d in D.iterrows():
        ov=len(tk & d.tk)
        if not ov: continue
        score=ov/ max(1,len(tk))
        u=d.units; ue= pd.notna(u) and x.Units>0 and abs(u-x.Units)<=max(2,0.25*max(u,x.Units))
        sc=score+(0.5 if ue else 0)
        if best is None or sc>best[0]: best=(sc,i,ov,ue)
    rows.append(dict(no=x['Project No.'],name=x['Scheme / Project Name'],units=x.Units,prog=x['Funding Programme'],stage=x.stage,q=x.stage_q,
        score=best[0] if best else 0, match=D.loc[best[1],'heading'] if best else '', munits=D.loc[best[1],'units'] if best else np.nan,
        mref=D.loc[best[1],'ref'] if best else '', mowner=D.loc[best[1],'owner'] if best else '', ue=best[3] if best else False, idx=best[1] if best else None))
M=pd.DataFrame(rows)
M['mtext']=[D.loc[int(i),'text'][:80] if pd.notna(i) else '' for i in M.idx]
M.to_pickle('shcp_match.pkl')
print(len(M), (M.score>=1.0).sum(), ((M.score>=0.5)&M.ue).sum())
print(M.sort_values('score',ascending=False)[['no','name','units','prog','stage','score','match','munits','mowner']].to_string())
