"""Standardise the council's settlement capacity audit polygons (DevPlan_Variation_Settlement_RSCA_23_10_26.gpkg, one layer
per settlement) and check them against the council Excel (May 2026).

Each polygon gets: settlement, site_no (as the council numbers it, e.g. 5a, 1.1, 11d), parent_site (the Excel row it belongs
to), and the Excel figures. Where several polygons belong to one Excel site (split sites, or Askeaton 2 & 3 & 4) the site's
capacity is shared between them by area. Sites with no Excel row get area x the town's average density for that type of site.
Writes in_county/rsca26_sites.gpkg and in_county/rsca26_checks.csv.
"""
import re, sqlite3
import numpy as np, pandas as pd, geopandas as gpd

ITM = 2157
F = 'in_rsca26/rsca26.gpkg'
X = pd.read_csv('in_sca2/xl_sites.csv')
X['site'] = X.site.astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
num = lambda v: float(re.findall(r'\d+(?:\.\d+)?', str(v))[0]) if pd.notna(v) and re.findall(r'\d+(?:\.\d+)?', str(v)) else np.nan
X['dn'] = X.density.map(num)

TOWN = {'abbeyfeale': 'Abbeyfeale', 'askeaton': 'Askeaton', 'caherconlish': 'Caherconlish', 'cappamore': 'Cappamore',
        'castleconnell': 'Castleconnell', 'croom': 'Croom', 'kilmallock': 'Kilmallock', 'newcastlewest': 'Newcastle West',
        'rathkeale': 'Rathkeale'}
SITE_COLS = ['Site Number', 'Site No.', 'site_number', 'Site_number', 'rsca_number', 'site_numbe']

def cls(z):
    z = str(z).lower()
    if 'centre' in z: return 'centre'
    if 'servic' in z: return 'serviced'
    return 'resi'

rows = []
for (t,) in sqlite3.connect(F).execute("select table_name from gpkg_contents where data_type='features'"):
    town = TOWN[t.split('_')[0]]
    g = gpd.read_file(F, layer=t).to_crs(ITM)
    sc = next(c for c in SITE_COLS if c in g.columns and g[c].notna().all())
    sub = g['site'] if town == 'Kilmallock' else g[sc]      # Kilmallock numbers the parts of a site 1.1, 1.2 in 'site'
    for i, r in g.iterrows():
        s = str(sub[i]).strip()
        s = re.sub(r'\.0$', '', s)
        zon = next((r[c] for c in ['join_Zoning', 'Zoning', 'Zone_Orig'] if c in g.columns and pd.notna(r[c])), None)
        rows.append(dict(settlement=town, site_no=s, layer=t, zoning_file=zon, tier_file=r.get('TAZ_Tier'),
                         status_file=r.get('join_Site Status (July 26)'), geometry=r.geometry))
G = gpd.GeoDataFrame(rows, crs=ITM)
G['geometry'] = G.geometry.make_valid().buffer(0)
# one parcel per council site number: pieces drawn under the same number are joined (Newcastle West 5, Kilmallock 3);
# Newcastle West's four '11d' pieces are the whole of site 11 (11A-11D together = 30.5 ha in the Excel)
G.loc[G.settlement.eq('Newcastle West') & G.site_no.str.lower().eq('11d'), 'site_no'] = '11'
G['pieces'] = G.groupby(['settlement', 'site_no']).site_no.transform('size')
G = G.dissolve(by=['settlement', 'site_no'], aggfunc={'layer': 'first', 'zoning_file': 'first', 'tier_file': 'first',
                                                     'status_file': 'first', 'pieces': 'first'}).reset_index()
G['ha'] = G.area / 1e4

# parent Excel site for each polygon
def parent(town, s):
    xs = set(X.loc[X.settlement.eq(town), 'site'])
    if s in xs: return s
    m = re.match(r'^(\d+)', s)
    base = m.group(1) if m else s
    if base in xs and (re.match(r'^\d+[a-zA-Z]$', s) or re.match(r'^\d+\.\d+$', s)):
        return base                                               # 5a -> 5, 1.1 -> 1, 11d -> 11
    for x in xs:                                                  # combined rows such as '2 & 3 & 4'
        if '&' in x and base in [p.strip() for p in x.split('&')]:
            return x
    return None
G['parent_site'] = [parent(t, s) for t, s in zip(G.settlement, G.site_no)]
XI = X.set_index(['settlement', 'site'])
G['xl_area'] = [XI.loc[(t, p), 'area'] if isinstance(p, str) else np.nan for t, p in zip(G.settlement, G.parent_site)]
G['xl_capacity'] = [XI.loc[(t, p), 'capacity'] if isinstance(p, str) else np.nan for t, p in zip(G.settlement, G.parent_site)]
G['xl_density'] = [XI.loc[(t, p), 'density'] if isinstance(p, str) else None for t, p in zip(G.settlement, G.parent_site)]
for c in ['zoning', 'tier', 'ww', 'permission', 'status', 'note', 'stype', 'units_perm']:
    G['xl_' + c] = [XI.loc[(t, p), c] if isinstance(p, str) else None for t, p in zip(G.settlement, G.parent_site)]
