"""Limerick housing supply GeoPackage: land supply, permissions, delivery programmes, kept apart and linked by keys.

Layers
  sites                    council land register (city now, county when supplied)          key: site_id
  permissions              one row per counted scheme (points until boundaries arrive)     key: perm_id / planning_ref
  applications             every application incl. superseded/refused (audit trail)        key: planning_ref
  programmes (table)       social housing report, LDA, PBSA rows linked to permissions     key: programme_id -> perm_id
  non_new_supply (table)   Buy & Renew, remedial works (existing homes, not pipeline)
  site_reconciliation (table)   per site: capacity vs consented vs built vs residual
  off_register_permissions (view)  permissions not on a council site
  reference layers         neighbourhoods, EDs, LEAs, LDA public land, KPMG polygons, Clare schemes, register leads
  layer_guide (table)      what each layer is
"""
import os, re, json, sqlite3
import numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import shape

OUT = 'Limerick_Housing_Supply.gpkg'
ITM = 2157
EDGE_M = 50
if os.path.exists(OUT):
    os.remove(OUT)


def clean(df):
    df = df.copy()
    for c in df.columns:
        if c == 'geometry':
            continue
        if str(df[c].dtype).startswith('datetime'):
            df[c] = pd.to_datetime(df[c]).dt.date.astype('string')
        elif df[c].dtype == object:
            df[c] = df[c].map(lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else
                              (v.strftime('%Y-%m-%d') if hasattr(v, 'strftime') else (v if isinstance(v, (str, int, float, bool)) else str(v))))
    return df


def write(gdf, layer):
    clean(gdf).to_file(OUT, layer=layer, driver='GPKG')


def table(df, layer):
    # attribute-only table (no geometry)
    import pyogrio
    pyogrio.write_dataframe(pd.DataFrame(clean(df)).reset_index(drop=True), OUT, layer=layer, driver='GPKG')


# ------------------------------------------------------------------ sites (council land register)
S0 = gpd.read_file('in_sca/sca.gpkg').to_crs(ITM)
# some council sites are drawn as two separate polygons, each carrying the whole site's capacity: merge to one multipart site
S0 = S0.dissolve(by='rsca', aggfunc='first', as_index=False)
sites = gpd.GeoDataFrame({
    'site_id': S0.rsca.astype(int).map(lambda v: f'CITY-{v}'),
    'rsca': S0.rsca.astype('Int64'), 'scope': 'City', 'neighbourhood': S0.nbhd9, 'local_name': S0.neighbourhood,
    'register_status': S0.revised_status, 'landowner': S0.owner.replace({'EOI': 'Unknown'}).fillna('Unknown'), 'zoning': S0.joined_Zoning.str.strip(),
    'site_type': S0.joined_Type.str.strip(), 'density_band': S0.joined_Densities, 'area_ha': S0.area_app.round(3),
    'capacity_units': S0.cap.round(0), 'reconcile_action': S0.Action,
}, geometry=S0.geometry, crs=ITM)
# council file marks one site (rsca 12, Moyross) 'EOI' with no owner: folded into Unknown
sites.loc[S0.owner.eq('EOI').values, 'reconcile_action'] = 'Unchanged (council file landowner "EOI", owner not stated: shown as Unknown)'

# sites the council's 04/12/25 review removed with no recorded reason, checked and still developable (initial audit fid -> why)
REINSTATE = {56: 'Reinstated: removed in council review with no reason recorded; adjoining land built under 17/470, this remainder undeveloped',
             144: 'Reinstated: removed in council review with no reason recorded; council-owned, undeveloped, no permission. Irregular narrow shape, so the density-based capacity may overstate what fits'}
A0 = gpd.read_file('in_audit0/original.shp').to_crs(ITM)
A0 = A0[A0.fid.isin(REINSTATE)]
if len(A0):
    nb = gpd.read_file('nbh.geojson').to_crs(ITM)[['nbhd', 'geometry']]
    A0 = A0.assign(nbhd=gpd.sjoin(gpd.GeoDataFrame(geometry=A0.representative_point(), crs=ITM), nb, predicate='within').nbhd)
    sites = pd.concat([sites, gpd.GeoDataFrame({
        'site_id': A0.rsca.astype(int).map(lambda v: f'CITY-{v}'),
        'rsca': A0.rsca.astype('Int64'), 'scope': 'City', 'neighbourhood': A0.nbhd, 'local_name': A0.neighbourh,
        'register_status': A0.revised_st, 'landowner': A0.Ownership.fillna('Unknown'), 'zoning': A0.joined_Zon.str.strip(),
        'site_type': A0.joined_Typ.str.strip(), 'density_band': A0.joined_Den, 'area_ha': A0.joined_A_1.round(3),
        'capacity_units': A0.joined_C_3.round(0), 'reconcile_action': A0.fid.map(REINSTATE),
    }, geometry=A0.geometry, crs=ITM)], ignore_index=True)
    assert sites.site_id.is_unique

