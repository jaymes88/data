"""Limerick housing land register: one parcel layer for all housing land, one permissions table, units counted once.

parcels             every piece of housing land: council audit parcels (our updated version) plus parcels for residential
                    consents outside the audit. Parcels do not overlap. Holds the land facts and the council capacity estimate.
parcel_permissions  one row per counted permission, each linked to exactly one parcel (parcel_id). Holds units, status
                    and estimated delivery years. Parcel totals are calculated from here, never typed into parcels.
parcel_summary      view: parcels with their totals calculated live from parcel_permissions.
register_checks     view: problems to fix (duplicate references, unlinked permissions, consents above capacity).

Writes Limerick_Housing_Land_Register.gpkg and Limerick_Housing_Land_Register.xlsx (same tables, live formulas).
Inputs: Limerick_Housing_Supply.gpkg (sites, permissions, permission_boundaries), Limerick_Housing_Supply_Dashboard.xlsx
(delivery year estimates), lea.geojson, nbh.geojson.
"""
import os, re, json, sqlite3
import numpy as np, pandas as pd, geopandas as gpd, pyogrio
from shapely.geometry import shape
from shapely.ops import unary_union

ITM = 2157
SUP = 'Limerick_Housing_Supply.gpkg'
OUT = 'Limerick_Housing_Land_Register.gpkg'
XL = 'Limerick_Housing_Land_Register.xlsx'
AS_AT = '2026-10-11'
POINT_BUFFER_M = 25           # parcels for consents with no planning boundary: circle round the scheme point
MERGE_SHARE = 0.2             # consent parcels overlapping by this share of the smaller one are the same land
YEARS = ['Q4 2026', '2027', '2028', '2029', '2030', '2031+']
STATUS = {'Complete': 'Complete', 'Under construction': 'Under construction', 'Not started – permission live': 'Permitted – not started',
          'Stalled (CIS)': 'Stalled', 'Not started – past expiry': 'Expired – not started', 'In planning': 'In planning'}
LIVE = ['Complete', 'Under construction', 'Permitted – not started', 'Stalled']          # counted as consented
for f in (OUT,):
    if os.path.exists(f):
        os.remove(f)

S = gpd.read_file(SUP, layer='sites').to_crs(ITM)
P = gpd.read_file(SUP, layer='permissions').to_crs(ITM)
PB = gpd.read_file(SUP, layer='permission_boundaries').to_crs(ITM).set_index('perm_id')
DY = pd.read_excel('Limerick_Housing_Supply_Dashboard.xlsx', sheet_name='Schemes', dtype={'Perm id': str}).set_index('Perm id')
fc = lambda p: gpd.GeoDataFrame([f['properties'] for f in json.load(open(p))['features']],
                                geometry=[shape(f['geometry']) for f in json.load(open(p))['features']], crs=4326).to_crs(ITM)
LEA, NBH = fc('lea.geojson'), fc('nbh.geojson')
lea_col = [c for c in LEA.columns if c.upper() in ('ENGLISH', 'LE_ENGLISH', 'LEA', 'NAME', 'LE_NAME')][0] if any(
    c.upper() in ('ENGLISH', 'LE_ENGLISH', 'LEA', 'NAME', 'LE_NAME') for c in LEA.columns) else LEA.columns[0]


def where(geom_series, layer, col):
    pts = gpd.GeoDataFrame(geometry=geom_series.representative_point(), crs=ITM)
    j = gpd.sjoin(pts, layer[[col, 'geometry']], how='left', predicate='within')
    return j[~j.index.duplicated()][col]


# ------------------------------------------------------------------ audit parcels
A = S.copy()
A['parcel_id'] = A.site_id
A['parcel_source'] = np.where(A.reconcile_action.fillna('').str.startswith('Reinstated'), 'Council audit – reinstated', 'Council audit')
A['scope'] = A.scope.fillna('City')
A['capacity_basis'] = 'Council estimate (area × density band)'
A['notes'] = A.reconcile_action.fillna('')

