"""Reconcile CSO BHQ17 (units for which permission granted, Limerick) with the planning register and the tracker.
Writes cso_recon.pkl: yearly table + the list of register grants not in the tracker."""
import re, pandas as pd, geopandas as gpd

c = pd.read_csv('in_cso/bhq17.csv')
c = c[c.Statistic == 'Units for which Permission Granted'].melt(id_vars=['Statistic', 'County', 'Type of Dwelling', 'UNIT'], var_name='q', value_name='v')
c['yr'] = c.q.str[:4].astype(int)
cso = c.pivot_table(index='yr', columns='Type of Dwelling', values='v', aggfunc='sum')
cso = cso.rename(columns={'One off houses': 'CSO one-off houses', 'Multi development houses': 'CSO scheme houses', 'Apartments': 'CSO apartments'})
cso = cso[['CSO one-off houses', 'CSO scheme houses', 'CSO apartments']]
cso['CSO total'] = cso.sum(axis=1)
quarters = c.groupby('yr').q.nunique()

r = pd.read_pickle('reg.pkl')
r['ref'] = r.ApplicationNumber.astype(str).str.strip()
r['n'] = pd.to_numeric(r.NumResidentialUnits, errors='coerce').fillna(0)
r['dd'] = pd.to_datetime(r.DecisionDate, errors='coerce')
r['yr'] = r.dd.dt.year
r['q'] = r.yr.astype('Int64').astype(str) + 'Q' + r.dd.dt.quarter.astype('Int64').astype(str)
a = gpd.read_file('Limerick_Housing_Supply.gpkg', layer='applications')
p = gpd.read_file('Limerick_Housing_Supply.gpkg', layer='permissions')
T = set(a.planning_ref.astype(str)) | set(p.planning_ref.astype(str)) | set(p.register_ref.dropna().astype(str))
g = r[r.Decision.isin(['CONDITIONAL', 'UNCONDITIONAL']) & r.ApplicationType.isin(['PERMISSION', 'PERMISSION CONSEQUENT', 'OUTLINE PERMISSION']) & (r.n > 0)].copy()
# SHDs appear in the council register as yy + ABP case no.
shd = g.ref.str.fullmatch(r'\d{2}3\d{5}') & ('ABPREF' + g.ref.str[-6:]).isin(T)
g['in_tracker'] = g.ref.isin(T) | shd
desc = g.DevelopmentDescription.fillna('')
g['cat'] = 'In tracker'
nt = ~g.in_tracker
g.loc[nt & (g.n == 1), 'cat'] = 'Single dwelling (one-off)'
g.loc[nt & g.n.between(2, 9), 'cat'] = 'Small scheme (2–9)'
big = nt & (g.n >= 10)
g.loc[big & desc.str.contains(r'modif|alteration|amend|change of house type|revis', case=False), 'cat'] = '10+: amendment to earlier permission'
g.loc[big & (g.cat == 'In tracker'), 'cat'] = '10+: not in tracker (mostly pre-2019 or completed before CIS window)'
last = int(g.yr.max())
qs = set(c[c.yr == last].q)
g = g[(g.yr < last) | g.q.isin(qs)]          # same quarters as CSO for the part year
REG = g.pivot_table(index='yr', columns='cat', values='n', aggfunc='sum').fillna(0)
order = ['Single dwelling (one-off)', 'Small scheme (2–9)', '10+: amendment to earlier permission', '10+: not in tracker (mostly pre-2019 or completed before CIS window)', 'In tracker']
REG = REG.reindex(columns=order, fill_value=0)
REG.columns = ['Register: ' + x for x in REG.columns]
REG['Register total'] = REG.sum(axis=1)
Y = cso.join(REG, how='left').fillna(0)
Y['quarters'] = quarters
Y['CSO minus register'] = Y['CSO total'] - Y['Register total']
# register limited to the same quarters as CSO for the last (part) year
pd.to_pickle({'years': Y, 'grants': g, 'last_quarters': sorted(qs)}, 'cso_recon.pkl')
pd.set_option('display.width', 250); pd.set_option('display.max_columns', 20)
print(Y.round(0))
print(g[g.cat.str.startswith('10+: not')].sort_values('n', ascending=False)[['ref', 'yr', 'n', 'DevelopmentDescription']].head(12).to_string(max_colwidth=80))
