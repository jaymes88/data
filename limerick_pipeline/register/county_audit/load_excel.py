import pandas as pd, re
def num(v):
    m=re.findall(r'\d+(?:\.\d+)?',str(v)) if pd.notna(v) else []
    return float(m[0]) if m else float('nan')
out=[]
for sh in ['Key Town','Towns','Large Villages']:
    d=pd.read_excel('in_sca2/xl/sca.xlsx',sheet_name=sh,header=1)
    d=d.rename(columns=lambda c: str(c).strip())
    d=d[d['Settlement'].notna() & d['SCA Site No.'].notna()].copy()
    d['sheet']=sh; d['xl_row']=d.index+3; out.append(d)
A=pd.concat(out,ignore_index=True)
pick=lambda pat: A[[c for c in A.columns if re.search(pat,c)]].bfill(axis=1).iloc[:,0]
S=pd.DataFrame(dict(sheet=A.sheet,xl_row=A.xl_row,settlement=A.Settlement.str.strip(),site=A['SCA Site No.'].astype(str).str.strip(),
  zoning=A.Zoning.astype(str).str.strip(),area_txt=A['Site Area (ha.)'].astype(str),area=A['Site Area (ha.)'].map(num),
  density=A.Density.map(num),capacity=pd.to_numeric(A.Capacity,errors='coerce'),stype=A['Infill/ Brownfield/ Greenfield'].astype(str).str.strip(),
  tier=A['Updated Tier'],ww=pick('Wastewater'),permission=A['Permission Granted/ Sought'],units_perm=A['No. of Units Permitted'],
  status=pick(r'^Site Status'),note=pick(r'^Notes?$')))
S.to_csv('in_sca2/xl_sites.csv',index=False)