# ------------------------------------------------------------------ permissions: which parcel each belongs to
P['parcel_id'] = np.where(P.site_match.eq('Within site'), P.site_id, None)
audit_union = unary_union(list(A.geometry))
cons = P[P.parcel_id.isna()].copy()
geoms, approx = [], []
for pid, r in cons.iterrows():
    if r.perm_id in PB.index:
        g, a = PB.loc[r.perm_id, 'geometry'], 'Planning application boundary'
    else:
        g, a = r.geometry.buffer(POINT_BUFFER_M), f'Approximate – {POINT_BUFFER_M} m circle round scheme point (no boundary)'
    clipped = g.difference(audit_union)
    if clipped.is_empty or clipped.area < 0.05 * g.area:     # almost all on audit land: belongs to the audit parcel it overlaps most
        ov = A[A.intersects(g)]
        k = ov.geometry.intersection(g).area.idxmax()
        P.at[pid, 'parcel_id'] = ov.at[k, 'parcel_id']
        geoms.append(None); approx.append(None)
        continue
    geoms.append(clipped); approx.append(a)
cons['g'], cons['geometry_basis'] = geoms, approx
cons = cons[cons.g.notna()].copy()

# group consents on the same land into one parcel (phases, additional applications, replacements)
cons = cons.sort_values('units', ascending=False)
idx = list(cons.index)
parent = {i: i for i in idx}
def root(i):
    while parent[i] != i:
        i = parent[i]
    return i
for a_i, i in enumerate(idx):
    for j in idx[a_i + 1:]:
        gi, gj = cons.at[i, 'g'], cons.at[j, 'g']
        if gi.intersects(gj) and gi.intersection(gj).area >= MERGE_SHARE * min(gi.area, gj.area):
            parent[root(j)] = root(i)
cons['grp'] = [root(i) for i in cons.index]
rows = []
taken = None
for grp, g in sorted(cons.groupby('grp'), key=lambda kv: -kv[1].units.sum()):
    lead = g.sort_values(['units'], ascending=False).iloc[0]
    geom = unary_union(list(g.g))
    if taken is not None:
        geom = geom.difference(taken)                         # keep parcels from overlapping
    taken = geom if taken is None else taken.union(geom)
    ref = re.sub(r'[^A-Za-z0-9]', '', lead.planning_ref or lead.register_ref or f'CIS{lead.perm_id}')
    pid_ = f"PC-{ref}"
    P.loc[g.index, 'parcel_id'] = pid_
    rows.append(dict(parcel_id=pid_, parcel_source='Planning consent – not in council audit',
                     scope='City' if lead.neighbourhood not in ('Outside city neighbourhoods', 'Unknown') else 'County',
                     neighbourhood=lead.neighbourhood, local_name=str(lead.scheme)[:80], register_status='', landowner='',
                     zoning='', site_type='', density_band='', capacity_basis='Consented units (no council estimate)',
                     notes=('; '.join(sorted(set(x for x in g.geometry_basis if x.startswith('Approx'))))
                            + ('; was matched as ' + ', '.join(sorted(set(g.site_match))) if g.site_match.str.contains('check').any() else '')).strip('; '),
                     geometry=geom))
C = gpd.GeoDataFrame(rows, crs=ITM)
assert P.parcel_id.notna().all()

# ------------------------------------------------------------------ parcels layer (land facts only)
keep = ['parcel_id', 'parcel_source', 'scope', 'neighbourhood', 'local_name', 'register_status', 'landowner', 'zoning', 'site_type',
        'density_band', 'capacity_basis', 'notes']
A_ = A[keep + ['capacity_units', 'rsca', 'area_ha', 'geometry']].copy()
C_ = C[keep + ['geometry']].copy()
C_['capacity_units'] = np.nan                                 # consent-only parcels: capacity = consented units (set below)
C_['rsca'] = pd.NA
C_['area_ha'] = (C_.area / 1e4).round(3)
parcels = gpd.GeoDataFrame(pd.concat([A_, C_], ignore_index=True), crs=ITM)
parcels['lea'] = where(parcels.geometry, LEA, lea_col).values
parcels['mapped_area_ha'] = (parcels.area / 1e4).round(3)
parcels['developable_area_ha'] = parcels.area_ha
parcels['council_capacity_units'] = parcels.capacity_units
parcels = parcels.drop(columns='capacity_units')
parcels['last_reviewed'] = AS_AT
parcels['reviewed_by'] = ''
parcels = parcels[['parcel_id', 'parcel_source', 'scope', 'rsca', 'neighbourhood', 'lea', 'local_name', 'landowner', 'zoning', 'site_type',
                   'density_band', 'developable_area_ha', 'mapped_area_ha', 'council_capacity_units', 'capacity_basis', 'register_status', 'notes', 'last_reviewed',
                   'reviewed_by', 'geometry']]
assert parcels.parcel_id.is_unique