# ------------------------------------------------------------------ permissions (one row per counted scheme)
D = pd.read_pickle('delivery.pkl')
apps = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Applications', dtype={'CIS Reference': str})
beds = dict(zip(apps['Project Id'].astype(str), apps['Student Bedspaces']))
desc = dict(zip(apps['Project Id'].astype(str), apps['Register Description'].fillna('') + ' ' + apps['Project Heading'].fillna('')))
feed = pd.read_pickle('shcp_feed.pkl')
dup = apps[apps['Final Relationship'] == 'Duplicate'].set_index('Project Id')['Related Ref'].to_dict()
byref = dict(zip(D.ref, D.pid)) | dict(zip(D.register_ref, D.pid))
feed['pid'] = [byref.get(str(dup[p]), p) if p in dup else p for p in feed.pid]
sh_units = feed.groupby(feed.pid.astype(str)).units.sum().to_dict()

body = {'Private': 'Private', 'Public – local authority': 'Local authority', 'Public – approved housing body': 'Approved housing body',
        'Public – LDA': 'Land Development Agency'}
P = D[D.lat.notna()].copy()
P['perm_id'] = P.pid.astype(str)
P['delivery_body'] = P.owner.map(body)
P['student_bedspaces'] = P.perm_id.map(beds)
P['social_units_programme'] = P.perm_id.map(sh_units)
txt = P.perm_id.map(desc).fillna('').str.lower()


def tenure(r, t):
    if r.dwelling_type == 'Student':
        return 'Student (PBSA)'
    if r.delivery_body == 'Land Development Agency' or re.search(r'cost[- ]rental', t):
        return 'Affordable / cost rental'
    if re.search(r'\baffordable\b', t) and r.delivery_body != 'Private':
        return 'Affordable / cost rental'
    if r.delivery_body in ('Local authority', 'Approved housing body'):
        return 'Social'
    if pd.notna(r.social_units_programme) and r.social_units_programme > 0:
        return 'Mixed (market + social)'
    return 'Market (incl. Part V)'


P['tenure'] = [tenure(r, t) for (_, r), t in zip(P.iterrows(), txt)]
P['supply_type'] = np.where(txt.str.contains(r'change of use|conversion|convert|refurbish|retrofit|living georgian'), 'Change of use / conversion', 'New build')
P['delivery_mode'] = np.where(P.sh_mode.eq('Turnkey'), 'Turnkey purchase', np.where(P.delivery_body.eq('Private'), 'Private development', 'Direct build / own scheme'))
pts = gpd.GeoDataFrame(P, geometry=gpd.points_from_xy(P.lon, P.lat), crs=4326).to_crs(ITM)

# link to council sites: within, edge (<= 50m, point precision), off register; county = not yet assessed
city_mask = ~pts.nbhd.isin(['Outside city neighbourhoods', 'Unknown'])
j = gpd.sjoin(pts[['geometry']], sites[['site_id', 'geometry']], how='left', predicate='within')
j = j[~j.index.duplicated()]
pts['site_id'] = j.site_id
pts['site_match'] = np.where(pts.site_id.notna(), 'Within site', None)
need = pts.site_id.isna()
dists = pts[need].geometry.apply(lambda g: sites.distance(g))
near_id = dists.idxmin(axis=1).map(sites.site_id)
near_d = dists.min(axis=1)
pts.loc[need, 'dist_to_site_m'] = near_d.round(0)
edge = need & pts.index.isin(near_d[near_d <= EDGE_M].index)
pts.loc[edge, 'site_id'] = near_id[near_d <= EDGE_M]
pts.loc[edge, 'site_match'] = f'Edge (≤{EDGE_M} m) – check'
pts.loc[pts.site_match.isna() & city_mask, 'site_match'] = 'Off register'
pts.loc[pts.site_match.isna(), 'site_match'] = 'Not assessed (county sites pending)'
pts['on_register'] = pts.site_match.map({'Within site': 'Yes', f'Edge (≤{EDGE_M} m) – check': 'Possible', 'Off register': 'No'}).fillna('Not assessed')
pts['location_source'] = 'Planning register / KPMG / CIS'

