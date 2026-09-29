import pandas as pd, numpy as np, re
exec(open('shcp_match.py').read().split("rows=[]")[0])
TOWNS=['abbeyfeale','adare','ardagh','askeaton','athea','ballylanders','bruff','broadford','caherconlish','cappamore','castleconnell','croom','doon','feenagh','glin','hospital','kilfinane','kilmallock','kilmeedy','knocklong','mountcollins','mungret','newcastle west','newcastlewest','pallaskenry','patrickswell','rathkeale','annacotty','castletroy','raheen','dooradoyle','moyross','southill','caherdavin','corbally','thomondgate','garryowen','singland','kennedy park','galbally','foynes','kildimo','murroe']
norm=lambda t: re.sub(r"[’'`]",'',str(t).lower()).replace('newcastlewest','newcastle west').replace('castleconnel ','castleconnell ')
out=[]
for _,x in s.iterrows():
    base=dict(no=x['Project No.'],name=x['Scheme / Project Name'],units=x.Units,programme=x['Funding Programme'],ahb=x['Approved Housing Body'],stage=x.stage,stage_quarter=x.stage_q)
    if not x.newbuild:
        out.append({**base,'category':'Not new supply (buy and renew / remedial)'}); continue
    nm=norm(x['Scheme / Project Name']); tk=toks(nm)
    towns=[t for t in TOWNS if t in nm]
    cands=[]
    for i,d in D.iterrows():
        tx=norm(d.text)
        if towns and not all(t in tx for t in towns): continue
        ov=len(tk & d.tk)
        if not ov: continue
        u=d.units; ue= pd.notna(u) and x.Units>0 and abs(u-x.Units)<=max(2,0.25*max(u,x.Units))
        cands.append((ov/len(tk)+(0.5 if ue else 0), ov, ue, i))
    if not cands:
        out.append({**base,'category':'Not in tracker'}); continue
    sc,ov,ue,i=max(cands)
    d=D.loc[i]
    if ue and ov>=2 or (ue and sc>=1.4):
        cat='Matched'
    elif pd.notna(d.units) and d.units>x.Units and ov>=1 and sc>=0.75 and x.Units>=3:
        cat='Part of larger scheme (turnkey / phase)'
    elif x.Units<=2:
        cat='Not in tracker'
    else:
        cat='Possible match – review'
    out.append({**base,'category':cat,'tracker_ref':d.ref,'tracker_site':d.site,'tracker_scheme':d.heading,'tracker_units':d.units,
                'tracker_status':d.status,'tracker_owner':d.owner,'tracker_nbhd':d.nbhd,'match_score':round(sc,2)})
X=pd.DataFrame(out)
X.to_pickle('shcp_xwalk.pkl')
print(X.groupby('category').agg(rows=('units','size'),units=('units','sum')))
nb=X[X.category!='Not new supply (buy and renew / remedial)']
print(pd.crosstab(nb.category,nb.stage))
m=X[X.category=='Matched']
print(pd.crosstab(m.stage,m.tracker_status))
print(m.tracker_owner.value_counts())
for c in ['Possible match – review','Part of larger scheme (turnkey / phase)']:
    print('==',c); print(X[X.category==c][['name','units','tracker_scheme','tracker_units']].to_string())