# ------------------------------------------------------------------ parcel_permissions table
pp = pd.DataFrame({
    'perm_id': P.perm_id, 'parcel_id': P.parcel_id, 'planning_ref': P.planning_ref.fillna(''), 'register_ref': P.register_ref.fillna(''),
    'scheme': P.scheme, 'units': P.units.fillna(0), 'student_bedspaces': P.student_bedspaces,
    'status': P.status.map(STATUS), 'counts_toward_totals': 'Yes', 'relationship': P.relationship,
    'tenure': P.tenure, 'delivery_body': P.delivery_body, 'route': P.route, 'final_grant': P.final_grant, 'expiry': P.expiry,
    'start_on_site': P.start, 'est_start': P.perm_id.map(DY['Est. start']), 'est_last_completions': P.perm_id.map(DY['Est. last completions']),
    'confidence': P.perm_id.map(DY['Confidence']),
})
for y in YEARS:
    pp[f'est_{y.lower().replace(" ", "_").replace("+", "_plus")}'] = P.perm_id.map(DY[y]).fillna(0).round(1)
pp['match_basis'] = P.site_match.where(P.site_match.eq('Within site'), 'Own consent parcel') \
    .where(~P.parcel_id.str.startswith('CITY') | P.site_match.eq('Within site'), 'Mostly on audit parcel')
pp['source'] = P.source
pp['last_updated'] = AS_AT
pp['notes'] = ''
assert pp.perm_id.is_unique and pp.status.notna().all()
YC = [c for c in pp.columns if c.startswith('est_') and c not in ('est_start', 'est_last_completions')]

# consent-only parcels: capacity = consented units on them
cons_units = pp[pp.status.isin(LIVE)].groupby('parcel_id').units.sum()
m = parcels.parcel_source.eq('Planning consent – not in council audit')
parcels.loc[m, 'council_capacity_units'] = np.nan


# ------------------------------------------------------------------ summary (python copy, for checks and the workbook)
def summary(parcels, pp):
    t = parcels.drop(columns='geometry').set_index('parcel_id')
    c = pp[pp.counts_toward_totals.eq('Yes')]
    for st, col in [('Complete', 'complete_units'), ('Under construction', 'under_construction_units'),
                    ('Permitted – not started', 'permitted_not_started_units'), ('Stalled', 'stalled_units'),
                    ('Expired – not started', 'expired_units'), ('In planning', 'in_planning_units')]:
        t[col] = c[c.status.eq(st)].groupby('parcel_id').units.sum().reindex(t.index).fillna(0)
    t['consented_units'] = t[['complete_units', 'under_construction_units', 'permitted_not_started_units', 'stalled_units']].sum(axis=1)
    t['capacity_used'] = t.council_capacity_units.fillna(t.consented_units)
    t['unconsented_capacity'] = (t.capacity_used - t.consented_units).clip(lower=0)
    t['total_supply_units'] = t.consented_units + t.unconsented_capacity
    t['future_supply_units'] = t.total_supply_units - t.complete_units
    t['permissions'] = c.groupby('parcel_id').size().reindex(t.index).fillna(0).astype(int)
    return t
T = summary(parcels, pp)
print(parcels.parcel_source.value_counts().to_dict())
print('permissions', len(pp), 'units', pp.units.sum(), 'consented', T.consented_units.sum(), 'unconsented', T.unconsented_capacity.sum(),
      'total', T.total_supply_units.sum(), 'future', T.future_supply_units.sum())
# no double counting: every counted permission's units appear once
assert abs(T[['complete_units', 'under_construction_units', 'permitted_not_started_units', 'stalled_units', 'expired_units', 'in_planning_units']].values.sum()
           - pp.units.sum()) < 0.01
ov = gpd.sjoin(parcels[['parcel_id', 'geometry']], parcels[['parcel_id', 'geometry']], predicate='overlaps')
ov = ov[ov.parcel_id_left < ov.parcel_id_right]
ov_area = sum(parcels.set_index('parcel_id').geometry[a].intersection(parcels.set_index('parcel_id').geometry[b]).area
              for a, b in zip(ov.parcel_id_left, ov.parcel_id_right)) / 1e4
print('overlap between parcels (ha):', round(ov_area, 3), 'pairs', len(ov))

# ------------------------------------------------------------------ GeoPackage
def clean(df):
    df = df.copy()
    for c in df.columns:
        if c != 'geometry' and str(df[c].dtype).startswith('datetime'):
            df[c] = pd.to_datetime(df[c]).dt.strftime('%Y-%m-%d')
    return df