perm_cols = ['perm_id', 'ref', 'register_ref', 'heading', 'units', 'student_bedspaces', 'band', 'dwelling_type', 'tenure',
             'delivery_body', 'delivery_mode', 'supply_type', 'social_units_programme', 'route', 'status', 'stage',
             'received', 'final_grant', 'expiry', 'start', 'start_source', 'completion', 'completion_source',
             'approval_yrs', 'grant_to_start_yrs', 'start_to_complete_yrs', 'build_rate_dpa',
             'site_id', 'site_match', 'on_register', 'dist_to_site_m', 'nbhd', 'lea', 'settlement', 'source',
             'relationship', 'rel_conf', 'sh_no', 'sh_programme', 'sh_stage', 'sh_quarter', 'barriers_noted']
permissions = pts[perm_cols + ['geometry']].rename(columns={'ref': 'planning_ref', 'heading': 'scheme', 'band': 'size_band',
                                                         'nbhd': 'neighbourhood', 'sh_no': 'dept_project_no',
                                                         'sh_programme': 'dept_programme', 'sh_stage': 'dept_stage', 'sh_quarter': 'dept_quarter'})
write(permissions, 'permissions')

# ------------------------------------------------------------------ applications (audit trail)
full = __import__('sources').load_full('lp.xlsx')[['Project Id', 'Latitude', 'Longitude']]
A = apps.merge(full, on='Project Id', how='left')
acols = ['Project Id', 'Site ID', 'CIS Reference', 'Project Heading', 'Address', 'CIS Stage', 'Application Date', 'CIS Decision Date',
         'Units', 'Dwelling Type', 'Final Relationship', 'Related Ref', 'Confidence', 'Counts?', 'Reporting Tier', 'Register Outcome',
         'Expiry incl. EoD', 'Check Result', 'Register Link', 'Source Dataset']
A = A[A.Latitude.notna()]
ag = gpd.GeoDataFrame(A[acols].rename(columns=lambda c: c.lower().replace(' ', '_').replace('?', '').replace('.', '')),
                      geometry=gpd.points_from_xy(A.Longitude, A.Latitude), crs=4326).to_crs(ITM)
ag = ag.rename(columns={'project_id': 'perm_id', 'cis_reference': 'planning_ref', 'site_id': 'cis_site_group'})
ag['perm_id'] = ag.perm_id.astype(str)
write(ag, 'applications')

# ------------------------------------------------------------------ programmes (table) and non-new supply (table)
X = pd.read_pickle('shcp_xwalk.pkl')
fmap = dict(zip(feed.no, feed.pid.astype(str)))
X['perm_id'] = X.no.map(fmap)
X['link_status'] = np.where(X.perm_id.notna(), 'Linked (vetted match)',
                            np.where(X.category.str.startswith('Not new'), 'Not new supply', 'Not linked – no confident match'))
prog = pd.DataFrame({
    'programme_id': 'DHLGH-' + X.no.astype(str), 'source': 'DHLGH Social Housing Construction Status Report Q1 2026',
    'programme': X.programme, 'delivery_body': np.where(X.programme.str.contains('CALF|CAS'), 'Approved housing body', 'Local authority'),
    'delivery_mode': np.where(X.programme.str.contains('Turnkey'), 'Turnkey purchase', np.where(X.programme.str.contains('Buy and Renew'), 'Buy and renew', 'Direct build / own scheme')),
    'tenure': 'Social', 'scheme': X.name, 'units': X.units, 'ahb': X.ahb, 'stage': X.stage, 'stage_quarter': X.stage_quarter,
    'perm_id': X.perm_id, 'link_status': X.link_status, 'match_category': X.category})
newprog = prog[~prog.match_category.str.startswith('Not new')].drop(columns='match_category')
lda = D[D.owner == 'Public – LDA']
newprog = pd.concat([newprog, pd.DataFrame({
    'programme_id': 'LDA-' + lda.ref, 'source': 'Land Development Agency (planning register / LDA announcements)', 'programme': 'LDA',
    'delivery_body': 'Land Development Agency', 'delivery_mode': 'Direct build / own scheme', 'tenure': 'Affordable / cost rental',
    'scheme': lda.heading, 'units': lda.units, 'stage': lda.status, 'perm_id': lda.pid.astype(str), 'link_status': 'Linked (planning ref)'})])