# Newcastle West site 11 carries no capacity on its own row in the Excel (only its parts 11A-11D do, as areas): use area x density
nw11 = G.settlement.eq('Newcastle West') & G.parent_site.eq('11')
G.loc[nw11, 'xl_capacity'] = G.loc[nw11, 'xl_area'] * 35

# share each Excel site's capacity between its polygons by area
grp = G.groupby(['settlement', 'parent_site']).ha.transform('sum')
G['parts'] = G.groupby(['settlement', 'parent_site']).ha.transform('size')
G['Capacity'] = np.where(G.parent_site.notna(), (G.xl_capacity * G.ha / grp).round(1), np.nan)
G['cap_basis'] = np.where(G.parent_site.notna(),
                          np.where(G.parts > 1, 'Council capacity (Excel May 2026), shared between the site’s ' + G.parts.astype(str) + ' polygons by area',
                                   'Council capacity (Excel May 2026)'), '')
# no Excel row: area x the town's average density for that type of site
X['cls'] = X.zoning.map(cls)
town_d = X.groupby(['settlement', 'cls']).dn.median().to_dict()
for i, r in G[G.parent_site.isna()].iterrows():
    c_ = cls(r.zoning_file) if r.zoning_file and cls(r.zoning_file) in ('serviced', 'centre') else 'resi'
    d = town_d.get((r.settlement, c_), town_d.get((r.settlement, 'resi')))
    G.at[i, 'Capacity'] = round(r.ha * d, 1)
    G.at[i, 'Densities'] = f'{d:g}'
    G.at[i, 'cap_basis'] = f'Area x town average density for {c_} sites in the council audit ({d:g}/ha): site not in the Excel'
G['Densities'] = np.where(G.parent_site.notna(), G.xl_density.astype(str), G.get('Densities'))

# ---------------------------------------------------------------- checks
chk = []
def add(level, what, town, site, detail):
    chk.append(dict(level=level, check=what, settlement=town, site_no=site, detail=detail))
for t in G.settlement.unique():
    xs = X[X.settlement.eq(t) & X.area.fillna(0).gt(0)]
    have = set(G.loc[G.settlement.eq(t), 'parent_site'].dropna())
    for s in xs.site:
        drawn_as_parent = bool(re.match(r'^\d+[A-Z]$', s)) and re.match(r'^\d+', s).group(0) in have
        if s not in have and not drawn_as_parent:
            if True:
                add('Missing', 'Excel site with no polygon in the council file', t, s, f'{xs.loc[xs.site.eq(s), "area"].iloc[0]} ha in the Excel')
for (t, p), g in G[G.parent_site.notna()].groupby(['settlement', 'parent_site']):
    a, x = g.ha.sum(), g.xl_area.iloc[0]
    if pd.notna(x) and x > 0 and abs(a / x - 1) > 0.2:
        add('Area', 'polygon area differs from the Excel area by more than 20%', t, p, f'polygons {a:.2f} ha vs Excel {x:g} ha')
    if len(g) > 1 or g.pieces.max() > 1:
        add('Info', 'Excel site drawn as several pieces (capacity shared by area where numbered separately)', t, p,
            ', '.join(g.site_no) + f' = {a:.2f} ha (Excel {x:g} ha)')
for _, r in G[G.parent_site.isna()].iterrows():
    add('New', 'site not in the Excel (capacity from town average density)', r.settlement, r.site_no, f'{r.ha:.2f} ha, {r.zoning_file or "zoning not given"}')
sj = gpd.sjoin(G[['settlement', 'site_no', 'geometry']], G[['settlement', 'site_no', 'geometry']], predicate='intersects')
sj = sj[sj.index < sj.index_right]
for i, r in sj.iterrows():
    ov = G.at[i, 'geometry'].intersection(G.at[r.index_right, 'geometry']).area
    if ov > 100:
        add('Overlap', 'two council polygons overlap', r.settlement_left, f'{r.site_no_left} / {r.site_no_right}', f'{ov / 1e4:.2f} ha')
add('Info', 'geometry', 'all', '', f'{len(G)} polygons, all valid after repair: {bool(G.is_valid.all())}; CRS EPSG:2157')
C = pd.DataFrame(chk)
G.to_file('in_county/rsca26_sites.gpkg', layer='sites', driver='GPKG')
C.to_csv('in_county/rsca26_checks.csv', index=False)
pd.set_option('display.width', 250, 'display.max_colwidth', 90, 'display.max_rows', 200)
print(G.groupby('settlement').agg(polygons=('site_no', 'size'), ha=('ha', 'sum'), cap=('Capacity', 'sum'), new=('parent_site', lambda s: s.isna().sum())).round(1))
print(C.to_string())