parcels_out = clean(parcels)
parcels_out['rsca'] = pd.to_numeric(parcels_out.rsca.astype(object).where(parcels_out.rsca.notna(), None), errors='coerce')
parcels_out.to_file(OUT, layer='parcels', driver='GPKG')
pyogrio.write_dataframe(clean(pp), OUT, layer='parcel_permissions', driver='GPKG')
lists = pd.DataFrame([('status', s, 'Yes' if s in LIVE else 'No') for s in ['Complete', 'Under construction', 'Permitted – not started', 'Stalled',
                                                                        'Expired – not started', 'In planning']]
                     + [('parcel_source', s, '') for s in ['Council audit', 'Council audit – reinstated', 'Planning consent – not in council audit',
                                                           'Council audit – county']]
                     + [('counts_toward_totals', s, '') for s in ['Yes', 'No']],
                     columns=['list', 'value', 'counted_as_consented'])
pyogrio.write_dataframe(lists, OUT, layer='lookup_values', driver='GPKG')
DICT = [
    ('parcels', 'parcel_id', 'Unique parcel key. CITY-<rsca> for council audit parcels; PC-<planning ref> for consent parcels outside the audit. Never reuse a retired id.'),
    ('parcels', 'parcel_source', 'Council audit / Council audit – reinstated / Planning consent – not in council audit. County audit parcels: Council audit – county.'),
    ('parcels', 'scope', 'City or County.'),
    ('parcels', 'rsca', 'Council audit reference (audit parcels only).'),
    ('parcels', 'council_capacity_units', 'Council estimate of homes the parcel can take (audit parcels). Blank on consent parcels: their capacity is the consented units.'),
    ('parcels', 'capacity_basis', 'How capacity is set.'),
    ('parcels', 'developable_area_ha', 'Audit parcels: the council\u2019s net developable area, the basis of its capacity estimate. Consent parcels: mapped area.'),
    ('parcels', 'mapped_area_ha', 'Area of the polygon as drawn. Larger than the developable area where the council netted off roads, open space or constrained land.'),
    ('parcels', 'register_status', 'Status in the council audit file (audit parcels).'),
    ('parcels', 'notes', 'Why a parcel was reinstated, matched approximately, or needs checking.'),
    ('parcels', 'last_reviewed / reviewed_by', 'Update on each review.'),
    ('parcel_permissions', 'perm_id', 'Unique permission key (CIS project id or REG-<ref>). One row per permission.'),
    ('parcel_permissions', 'parcel_id', 'The one parcel this permission sits on. Must exist in parcels.'),
    ('parcel_permissions', 'units', 'Homes in this permission as counted (after amendments and repeats are removed). PBSA: units as recorded, bedspaces separate.'),
    ('parcel_permissions', 'status', 'Complete / Under construction / Permitted – not started / Stalled / Expired – not started / In planning.'),
    ('parcel_permissions', 'counts_toward_totals', 'Yes for the permission being counted. Set to No when a later permission replaces it on the same land (keep the row for the record).'),
    ('parcel_permissions', 'relationship', 'How the permission relates to others on the land (primary, additional phase, additional application, replaces earlier, extension of duration).'),
    ('parcel_permissions', 'est_start / est_last_completions / confidence / est_*', 'Estimated delivery years (method on the dashboard Assumptions sheet). Update when programmes are known.'),
    ('parcel_permissions', 'match_basis', 'Within site (boundary or point on an audit parcel); Mostly on audit parcel; Own consent parcel.'),
    ('parcel_summary', 'consented_units', 'Complete + under construction + permitted not started + stalled, from parcel_permissions where counts_toward_totals = Yes.'),
    ('parcel_summary', 'unconsented_capacity', 'Council capacity minus consented units, not below zero. Zero on consent parcels.'),
    ('parcel_summary', 'total_supply_units', 'Consented units + unconsented capacity. Sums across parcels with no double counting.'),
    ('parcel_summary', 'future_supply_units', 'Total supply minus homes already complete.'),
    ('rules', 'One permission, one parcel', 'Each permission row has exactly one parcel_id; parcels never overlap; totals are calculated, not typed.'),
    ('rules', 'New permission', 'Add a row to parcel_permissions. If it is on an existing parcel, use that parcel_id. If not, draw a parcel from the planning boundary (clipped to exclude existing parcels) with id PC-<ref>.'),
    ('rules', 'Amendment / repeat / extension', 'Add the row with counts_toward_totals = No unless it replaces the counted permission, in which case switch the old row to No and the new row to Yes.'),
    ('rules', 'Refused / withdrawn', 'Do not add to parcel_permissions. Record land interest in notes if useful.'),
]
pyogrio.write_dataframe(pd.DataFrame(DICT, columns=['table', 'field', 'meaning']), OUT, layer='data_dictionary', driver='GPKG')