pb = __import__('sources').pbsa()
pb = pb[pb.existing == 'no']
pb_link = {r: str(p) for r, p in zip(D.ref, D.pid)}
newprog = pd.concat([newprog, pd.DataFrame({
    'programme_id': 'PBSA-' + pb.scheme.str.replace(r'\W+', '-', regex=True), 'source': 'PBSA schedule supplied for the study',
    'programme': 'Purpose-built student accommodation', 'delivery_body': 'Private', 'delivery_mode': 'Private development',
    'tenure': 'Student (PBSA)', 'scheme': pb.scheme, 'units': pb.beds, 'stage': pb.status.replace('', 'No permission'),
    'perm_id': [next((pb_link[r] for r in refs if r in pb_link), None) for refs in pb.refs],
    'link_status': ['Linked (planning ref)' if any(r in pb_link for r in refs) else ('Existing use (retention) – not pipeline' if 'retention' in s.lower() or s.endswith('2660543') else 'Not linked – no permission')
                    for refs, s in zip(pb.refs, pb.status.fillna(''))]})])
newprog['units_note'] = np.where(newprog.programme.eq('Purpose-built student accommodation'), 'Bedspaces', 'Dwellings')
table(newprog, 'programmes')
nonnew = prog[prog.match_category.str.startswith('Not new')].drop(columns=['perm_id', 'link_status', 'match_category'])
table(nonnew, 'non_new_supply')

# ------------------------------------------------------------------ site reconciliation (table)
pp = permissions[permissions.site_id.notna()]
w = pp[pp.site_match == 'Within site']
e = pp[pp.site_match != 'Within site']
grp = lambda d, st: d[d.status.isin(st)].groupby('site_id').units.sum()
rec = sites[['site_id', 'scope', 'neighbourhood', 'local_name', 'register_status', 'landowner', 'zoning', 'site_type', 'area_ha', 'capacity_units']].copy()
rec['complete_units'] = rec.site_id.map(grp(w, ['Complete'])).fillna(0)
rec['under_construction_units'] = rec.site_id.map(grp(w, ['Under construction'])).fillna(0)
rec['permitted_not_started_units'] = rec.site_id.map(grp(w, ['Not started – permission live', 'Stalled (CIS)'])).fillna(0)
rec['expired_not_started_units'] = rec.site_id.map(grp(w, ['Not started – past expiry'])).fillna(0)
rec['in_planning_units'] = rec.site_id.map(grp(w, ['In planning'])).fillna(0)
rec['edge_match_units'] = rec.site_id.map(e.groupby('site_id').units.sum()).fillna(0)
rec['consented_units'] = rec.complete_units + rec.under_construction_units + rec.permitted_not_started_units
rec['residual_capacity'] = (rec.capacity_units - rec.consented_units).clip(lower=0)
rec['consented_vs_capacity'] = np.where(rec.capacity_units > 0, (rec.consented_units / rec.capacity_units).round(2), np.nan)
rec['permissions_on_site'] = rec.site_id.map(w.groupby('site_id').size()).fillna(0).astype(int)
rec['flag'] = np.select([rec.consented_units > rec.capacity_units * 1.1, rec.edge_match_units > 0,
                         (rec.consented_units == 0) & rec.register_status.str.contains('Permission Granted|Complete', na=False)],
                        ['Consented above capacity', 'Edge match – check boundary', 'Register says permitted/complete but no permission linked'], '')
table(pd.DataFrame(rec.drop(columns='geometry', errors='ignore')), 'site_reconciliation')

# ------------------------------------------------------------------ reference layers
def geo(path, layer):
    fc = json.load(open(path))
    write(gpd.GeoDataFrame([f['properties'] for f in fc['features']], geometry=[shape(f['geometry']) for f in fc['features']], crs=4326).to_crs(ITM), layer)

write(sites, 'sites')
geo('nbh.geojson', 'ref_city_neighbourhoods')
geo('nbh_eds.geojson', 'ref_city_neighbourhood_eds')
geo('lea.geojson', 'ref_local_electoral_areas')
geo('lda_sites.geojson', 'ref_lda_public_land')
src = __import__('sources')
K = src._read_shp(src.KPMG_SHP)
kcmp = pd.read_pickle('kpmg_cmp.pkl').set_index('pid')['why'] if os.path.exists('kpmg_cmp.pkl') else {}
write(gpd.GeoDataFrame({'project_id': K['Project Id'].astype('int64'), 'planning_ref': K['Reference'], 'scheme': K['Project He'],
                        'stage': K['Detailed s'], 'units': K['Units'], 'planning_authority': K['Planning A'],
                        'kpmg_neighbourhood': K['Neighbourh'],
                        'in_our_pipeline': K['Project Id'].astype('int64').map(lambda p: 'Yes' if str(p) in set(permissions.perm_id) else (kcmp.get(p, 'No') if len(kcmp) else 'No'))},
                       geometry=list(K['_geom_itm']), crs=ITM), 'ref_kpmg_audit_polygons')
reg = pd.read_pickle('reg.pkl'); reg['ref'] = reg.ApplicationNumber.astype(str)
N = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Register Not in CIS', dtype={'Register Ref': str})
N = N.merge(reg.drop_duplicates('ref')[['ref', 'lat', 'lon']], left_on='Register Ref', right_on='ref', how='left').dropna(subset=['lat'])
write(gpd.GeoDataFrame(N.drop(columns=['ref', 'lat', 'lon']).rename(columns=lambda c: c.lower().replace(' ', '_').replace('(', '').replace(')', '')),
                       geometry=gpd.points_from_xy(N.lon, N.lat), crs=4326).to_crs(ITM), 'ref_register_leads')

# ------------------------------------------------------------------ guide + views
guide = pd.DataFrame([
    ('sites', 'Layer', 'Council land register sites (city). County sites to be added with scope = County.', 'site_id'),
    ('permissions', 'Layer', 'One row per counted residential scheme. Tenure, delivery body and supply type are fields – filter or style on them rather than splitting layers.', 'perm_id'),
    ('applications', 'Layer', 'Every application including superseded, refused, duplicate and not-counted records. Audit trail for permissions.', 'planning_ref'),
    ('programmes', 'Table', 'Delivery programme records (DHLGH social housing report, LDA, PBSA) linked to permissions by perm_id where a confident match exists.', 'programme_id -> perm_id'),
    ('non_new_supply', 'Table', 'Buy & Renew and remedial works from the DHLGH report. Existing homes – not part of the pipeline.', 'programme_id'),
    ('site_reconciliation', 'Table', 'Per council site: capacity, complete, under construction, permitted not started, expired, in planning, residual. Join to sites on site_id.', 'site_id'),
    ('off_register_permissions', 'View', 'Permissions in the city not on a council site (site_match = Off register).', 'perm_id'),
    ('edge_match_permissions', 'View', f'Permissions within {EDGE_M} m of a council site but not inside it – point precision; resolve with planning boundaries.', 'perm_id'),
    ('ref_*', 'Layers', 'Reference only: neighbourhoods, EDs, LEAs, LDA public land, KPMG audit polygons, register leads not in CIS.', ''),
], columns=['layer', 'type', 'description', 'key'])
table(guide, 'layer_guide')

con = sqlite3.connect(OUT)
cols = [r[1] for r in con.execute('PRAGMA table_info(permissions)')]
gcol = con.execute("SELECT column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns WHERE table_name='permissions'").fetchone()
for view, where in [('off_register_permissions', "site_match = 'Off register'"), ('edge_match_permissions', "site_match LIKE 'Edge%'")]:
    con.execute(f'CREATE VIEW {view} AS SELECT {", ".join(cols)} FROM permissions WHERE {where}')
    con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) VALUES (?, 'features', ?, ?)", (view, view, gcol[2]))
    con.execute('INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) VALUES (?, ?, ?, ?, 0, 0)', (view, gcol[0], gcol[1], gcol[2]))
con.commit(); con.close()

import pyogrio
for l in pyogrio.list_layers(OUT):
    print(l[0], l[1], pyogrio.read_info(OUT, layer=l[0])['features'])
print(permissions.site_match.value_counts().to_dict())
print(permissions.tenure.value_counts().to_dict())
print(permissions.delivery_body.value_counts().to_dict())
print(permissions.supply_type.value_counts().to_dict())
print(newprog.link_status.value_counts().to_dict())
print(rec.flag.value_counts().to_dict())
print('capacity', rec.capacity_units.sum(), 'consented', rec.consented_units.sum(), 'residual', rec.residual_capacity.sum())