con = sqlite3.connect(OUT)
gcol = con.execute("SELECT column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns WHERE table_name='parcels'").fetchone()
pcols = [r[1] for r in con.execute('PRAGMA table_info(parcels)')]
s = lambda st: f"COALESCE(SUM(CASE WHEN pp.status = '{st}' THEN pp.units END), 0)"
cons_sql = f"({s('Complete')} + {s('Under construction')} + {s('Permitted – not started')} + {s('Stalled')})"
cap_sql = f"COALESCE(p.council_capacity_units, {cons_sql})"
con.execute(f"""CREATE VIEW parcel_summary AS SELECT {', '.join('p.' + c for c in pcols)},
  {s('Complete')} AS complete_units, {s('Under construction')} AS under_construction_units,
  {s('Permitted – not started')} AS permitted_not_started_units, {s('Stalled')} AS stalled_units,
  {s('Expired – not started')} AS expired_units, {s('In planning')} AS in_planning_units,
  {cons_sql} AS consented_units,
  MAX({cap_sql} - {cons_sql}, 0) AS unconsented_capacity,
  {cons_sql} + MAX({cap_sql} - {cons_sql}, 0) AS total_supply_units,
  {cons_sql} + MAX({cap_sql} - {cons_sql}, 0) - {s('Complete')} AS future_supply_units,
  {' , '.join(f"COALESCE(SUM(pp.{c}), 0) AS {c}" for c in YC)},
  COUNT(pp.perm_id) AS permissions,
  CASE WHEN p.council_capacity_units IS NOT NULL AND {cons_sql} > 1.1 * p.council_capacity_units THEN 'Consented above capacity' ELSE '' END AS flag
FROM parcels p LEFT JOIN parcel_permissions pp ON pp.parcel_id = p.parcel_id AND pp.counts_toward_totals = 'Yes'
GROUP BY p.fid""")
con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) VALUES ('parcel_summary', 'features', 'parcel_summary', ?)", (gcol[2],))
con.execute("INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) VALUES ('parcel_summary', ?, ?, ?, 0, 0)",
            (gcol[0], gcol[1], gcol[2]))
con.execute("""CREATE VIEW register_checks AS
  SELECT 'Permission linked to a parcel that does not exist' AS problem, pp.perm_id AS item, pp.parcel_id AS detail FROM parcel_permissions pp
    LEFT JOIN parcels p ON p.parcel_id = pp.parcel_id WHERE p.parcel_id IS NULL
  UNION ALL SELECT 'Planning reference counted more than once', planning_ref, COUNT(*) FROM parcel_permissions
    WHERE counts_toward_totals = 'Yes' AND planning_ref <> '' GROUP BY planning_ref HAVING COUNT(*) > 1
  UNION ALL SELECT 'Duplicate perm_id', perm_id, COUNT(*) FROM parcel_permissions GROUP BY perm_id HAVING COUNT(*) > 1
  UNION ALL SELECT 'Duplicate parcel_id', parcel_id, COUNT(*) FROM parcels GROUP BY parcel_id HAVING COUNT(*) > 1
  UNION ALL SELECT 'Consent parcel with no counted permission', p.parcel_id, '' FROM parcels p
    WHERE p.parcel_source LIKE 'Planning consent%' AND NOT EXISTS (SELECT 1 FROM parcel_permissions pp WHERE pp.parcel_id = p.parcel_id AND pp.counts_toward_totals = 'Yes')""")
con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier) VALUES ('register_checks', 'attributes', 'register_checks')")
con.commit()
chk = con.execute('SELECT problem, COUNT(*) FROM register_checks GROUP BY problem').fetchall()
v = con.execute('SELECT SUM(consented_units), SUM(unconsented_capacity), SUM(total_supply_units), COUNT(*) FROM parcel_summary').fetchone()
con.close()
print('checks', chk, 'view totals', v)
pd.to_pickle({'parcels': parcels, 'pp': pp, 'T': T, 'YC': YC}, 'land_register.pkl')
