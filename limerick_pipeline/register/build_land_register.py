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
REVIEW = 'in_review/parcel_review.csv'          # analyst review of each parcel (status, notes, site no., capacity), by parcel_id
REMOVED = 'in_review/review_removed.gpkg'       # parcels the analyst removed: their land and permissions stay out of the register
SUP = 'Limerick_Housing_Supply.gpkg'
OUT = 'Limerick_Housing_Land_Register.gpkg'
XL = 'Limerick_Housing_Land_Register.xlsx'
AS_AT = '2026-10-11'
CATCH = 'in_catch/lccc_catchments_All.shp'   # study catchments: 9 city neighbourhoods, key towns, large villages
ZONING = 'in_zoning/gzt.gpkg'          # national generalised zoning (GZT), current Limerick plans (pull_zoning.py)
ASKEATON = 'in_zoning/askeaton_zoning.gpkg'   # Askeaton future residential zoning, supplied Oct 2026 (not in the national GZT file)
RZLT = 'in_zoning/rzlt2027.gpkg'       # residential zoned land tax, annual draft map 2027
MIN_ZONED_HA = 0.1                     # drop zoning slivers smaller than this after clipping
HOME_BUFFER_M = 15                     # existing homes (GeoDirectory) and their curtilage clipped out of zoned land
COUNTY = 'in_county/county_audit_2026.gpkg'  # council county settlements audit: Excel May 2026 placed on polygons + 2022 audit (sca_assemble.py)
GEOD = 'in_geodir/limerick_geod_residential_points.gpkg'   # GeoDirectory residential address points (licensed; not committed)
COMPLETE_SHARE = 0.95         # new built addresses / permitted units at which a scheme is treated as complete
CLUSTER_MIN = 10              # new-build address clusters outside every parcel worth checking
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
RM = gpd.read_file(REMOVED).to_crs(ITM) if os.path.exists(REMOVED) else gpd.GeoDataFrame(columns=['parcel_id', 'planning_refs', 'review_notes', 'geometry'], geometry='geometry', crs=ITM)
rm_refs = {x for v in RM.planning_refs.fillna('') for x in v.split(';') if x}
REMOVED_PERMS = P[P.planning_ref.astype(str).isin(rm_refs) | P.register_ref.astype(str).isin(rm_refs)].copy()
P = P[~P.perm_id.isin(REMOVED_PERMS.perm_id)].copy()
print('permissions removed at review:', list(REMOVED_PERMS.planning_ref))
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
A['parcel_source'] = 'Council audit'          # the 3 sites we reinstated are council audit land; why is kept in notes
A['scope'] = A.scope.fillna('City')
A['capacity_basis'] = 'Council estimate (area × density band)'
A['notes'] = A.reconcile_action.fillna('')

# council county settlements audit: sites in the smaller Development Plan settlements. Gross area and a density
# (homes/ha) per site; capacity = area x density. Where a range is given (e.g. 10-22) the midpoint is used.
if os.path.exists(COUNTY):
    # county settlements audit, assembled by sca_assemble.py: council Excel (May 2026) sites placed on polygons, every
    # polygon the council supplied (unnumbered where no Excel row is matched yet), and 2022 audit sites the Excel lacks
    K = gpd.read_file(COUNTY, layer='sites').to_crs(ITM)
    K['geometry'] = K.geometry.make_valid().buffer(0)
    def _dens(v):
        n = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', str(v))] if pd.notna(v) else []
        return sum(n) / len(n) if n else np.nan
    K['dph'] = K.Densities.map(_dens)
    K['cap'] = K.Capacity.where(K.Capacity.notna(), (K.Area * K.dph).round(1))
    # The audit predates some consents. A consent lying mostly inside a site (95%+) joins that site's parcel below; one
    # that only overlaps it keeps its own land, so the site is clipped and its capacity scaled to what is left.
    # Remnants under 0.05 ha are dropped.
    # Only the 2022 sites are clipped: the May 2026 Excel and the council's own outlines already take account of
    # permissions (site status, reduced areas), so they keep their full outline and permissions attach to them below.
    K['orig_ha'] = K.area / 1e4
    K['clip_note'] = ''
    old = K.source.str.startswith('County audit 2022')
    for _, r in P.iterrows():
        g = PB.loc[r.perm_id, 'geometry'] if r.perm_id in PB.index else r.geometry.buffer(POINT_BUFFER_M)
        for k in K.index[old & K.intersects(g)]:
            ov = K.at[k, 'geometry'].intersection(g).area
            if ov / g.area < 0.95 and ov > 0.01 * K.at[k, 'geometry'].area:
                K.at[k, 'geometry'] = K.at[k, 'geometry'].difference(g)
                K.at[k, 'clip_note'] += f'; clipped by consent {r.planning_ref or r.perm_id}'
    K['left_ha'] = K.area / 1e4
    gone = K.left_ha < 0.05
    if gone.any():
        print('county audit sites dropped (built or permitted since):', list(K.loc[gone, 'settlement_name'] + ' ' + K.loc[gone, 'site_no']))
    K = K[~gone].copy()
    K['Area'] = (K.Area * K.left_ha / K.orig_ha).round(3)
    K['cap'] = (K.cap * K.left_ha / K.orig_ha).round(0)
    K['site_id'] = ['CTY-' + re.sub(r'[^A-Z]', '', s.upper())[:12] + '-' + re.sub(r'[^A-Za-z0-9]+', '-', str(n)).strip('-').upper()
                    for s, n in zip(K.settlement_name, K.site_no)]
    assert K.site_id.is_unique, K.site_id[K.site_id.duplicated()].tolist()
    tier = K.TAZ_Tier.map({1: 'Tier 1 (serviced)', 2: 'Tier 2 (serviceable)'}).fillna('')
    ww = np.where(K.wastewater.notna(), 'wastewater ' + K.wastewater.fillna('').str.strip(), '')
    status = (tier + '; ' + ww).str.strip('; ')
    notes = (K.site_status.fillna('').radd('Site status: ').where(K.site_status.notna(), '') + '; '
             + K.permission.fillna('').radd('Permission: ').where(K.permission.notna(), '') + '; '
             + K.note.fillna('') + '; ' + K.placement.fillna('').radd('Placement: ') + K.clip_note).str.replace(r'(; )+', '; ', regex=True).str.strip('; ')
    KA = gpd.GeoDataFrame(dict(
        site_id=K.site_id, parcel_id=K.site_id, rsca=None, scope='County', neighbourhood='Outside city neighbourhoods',
        local_name=K.settlement_name + ' – site ' + K.site_no, register_status=status,
        landowner='', zoning=K.Zone_Orig.fillna(''), site_type=K.Taz_Type.fillna('').str.strip(), density_band=K.Densities.fillna('').astype(str),
        area_ha=K.Area, capacity_units=K.cap, reconcile_action=np.where(K.source.str.startswith('County audit 2022'), '', 'county-2026'), parcel_source='Council audit – county',
        capacity_basis=K.cap_basis.fillna(''),
        notes=notes, geometry=K.geometry), crs=ITM)
    A = pd.concat([A, KA], ignore_index=True)
    print('county audit sites', len(KA), 'settlements', K.settlement_name.nunique(), 'capacity', KA.capacity_units.sum(),
          'no capacity yet', int(KA.capacity_units.isna().sum()))

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
    ov = A[A.intersects(g)]
    best = ov.geometry.intersection(g).area.idxmax() if len(ov) else None
    soft = best is not None and ov.at[best, 'reconcile_action'] == 'county-2026' and ov.geometry.intersection(g).area.max() >= 0.5 * g.area
    if clipped.is_empty or clipped.area < 0.05 * g.area or soft:   # (mostly) on audit land: belongs to the audit parcel it overlaps most
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

# ------------------------------------------------------------------ zoned land without consent (interim, until the county audit)
# New residential zoning (GZT R1, and R3 zones described as new residential / residential development area / serviced sites)
# not already in a parcel and not already built on. Capacity = mapped area x developable share x density.
#   developable share: the council city audit's own ratio of developable to mapped area
#   density: median homes per hectare of permitted Limerick schemes (10+ homes, planning boundary) by area type;
#            serviced sites zoning at the lower quartile of county schemes
PBF = PB.reset_index().merge(P[['perm_id', 'settlement', 'neighbourhood']], on='perm_id')
PBF = PBF[(PBF.units >= 10) & (PBF.boundary_ha > 0.2)]
PBF['tier'] = np.where(PBF.neighbourhood.eq('City Centre'), 'City centre',
                       np.where(PBF.settlement.eq('Limerick City and Suburbs'), 'City suburbs', 'County towns and villages'))
DENS = PBF.groupby('tier').units_per_ha.median().round(0).to_dict()
DENS_N = PBF.groupby('tier').size().to_dict()
DENS['Serviced sites'] = round(float(PBF[PBF.tier.eq('County towns and villages')].units_per_ha.quantile(0.25)), 0)
aud = A[A.area_ha.notna() & (A.area_ha <= A.area / 1e4 * 1.001) & A.parcel_source.ne('Council audit – county')]   # city audit only: county areas are gross
NET = round(float(aud.area_ha.sum() / (aud.area.sum() / 1e4)), 2)
print('densities', DENS, 'n', DENS_N, 'net share', NET)
Z = gpd.GeoDataFrame(columns=['geometry'], geometry='geometry', crs=ITM)
if os.path.exists(ZONING):
    ZG = gpd.read_file(ZONING).to_crs(ITM)
    if os.path.exists(ASKEATON):
        AK = gpd.read_file(ASKEATON).to_crs(ITM).explode(index_parts=False)
        AK = gpd.GeoDataFrame(dict(PLAN_NAME='Askeaton Local Area Plan (council zoning file, Oct 2026)',
                                   ZONE_GZT=np.where(AK.zone.str.startswith('RDA'), 'R1', 'R3'),
                                   ZONE_ORIG=AK['desc'].str.replace('Resi ', 'Residential ', regex=False),
                                   geometry=AK.geometry.values), crs=ITM)
        ZG = pd.concat([ZG, AK], ignore_index=True)
    newres = ZG.ZONE_GZT.eq('R1') | (ZG.ZONE_GZT.eq('R3') & ZG.ZONE_ORIG.str.contains('New Residential|Development Area|Servic', case=False, na=False))
    ZG = ZG[newres].explode(index_parts=False).reset_index(drop=True)
    taken_all = unary_union(list(A.geometry) + list(C.geometry) + list(RM.geometry))   # removed at review: stays out
    homes = unary_union(list(gpd.read_file(GEOD).to_crs(ITM).buffer(HOME_BUFFER_M))) if os.path.exists(GEOD) else None
    rz = unary_union(list(gpd.read_file(RZLT).to_crs(ITM).geometry)) if os.path.exists(RZLT) else None
    city_u = unary_union(list(NBH.geometry))
    cc_u = unary_union(list(NBH[NBH.nbhd.eq('City Centre')].geometry))
    zrows = []
    for i, z in ZG.iterrows():
        g = z.geometry.difference(taken_all)
        if homes is not None:
            g = g.difference(homes)
        for part in (getattr(g, 'geoms', [g]) if not g.is_empty else []):
            part = part.difference(taken_all)                 # zoning layers can overlap between plans
            if part.is_empty or part.area / 1e4 < MIN_ZONED_HA:
                continue
            taken_all = taken_all.union(part)
            if part.geom_type != 'Polygon':
                part = max(getattr(part, 'geoms', [part]), key=lambda q: q.area)
            serviced = 'servic' in str(z.ZONE_ORIG).lower()
            pt = part.representative_point()
            tier = 'Serviced sites' if serviced else ('City centre' if pt.within(cc_u) else 'City suburbs' if pt.within(city_u) else 'County towns and villages')
            plan = re.sub(r' (Local Area P[Ll]an|Development Plan).*', '', str(z.PLAN_NAME))
            zrows.append(dict(plan_name=z.PLAN_NAME, plan=plan, zone_gzt=z.ZONE_GZT, zone_orig=z.ZONE_ORIG,
                              phase='Phase 2 – later phasing' if 'phase 2' in str(z.ZONE_ORIG).lower() else '',
                              scope='City' if pt.within(city_u) else 'County', density_tier=tier, density_dph=DENS[tier],
                              rzlt_2027_share=round(part.intersection(rz).area / part.area, 2) if rz is not None else np.nan,
                              geometry=part))
    if zrows:
        Z = gpd.GeoDataFrame(zrows, crs=ITM)
        Z['n'] = Z.groupby('plan').cumcount() + 1
        Z['parcel_id'] = 'ZN-' + Z.plan.str.replace(r'[^A-Za-z]', '', regex=True).str[:12] + '-' + Z.n.astype(str).str.zfill(3)
        Z['mapped'] = Z.area / 1e4
        Z['area_ha'] = (Z.mapped * NET).round(3)
        Z['capacity_units'] = (Z.area_ha * Z.density_dph).round(0)
        Z['parcel_source'] = 'Zoned land – no consent (estimate)'
        Z['neighbourhood'] = where(Z.geometry, NBH, 'nbhd').fillna('County').values
        Z['local_name'] = Z.plan + ': ' + Z.zone_orig
        Z['zoning'] = Z.zone_orig
        Z['capacity_basis'] = 'Estimate: zoned area x developable share x density'
        Z['density_basis'] = [f'{d:.0f} homes/ha = median of {DENS_N.get(t, 0)} permitted Limerick schemes of 10+ homes in {t.lower()} '
                              f'(planning boundaries, gross over the red line)' if t != 'Serviced sites' else
                              f'{d:.0f} homes/ha = lower quartile of permitted county schemes, for serviced-site (self-build) zoning'
                              for d, t in zip(Z.density_dph, Z.density_tier)]
        Z['density_basis'] = Z.density_basis + f'; developable share {NET:.2f} = council city audit developable area / mapped area'
        Z['notes'] = np.where(Z.phase.ne(''), 'Phase 2 zoning: later phasing', '')
        Z.loc[Z.plan.eq('Askeaton'), 'notes'] = (Z.loc[Z.plan.eq('Askeaton'), 'notes'] + '; Askeaton WWTP Red status in HDAP 2026: no remaining wastewater capacity').str.strip('; ')
        for c in ['register_status', 'landowner', 'site_type', 'density_band']:
            Z[c] = ''
        Z['rsca'] = pd.NA
    print('zoned parcels', len(Z), 'ha', round(Z.mapped.sum(), 1) if len(Z) else 0, 'capacity', Z.capacity_units.sum() if len(Z) else 0)
assert P.parcel_id.notna().all()

# ------------------------------------------------------------------ parcels layer (land facts only)
keep = ['parcel_id', 'parcel_source', 'scope', 'neighbourhood', 'local_name', 'register_status', 'landowner', 'zoning', 'site_type',
        'density_band', 'capacity_basis', 'notes']
A_ = A[keep + ['capacity_units', 'rsca', 'area_ha', 'geometry']].copy()
C_ = C[keep + ['geometry']].copy()
C_['capacity_units'] = np.nan                                 # consent-only parcels: capacity = consented units (set below)
C_['rsca'] = pd.NA
C_['area_ha'] = (C_.area / 1e4).round(3)
ZX = ['plan_name', 'zone_gzt', 'phase', 'density_tier', 'density_dph', 'density_basis', 'rzlt_2027_share']
Z_ = Z[keep + ['capacity_units', 'rsca', 'area_ha'] + ZX + ['geometry']].copy() if len(Z) else None
parcels = gpd.GeoDataFrame(pd.concat([A_, C_] + ([Z_] if Z_ is not None else []), ignore_index=True), crs=ITM)
for c in ZX:
    if c not in parcels:
        parcels[c] = None
parcels['lea'] = where(parcels.geometry, LEA, lea_col).values
parcels['mapped_area_ha'] = (parcels.area / 1e4).round(3)
parcels['developable_area_ha'] = parcels.area_ha
parcels['last_reviewed'] = AS_AT
parcels['reviewed_by'] = ''
parcels['density_estimate_units'] = np.nan
parcels = parcels[['parcel_id', 'parcel_source', 'scope', 'rsca', 'neighbourhood', 'lea', 'local_name', 'landowner', 'zoning', 'site_type',
                   'density_band', 'developable_area_ha', 'mapped_area_ha', 'capacity_units', 'capacity_basis', 'density_estimate_units', 'plan_name', 'zone_gzt', 'phase',
                   'density_tier', 'density_dph', 'density_basis', 'rzlt_2027_share', 'register_status', 'notes', 'last_reviewed',
                   'reviewed_by', 'geometry']]
parcels['geometry'] = parcels.geometry.make_valid().buffer(0)
# analyst review: status and notes carried onto each parcel; parcels marked Remove are taken out
RV = pd.read_csv(REVIEW, dtype=str).fillna('') if os.path.exists(REVIEW) else pd.DataFrame(columns=['parcel_id'])
for c in ['review_status', 'review_site_no', 'review_capacity', 'review_notes', 'reviewed_by', 'reviewed_on', 'review_round']:
    parcels[c] = parcels.parcel_id.map(RV.set_index('parcel_id')[c]) if c in RV else ''
    parcels[c] = parcels[c].fillna('')
parcels.loc[parcels.review_status.eq(''), 'review_status'] = 'To review'
# IDs of zoned-land parcels (numbered in sequence) and consent parcels (named after the largest permission) can change
# between builds, so a parcel whose ID is zoned land or not in the review takes the review of the reviewed polygon it
# overlaps by 50%+
REVIEW_SHAPES = 'in_review/review_shapes.gpkg'
if os.path.exists(REVIEW_SHAPES):
    ZR = gpd.read_file(REVIEW_SHAPES).to_crs(ITM)
    ZR = ZR[ZR.review_status.ne('Remove')]                      # removed land and permissions are already taken out
    loose = parcels.parcel_id.str.startswith('ZN-') | ~parcels.parcel_id.isin(RV.parcel_id)
    for i in parcels.index[loose]:
        g = parcels.at[i, 'geometry']
        ov = ZR.geometry.intersection(g).area
        hit = ov.max() >= 0.5 * g.area if len(ov) else False
        for c in ['review_status', 'review_site_no', 'review_capacity', 'review_notes', 'reviewed_by']:
            v = ZR.at[ov.idxmax(), c] if hit else None
            parcels.at[i, c] = (v if isinstance(v, str) else '' if v is None or pd.isna(v) else str(v)) if hit else ('To review' if c == 'review_status' else '')
        on = hit and parcels.at[i, 'review_status'] != 'To review'
        parcels.at[i, 'reviewed_on'], parcels.at[i, 'review_round'] = ('2026-10-26', 'Non-city review, Oct 2026') if on else ('', '')
gone_ids = set()                                             # removals are applied by shape and permission (REMOVED)
parcels = parcels[~parcels.parcel_id.isin(gone_ids)].copy()
cap_ov = pd.to_numeric(parcels.review_capacity, errors='coerce')
parcels.loc[cap_ov.notna(), 'capacity_units'] = cap_ov[cap_ov.notna()]
parcels.loc[cap_ov.notna(), 'capacity_basis'] = 'Analyst review capacity'
print('review:', parcels.review_status.value_counts().to_dict(), 'removed', sorted(gone_ids))
assert parcels.parcel_id.is_unique

# ------------------------------------------------------------------ study catchments
# Each parcel goes to the catchment it overlaps most; parcels touching none are 'Rest of county'.
parcels['catchment'], parcels['catchment_type'], parcels['catchment_share'] = 'Rest of county', 'Rest of county', np.nan
parcels['catchment_basis'] = 'Rest of county'
EDGE_TOWN_M, NAMED_TOWN_M = 500, 2000   # settlement-edge rules for parcels outside every catchment
CA = None
if os.path.exists(CATCH):
    CA = gpd.read_file(CATCH).to_crs(ITM)
    CA['catchment'] = CA.URBAN_AR_2.astype(str).str.strip()
    CA['catchment_type'] = CA['type'].map({'Key Town': 'Key town', 'Village': 'Large village', 'nbhd': 'City neighbourhood'}).fillna(CA['type'])
    for i, r in parcels.iterrows():
        hit = CA[CA.intersects(r.geometry)]
        if len(hit):
            sh = hit.geometry.intersection(r.geometry).area / r.geometry.area
            k = sh.idxmax()
            if sh[k] > 0.05:
                parcels.at[i, 'catchment'], parcels.at[i, 'catchment_type'] = hit.at[k, 'catchment'], hit.at[k, 'catchment_type']
                parcels.at[i, 'catchment_share'] = round(float(sh[k]), 2)
                parcels.at[i, 'catchment_basis'] = 'Inside catchment'
    # parcels outside every catchment but clearly tied to a settlement:
    #   zoned in that settlement's local area plan; or within EDGE_TOWN_M of it; or named in the scheme and within NAMED_TOWN_M
    towns = CA[CA.catchment_type.ne('City neighbourhood')]
    sch = P.groupby('parcel_id').scheme.apply(lambda x: ' '.join(x.astype(str))).to_dict()
    for i, r in parcels[parcels.catchment.eq('Rest of county')].iterrows():
        d = towns.distance(r.geometry)
        k = d.idxmin()
        town, dist = towns.at[k, 'catchment'], d[k]
        plan = str(r.get('plan_name') or '')
        lap_town = next((t for t in towns.catchment if plan.lower().startswith(t.lower())), None)
        txt = (str(r.local_name) + ' ' + sch.get(r.parcel_id, '')).lower()
        named = next((t for t in towns.catchment if t.lower() in txt), None)
        if lap_town:
            town, basis = lap_town, f'Zoned in the {plan}'
        elif dist <= EDGE_TOWN_M:
            basis = f'Edge of settlement (within {EDGE_TOWN_M} m)'
        elif named and towns.loc[towns.catchment.eq(named)].distance(r.geometry).min() <= NAMED_TOWN_M:
            town, basis = named, f'Named in scheme, within {NAMED_TOWN_M / 1000:.0f} km'
        else:
            continue
        parcels.at[i, 'catchment'] = town
        parcels.at[i, 'catchment_type'] = towns.loc[towns.catchment.eq(town), 'catchment_type'].iloc[0]
        parcels.at[i, 'catchment_share'] = 0.0
        parcels.at[i, 'catchment_basis'] = basis
    print('catchment basis', parcels.catchment_basis.str.replace(r' the .*', '', regex=True).value_counts().to_dict())
    print('catchments', parcels.groupby('catchment_type').size().to_dict())
cols = list(parcels.columns)
for c in ['catchment', 'catchment_type', 'catchment_share', 'catchment_basis']:
    cols.remove(c)
cols[cols.index('neighbourhood'):cols.index('neighbourhood')] = ['catchment', 'catchment_type', 'catchment_share', 'catchment_basis']
parcels = parcels[cols]

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
pp['catchment'] = pp.parcel_id.map(parcels.set_index('parcel_id').catchment)
pp['catchment_type'] = pp.parcel_id.map(parcels.set_index('parcel_id').catchment_type)
pp['match_basis'] = P.site_match.where(P.site_match.eq('Within site'), 'Own consent parcel') \
    .where(~P.parcel_id.str.startswith('CITY') | P.site_match.eq('Within site'), 'Mostly on audit parcel')
pp['source'] = P.source
# bedroom mix from the pipeline tracker (CIS, register description or planning file documents)
_ap = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Applications', dtype={'Project Id': str}).set_index('Project Id')
MIXC = {'Studio': 'mix_studio', '1 Bed': 'mix_1bed', '2 Bed': 'mix_2bed', '3 Bed': 'mix_3bed', '4 Bed': 'mix_4bed', '5+ Bed': 'mix_5plus'}
pp['mix_source'] = pp.perm_id.map(_ap['Mix Source']).fillna('Not available')
for k, v in MIXC.items():
    pp[v] = pd.to_numeric(pp.perm_id.map(_ap[k]), errors='coerce').fillna(0)
pp.loc[pp.mix_source.str.startswith('Not available'), list(MIXC.values())] = np.nan
pp['last_updated'] = AS_AT
pp['notes'] = ''
assert pp.perm_id.is_unique and pp.status.notna().all()
YC = [c for c in pp.columns if c.startswith('est_') and c not in ('est_start', 'est_last_completions')]

# ------------------------------------------------------------------ GeoDirectory: homes on the ground
# New residential addresses (created on or after the application was received) inside each permission's boundary,
# kept within its parcel. Each address is credited to one permission only: on a parcel with several permissions the
# earliest-started takes addresses up to its unit count, then the next. Status is moved to Complete only where built
# addresses reach COMPLETE_SHARE of units; anything else is a suggestion for a person to confirm.
pp['status_cis'] = pp.status
pp['status_source'] = 'CIS / building control'
for c in ['geod_new_built', 'geod_new_undercon', 'geod_new_vacant']:
    pp[c] = 0
pp['geod_extract'] = ''
pp['geod_suggestion'] = ''
GD = None
if os.path.exists(GEOD):
    GD = gpd.read_file(GEOD).to_crs(ITM)
    GD['created'] = pd.to_datetime(GD.create_dat, dayfirst=True, errors='coerce')
    GD = GD[GD.demolished.ne('Y') & GD.invalid.ne('Y')]
    extract = GD.created.max().strftime('%Y-%m-%d')
    gj = gpd.sjoin(GD[['created', 'under_cons', 'vacant', 'geometry']], parcels[['parcel_id', 'geometry']], predicate='within')
    parcels['geod_addresses_now'] = parcels.parcel_id.map(gj.groupby('parcel_id').size()).fillna(0).astype(int)
    parcels['geod_new_since_2019'] = parcels.parcel_id.map(gj[gj.created >= '2019-01-01'].groupby('parcel_id').size()).fillna(0).astype(int)
    parcels['geod_extract'] = extract
    pp['geod_extract'] = extract
    pgeom = parcels.set_index('parcel_id').geometry
    rec = pd.to_datetime(P.set_index('perm_id').received, errors='coerce')
    # An extension of duration keeps the parent permission alive, so homes built under the parent before the
    # extension was lodged belong to it. Count addresses from 1 January of the parent's year (related_ref, e.g.
    # 13447 = 13/447 = 2013) instead of the extension's received date.
    _apps = gpd.read_file(SUP, layer='applications', ignore_geometry=True)
    _par = _apps[_apps.final_relationship.str.contains('Extension of duration', na=False)].set_index('perm_id').related_ref.dropna().astype(str)
    _par = _par[_par.str.fullmatch(r'\d{5,8}')]
    for k, v in _par.items():
        if k in rec.index:
            rec[k] = pd.Timestamp(f'20{v[:2]}-01-01')
    for parcel_id, grp in pp[pp.counts_toward_totals.eq('Yes')].groupby('parcel_id'):
        used = set()
        grp = grp.assign(_o=pd.to_datetime(grp.start_on_site).fillna(pd.to_datetime(grp.final_grant))).sort_values('_o')
        for i, r in grp.iterrows():
            g = PB.loc[r.perm_id, 'geometry'] if r.perm_id in PB.index else P.set_index('perm_id').geometry[r.perm_id].buffer(POINT_BUFFER_M)
            g = g.buffer(5).intersection(pgeom[parcel_id].buffer(5))
            since = pd.to_datetime(rec[r.perm_id]) if pd.notna(rec[r.perm_id]) else pd.Timestamp('2017-01-01')
            a = GD[(GD.created >= since) & GD.within(g) & ~GD.index.isin(used)]
            built, uc = a[a.under_cons.ne('Y')], a[a.under_cons.eq('Y')]
            if not r.units or r.units <= 0:                   # zero-unit records (extensions, placeholders) take no addresses
                continue
            nb = min(len(built), int(r.units))
            nu = min(len(uc), max(int(r.units) - nb, 0))
            used |= set(built.index[:nb]) | set(uc.index[:nu])
            pp.at[i, 'geod_new_built'], pp.at[i, 'geod_new_undercon'] = nb, nu
            pp.at[i, 'geod_new_vacant'] = int(built.iloc[:nb].vacant.eq('Y').sum())
    u = pp.units.replace(0, np.nan)
    # small schemes: one address short of the unit count still counts (95% of 12 would demand all 12)
    full = (pp.geod_new_built >= np.where(pp.units >= 10, np.minimum(COMPLETE_SHARE * u, u - 1), COMPLETE_SHARE * u)) & pp.units.gt(0)
    some = (pp.geod_new_built + pp.geod_new_undercon) > 0
    pp.loc[full & pp.status.ne('Complete'), 'geod_suggestion'] = 'Complete – applied'
    pp.loc[~full & some & pp.status.isin(['Permitted – not started', 'Stalled', 'Expired – not started']), 'geod_suggestion'] = 'Under construction – check'
    pp.loc[~some & pp.status.eq('Complete'), 'geod_suggestion'] = 'No new addresses found – check location'
    pp.loc[pp.status.eq('Complete') & some & ~full, 'geod_suggestion'] = 'Fewer addresses than units – check'
    app = pp.geod_suggestion.eq('Complete – applied')
    pp.loc[app, 'status'] = 'Complete'
    pp.loc[app, 'status_source'] = f'GeoDirectory {extract}'
    pp.loc[app, YC] = 0.0
    print('GeoDirectory', extract, pp.geod_suggestion.value_counts().to_dict(), 'units moved to Complete', pp.loc[app, 'units'].sum())
# homes built to date: all units of a completed scheme, otherwise GeoDirectory's built count (part-built schemes)
pp['units_built'] = np.where(pp.status.eq('Complete'), pp.units, np.minimum(pp.geod_new_built.fillna(0), pp.units))

# consent-only parcels: capacity = consented units on them
cons_units = pp[pp.status.isin(LIVE)].groupby('parcel_id').units.sum()
m = parcels.parcel_source.eq('Planning consent – not in council audit')
parcels.loc[m, 'capacity_units'] = np.nan

# ------------------------------------------------------------------ every parcel contributes
# Parcels that would otherwise add nothing get a capacity, flagged in capacity_basis:
#   consent parcels with no live consent: units of the expired permission or the pending application (land already put forward for housing)
#   any parcel still without capacity (council audit parcels the council left at 0, consent parcels with no unit count):
#   developable area (mapped area x developable share where none is recorded) x density for its area type
live = pp[pp.counts_toward_totals.eq('Yes') & pp.status.isin(LIVE)].groupby('parcel_id').units.sum()
dead = pp[pp.counts_toward_totals.eq('Yes')]
exp_u = dead[dead.status.eq('Expired – not started')].groupby('parcel_id').units.sum()
pln_u = dead[dead.status.eq('In planning')].groupby('parcel_id').units.sum()
pid = parcels.parcel_id
no_live = pid.map(live).fillna(0).eq(0)
cons_p = parcels.parcel_source.eq('Planning consent – not in council audit')
fill_e = cons_p & no_live & pid.map(exp_u).fillna(0).gt(0)
fill_p = cons_p & no_live & ~fill_e & pid.map(pln_u).fillna(0).gt(0)
parcels.loc[fill_e, 'capacity_units'] = pid[fill_e].map(exp_u)
parcels.loc[fill_e, 'capacity_basis'] = 'Units of the expired permission (lapsed; land accepted for housing)'
parcels.loc[fill_p, 'capacity_units'] = pid[fill_p].map(pln_u)
parcels.loc[fill_p, 'capacity_basis'] = 'Units of the application in planning (pending decision)'
cc_u = unary_union(list(NBH[NBH.nbhd.eq('City Centre')].geometry)); city_u = unary_union(list(NBH.geometry))
need = (parcels.capacity_units.fillna(0) <= 0) & ~(cons_p & no_live.eq(False))
# county audit: a council capacity of 0 stands (land taken by a permission), and council polygons with no Excel row yet
# wait for their figures rather than take an estimate (they still get density_estimate_units)
cty = parcels.parcel_source.eq('Council audit – county')
need &= ~(cty & parcels.capacity_units.eq(0))
for i, r in parcels[need].iterrows():
    pt = r.geometry.representative_point()
    tier = 'City centre' if pt.within(cc_u) else 'City suburbs' if pt.within(city_u) else 'County towns and villages'
    dev = r.developable_area_ha if pd.notna(r.developable_area_ha) and r.developable_area_ha > 0 else round(r.mapped_area_ha * NET, 3)
    parcels.at[i, 'developable_area_ha'] = dev
    parcels.at[i, 'capacity_units'] = max(1.0, round(dev * DENS[tier]))
    parcels.at[i, 'density_tier'], parcels.at[i, 'density_dph'] = tier, DENS[tier]
    parcels.at[i, 'density_basis'] = f'{DENS[tier]:.0f} homes/ha = median of {DENS_N.get(tier, 0)} permitted Limerick schemes of 10+ homes in {tier.lower()}; developable share {NET:.2f} where none recorded'
    was = 'council audit recorded no capacity' if r.parcel_source.startswith('Council') else 'no unit count recorded'
    parcels.at[i, 'capacity_basis'] = f'Estimate ({was}): developable area x density'
# Indicative yield for every parcel from area and local density, so all polygons can be compared on one basis.
# It does not enter the supply totals: those use council capacity, zoning estimate or consented units (capacity_used).
for i, r in parcels.iterrows():
    pt = r.geometry.representative_point()
    tier = r.density_tier if isinstance(r.density_tier, str) and r.density_tier in DENS else (
        'City centre' if pt.within(cc_u) else 'City suburbs' if pt.within(city_u) else 'County towns and villages')
    dev = r.developable_area_ha if pd.notna(r.developable_area_ha) and r.developable_area_ha > 0 else round(r.mapped_area_ha * NET, 3)
    parcels.at[i, 'density_estimate_units'] = max(1.0, round(dev * DENS[tier]))
    if not (isinstance(r.density_tier, str) and r.density_tier):
        parcels.at[i, 'density_tier'], parcels.at[i, 'density_dph'] = tier, DENS[tier]
        parcels.at[i, 'density_basis'] = (f'{DENS[tier]:.0f} homes/ha = median of {DENS_N.get(tier, 0)} permitted Limerick schemes of 10+ homes in '
                                          f'{tier.lower()}; applied to {"developable" if pd.notna(r.developable_area_ha) and r.developable_area_ha > 0 else f"mapped area x {NET:.2f}"} for density_estimate_units only')
print('capacity filled: expired', int(fill_e.sum()), 'in planning', int(fill_p.sum()), 'area estimate', int(need.sum()),
      'units', parcels.loc[fill_e | fill_p | need, 'capacity_units'].sum())


# ------------------------------------------------------------------ summary (python copy, for checks and the workbook)
def summary(parcels, pp):
    t = parcels.drop(columns='geometry').set_index('parcel_id')
    c = pp[pp.counts_toward_totals.eq('Yes')]
    for st, col in [('Complete', 'complete_units'), ('Under construction', 'under_construction_units'),
                    ('Permitted – not started', 'permitted_not_started_units'), ('Stalled', 'stalled_units'),
                    ('Expired – not started', 'expired_units'), ('In planning', 'in_planning_units')]:
        t[col] = c[c.status.eq(st)].groupby('parcel_id').units.sum().reindex(t.index).fillna(0)
    t['consented_units'] = t[['complete_units', 'under_construction_units', 'permitted_not_started_units', 'stalled_units']].sum(axis=1)
    t['capacity_used'] = t.capacity_units.fillna(t.consented_units)
    t['unconsented_capacity'] = (t.capacity_used - t.consented_units).clip(lower=0)
    t['total_supply_units'] = t.consented_units + t.unconsented_capacity
    t['built_units'] = c[c.status.isin(LIVE)].groupby('parcel_id').units_built.sum().reindex(t.index).fillna(0)
    t['future_supply_units'] = t.total_supply_units - t.built_units
    t['permissions'] = c.groupby('parcel_id').size().reindex(t.index).fillna(0).astype(int)
    t['parcel_status'] = np.select([(t.consented_units > 0) & (t.built_units >= t.consented_units) & (t.unconsented_capacity == 0),
                                    t.built_units > 0, t.consented_units > 0], ['Finished', 'Partly built', 'Consented – not built'], 'No consent')
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
                     + [('parcel_source', s, '') for s in ['Council audit', 'Planning consent – not in council audit', 'Zoned land – no consent (estimate)',
                                                           'Council audit – county']]
                     + [('counts_toward_totals', s, '') for s in ['Yes', 'No']],
                     columns=['list', 'value', 'counted_as_consented'])
pyogrio.write_dataframe(lists, OUT, layer='lookup_values', driver='GPKG')
DICT = [
    ('parcels', 'parcel_id', 'Unique parcel key. CITY-<rsca> for council audit parcels; PC-<planning ref> for consent parcels outside the audit. Never reuse a retired id.'),
    ('parcels', 'parcel_source', 'Council audit (3 sites removed in the council review and reinstated by us say so in notes) / Planning consent – not in council audit / Zoned land – no consent (estimate: new residential zoning outside every other parcel and not built on, until the county audit replaces it). County audit parcels: Council audit – county.'),
    ('parcels', 'scope', 'City or County.'),
    ('parcels', 'rsca', 'Council audit reference (audit parcels only).'),
    ('parcels', 'capacity_units', 'Homes the parcel can take: council estimate on audit parcels, zoning estimate on zoned-land parcels. Blank on consent parcels: their capacity is the consented units.'),
    ('parcels', 'capacity_basis', 'How capacity is set.'),
    ('parcels', 'developable_area_ha', 'Audit parcels: the council\u2019s net developable area, the basis of its capacity estimate. Consent parcels: mapped area.'),
    ('parcels', 'mapped_area_ha', 'Area of the polygon as drawn. Larger than the developable area where the council netted off roads, open space or constrained land.'),
    ('parcels', 'register_status', 'Status in the council audit file (audit parcels).'),
    ('parcels', 'plan_name / zone_gzt / zoning / phase', 'Zoned-land parcels: development plan or LAP, national zoning type, plan zoning name, and Phase 2 flag.'),
    ('parcels', 'density_tier / density_dph / density_basis', 'Zoned-land parcels: area type, homes per hectare used, and where the figure comes from (Limerick permitted schemes).'),
    ('parcels', 'rzlt_2027_share', 'Share of the parcel on the Residential Zoned Land Tax draft map 2027 (land the council considers serviced and vacant or idle).'),
    ('parcels', 'geod_addresses_now / geod_new_since_2019 / geod_extract', 'GeoDirectory residential addresses inside the parcel now / created since 2019, and the extract date. A rise on a parcel with no permission means building without a linked consent.'),
    ('parcels', 'catchment / catchment_type / catchment_share / catchment_basis', 'Study catchment the parcel overlaps most and the share inside it. Parcels outside every catchment go to a key town or large village when zoned in its local area plan, within 500 m of it, or named in the scheme and within 2 km (catchment_share 0, catchment_basis says which). Otherwise Rest of county.'),
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
    ('parcel_permissions', 'status_cis / status_source', 'Status as CIS and building control give it, and where the current status comes from. GeoDirectory moves a scheme to Complete when new built addresses reach 95% of its units.'),
    ('parcel_permissions', 'geod_new_built / geod_new_undercon', 'GeoDirectory residential addresses created since the application was received (for an extension of duration, since 1 January of the parent permission year), inside the permission boundary and its parcel: built / flagged under construction. Each address credited to one permission.'),
    ('parcel_permissions', 'geod_extract / geod_suggestion', 'Date of the latest address in the GeoDirectory extract used, and what it suggests (applied, or check).'),
    ('parcel_permissions', 'mix_source / mix_studio … mix_5plus', 'Bedroom mix of the permission and where it comes from (CIS, register description, or planning file documents such as planner\u2019s reports and schedules of accommodation). Blank where not known.'),
    ('parcel_summary', 'mix_* / units_with_known_mix', 'Bedroom mix summed over the parcel\u2019s counted permissions, and the units it covers (the rest have no known mix).'),
    ('parcel_permissions', 'geod_new_vacant', 'Of the built addresses credited to the permission, how many GeoDirectory marks vacant.'),
    ('parcels', 'density_estimate_units', 'Indicative homes for the parcel from its area x the local median density of permitted Limerick schemes (density_tier, density_dph). Filled for every parcel so all land can be compared on one basis. Not used in the supply totals; on consent parcels the consented units are the figure that counts.'),
    ('parcel_summary', 'capacity_used', 'The unit figure the parcel is planned on: council or zoning capacity where there is one, otherwise the consented units. Always filled where the parcel has units.'),
    ('active_parcels', '(all fields)', 'parcel_summary without Finished parcels: the land still to deliver homes. Use this layer for maps of future supply.'),
    ('parcel_summary', 'parcel_status', 'Finished (every counted home complete and no unconsented capacity left), Partly built, Consented – not built, No consent. Finished parcels stay in the file as delivery history with zero future supply; the active_parcels layer leaves them out.'),
    ('parcel_permissions', 'units_built', 'Homes built to date: all units of a completed scheme, otherwise the GeoDirectory built count (so part-built schemes are netted off future supply).'),
    ('parcel_summary', 'built_units / future_supply_units', 'Homes built to date on the parcel, and total supply minus homes built.'),
    ('parcel_summary', 'consented_units', 'Complete + under construction + permitted not started + stalled, from parcel_permissions where counts_toward_totals = Yes.'),
    ('parcel_summary', 'unconsented_capacity', 'Council capacity minus consented units, not below zero. Zero on consent parcels.'),
    ('parcel_summary', 'total_supply_units', 'Consented units + unconsented capacity. Sums across parcels with no double counting.'),
    
    ('rules', 'One permission, one parcel', 'Each permission row has exactly one parcel_id; parcels never overlap; totals are calculated, not typed.'),
    ('rules', 'New permission', 'Add a row to parcel_permissions. If it is on an existing parcel, use that parcel_id. If not, draw a parcel from the planning boundary (clipped to exclude existing parcels) with id PC-<ref>.'),
    ('rules', 'Amendment / repeat / extension', 'Add the row with counts_toward_totals = No unless it replaces the counted permission, in which case switch the old row to No and the new row to Yes.'),
    ('rules', 'GeoDirectory refresh', 'Each quarter: rerun the build with the new extract. Schemes reaching 95% built addresses move to Complete; partial ones and mismatches show in register_checks for a person to confirm.'),
    ('rules', 'Zoned-land parcels', 'Interim estimates. When a permission is granted on one, draw the consent parcel and cut it out of the zoned parcel (or link the permission to it if it covers it). Replace them with county audit parcels when the audit arrives.'),
    ('rules', 'Retiring a parcel', 'Do not delete. A parcel is Finished when all its counted homes are complete (CIS, or GeoDirectory addresses reach the unit count) and no council capacity is left; it drops out of active_parcels. Delete only a parcel created in error.'),
    ('rules', 'Refused / withdrawn', 'Do not add to parcel_permissions. Record land interest in notes if useful.'),
]
pyogrio.write_dataframe(pd.DataFrame(DICT, columns=['table', 'field', 'meaning']), OUT, layer='data_dictionary', driver='GPKG')

con = sqlite3.connect(OUT)
gcol = con.execute("SELECT column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns WHERE table_name='parcels'").fetchone()
pcols = [r[1] for r in con.execute('PRAGMA table_info(parcels)')]
s = lambda st: f"COALESCE(SUM(CASE WHEN pp.status = '{st}' THEN pp.units END), 0)"
cons_sql = f"({s('Complete')} + {s('Under construction')} + {s('Permitted – not started')} + {s('Stalled')})"
cap_sql = f"COALESCE(p.capacity_units, {cons_sql})"
con.execute(f"""CREATE VIEW parcel_summary AS SELECT {', '.join('p.' + c for c in pcols)},
  CAST({cap_sql} AS REAL) AS capacity_used,
  CAST({s('Complete')} AS REAL) AS complete_units, CAST({s('Under construction')} AS REAL) AS under_construction_units,
  CAST({s('Permitted – not started')} AS REAL) AS permitted_not_started_units, CAST({s('Stalled')} AS REAL) AS stalled_units,
  CAST({s('Expired – not started')} AS REAL) AS expired_units, CAST({s('In planning')} AS REAL) AS in_planning_units,
  CAST({cons_sql} AS REAL) AS consented_units,
  CAST(MAX({cap_sql} - {cons_sql}, 0) AS REAL) AS unconsented_capacity,
  CAST({cons_sql} + MAX({cap_sql} - {cons_sql}, 0) AS REAL) AS total_supply_units,
  CAST(COALESCE(SUM(CASE WHEN pp.status IN ('Complete', 'Under construction', 'Permitted – not started', 'Stalled') THEN pp.units_built END), 0) AS REAL) AS built_units,
  CAST({cons_sql} + MAX({cap_sql} - {cons_sql}, 0) - COALESCE(SUM(CASE WHEN pp.status IN ('Complete', 'Under construction', 'Permitted – not started', 'Stalled') THEN pp.units_built END), 0) AS REAL) AS future_supply_units,
  {' , '.join(f"CAST(COALESCE(SUM(pp.{c}), 0) AS REAL) AS {c}" for c in YC)},
  CAST(COUNT(pp.perm_id) AS REAL) AS permissions,
  {', '.join(f"CAST(COALESCE(SUM(pp.{c}), 0) AS REAL) AS {c}" for c in ['mix_studio', 'mix_1bed', 'mix_2bed', 'mix_3bed', 'mix_4bed', 'mix_5plus'])},
  CAST(COALESCE(SUM(CASE WHEN pp.mix_source NOT LIKE 'Not available%' THEN pp.units END), 0) AS REAL) AS units_with_known_mix,
  CASE WHEN {cons_sql} > 0 AND COALESCE(SUM(CASE WHEN pp.status IN ('Complete', 'Under construction', 'Permitted – not started', 'Stalled') THEN pp.units_built END), 0) >= {cons_sql} AND MAX({cap_sql} - {cons_sql}, 0) = 0 THEN 'Finished'
       WHEN COALESCE(SUM(CASE WHEN pp.status IN ('Complete', 'Under construction', 'Permitted – not started', 'Stalled') THEN pp.units_built END), 0) > 0 THEN 'Partly built' WHEN {cons_sql} > 0 THEN 'Consented – not built' ELSE 'No consent' END AS parcel_status,
  CAST(COALESCE(SUM(pp.geod_new_built), 0) AS REAL) AS geod_new_built, CAST(COALESCE(SUM(pp.geod_new_undercon), 0) AS REAL) AS geod_new_undercon,
  CAST(COALESCE(SUM(pp.geod_new_vacant), 0) AS REAL) AS geod_new_vacant,
  CASE WHEN p.capacity_units IS NOT NULL AND {cons_sql} > 1.1 * p.capacity_units THEN 'Consented above capacity' ELSE '' END AS flag
FROM parcels p LEFT JOIN parcel_permissions pp ON pp.parcel_id = p.parcel_id AND pp.counts_toward_totals = 'Yes'
GROUP BY p.fid""")
con.execute("CREATE VIEW active_parcels AS SELECT * FROM parcel_summary WHERE parcel_status <> 'Finished'")
for v in ['parcel_summary', 'active_parcels']:
    con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, srs_id) VALUES (?, 'features', ?, ?)", (v, v, gcol[2]))
    con.execute("INSERT INTO gpkg_geometry_columns (table_name, column_name, geometry_type_name, srs_id, z, m) VALUES (?, ?, ?, ?, 0, 0)",
                (v, gcol[0], gcol[1], gcol[2]))
sumcols = ['complete_units', 'under_construction_units', 'permitted_not_started_units', 'stalled_units', 'consented_units', 'expired_units',
           'in_planning_units', 'unconsented_capacity', 'total_supply_units', 'future_supply_units'] + YC + ['geod_new_built']
con.execute(f"""CREATE VIEW catchment_summary AS SELECT catchment_type, catchment, COUNT(*) AS parcels,
  CAST(SUM(developable_area_ha) AS REAL) AS developable_area_ha, {', '.join(f'CAST(SUM({c}) AS REAL) AS {c}' for c in sumcols)},
  CAST(SUM(CASE WHEN parcel_source LIKE 'Zoned land%' THEN unconsented_capacity ELSE 0 END) AS REAL) AS zoned_land_estimate_units
  FROM parcel_summary GROUP BY catchment_type, catchment""")
con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier) VALUES ('catchment_summary', 'attributes', 'catchment_summary')")
con.execute("""CREATE VIEW register_checks AS
  SELECT 'Permission linked to a parcel that does not exist' AS problem, pp.perm_id AS item, pp.parcel_id AS detail FROM parcel_permissions pp
    LEFT JOIN parcels p ON p.parcel_id = pp.parcel_id WHERE p.parcel_id IS NULL
  UNION ALL SELECT 'Planning reference counted more than once', planning_ref, COUNT(*) FROM parcel_permissions
    WHERE counts_toward_totals = 'Yes' AND planning_ref <> '' GROUP BY planning_ref HAVING COUNT(*) > 1
  UNION ALL SELECT 'Duplicate perm_id', perm_id, COUNT(*) FROM parcel_permissions GROUP BY perm_id HAVING COUNT(*) > 1
  UNION ALL SELECT 'Duplicate parcel_id', parcel_id, COUNT(*) FROM parcels GROUP BY parcel_id HAVING COUNT(*) > 1
  UNION ALL SELECT 'GeoDirectory: ' || geod_suggestion, perm_id, parcel_id FROM parcel_permissions
    WHERE geod_suggestion <> '' AND geod_suggestion NOT LIKE '%applied'
  UNION ALL SELECT 'New homes (GeoDirectory, since 2019) on a parcel with no linked permission', p.parcel_id, p.geod_new_since_2019 FROM parcels p
    WHERE p.geod_new_since_2019 >= 5 AND NOT EXISTS (SELECT 1 FROM parcel_permissions pp WHERE pp.parcel_id = p.parcel_id AND pp.counts_toward_totals = 'Yes')
  UNION ALL SELECT 'Finished parcel: over 10% of its new homes vacant on GeoDirectory', parcel_id, geod_new_vacant FROM parcel_summary
    WHERE parcel_status = 'Finished' AND geod_new_vacant > 0.1 * geod_new_built
  UNION ALL SELECT 'GeoDirectory addresses on parcel reach the consented units but parcel not Finished', parcel_id, geod_new_built FROM parcel_summary
    WHERE parcel_status <> 'Finished' AND consented_units > 0 AND geod_new_built >= consented_units
  UNION ALL SELECT 'Consent parcel with no counted permission', p.parcel_id, '' FROM parcels p
    WHERE p.parcel_source LIKE 'Planning consent%' AND NOT EXISTS (SELECT 1 FROM parcel_permissions pp WHERE pp.parcel_id = p.parcel_id AND pp.counts_toward_totals = 'Yes')""")
con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier) VALUES ('register_checks', 'attributes', 'register_checks')")
con.commit()
chk = con.execute('SELECT problem, COUNT(*) FROM register_checks GROUP BY problem').fetchall()
v = con.execute('SELECT SUM(consented_units), SUM(unconsented_capacity), SUM(total_supply_units), COUNT(*) FROM parcel_summary').fetchone()
con.close()
print('checks', chk, 'view totals', v)
# ------------------------------------------------------------------ GeoDirectory new-build clusters outside every parcel
# Homes being built or recently built where the register has no parcel: a permission we are missing, a scheme
# under the CIS threshold, or one-off houses. Clusters of CLUSTER_MIN+ new addresses (created since 2019).
CL = gpd.GeoDataFrame(columns=['cluster_id', 'new_addresses', 'built', 'under_construction', 'streets', 'first_created',
                               'last_created', 'register_applications', 'geometry'], geometry='geometry', crs=ITM)
if GD is not None:
    allp = unary_union(list(parcels.geometry)).buffer(5)
    nw = GD[(GD.created >= '2019-01-01') & ~GD.within(allp)]
    blobs = gpd.GeoDataFrame(geometry=list(unary_union(list(nw.buffer(30))).geoms) if len(nw) else [], crs=ITM)
    nw = gpd.sjoin(nw, blobs.reset_index(names='blob'), predicate='within')
    SITES = gpd.read_file('in_pp_full/sites.gpkg').to_crs(ITM)
    SITES['ref'] = SITES.ApplicationNumber.astype(str)
    SITES['u'] = pd.to_numeric(SITES.NumResidentialUnits, errors='coerce').fillna(0)
    rows = []
    for b_, g in nw.groupby('blob'):
        if len(g) < CLUSTER_MIN:
            continue
        hull = g.unary_union.convex_hull.buffer(10)
        apps = SITES[SITES.intersects(hull) & SITES.u.ge(2) & SITES.Decision.isin(['CONDITIONAL', 'UNCONDITIONAL'])]
        rows.append(dict(new_addresses=len(g), built=int(g.under_cons.ne('Y').sum()), under_construction=int(g.under_cons.eq('Y').sum()),
                         streets=', '.join(g.thoroughfa.fillna('').value_counts().index[:3]), first_created=g.created.min().strftime('%Y-%m-%d'),
                         last_created=g.created.max().strftime('%Y-%m-%d'),
                         register_applications=', '.join(f'{r.ref} ({int(r.u)})' for r in apps.sort_values('u', ascending=False).itertuples())[:250],
                         geometry=hull))
    if rows:
        CL = gpd.GeoDataFrame(rows, crs=ITM).sort_values('new_addresses', ascending=False).reset_index(drop=True)
        CL.insert(0, 'cluster_id', [f'GD-{i + 1:03d}' for i in range(len(CL))])
        CL['scope'] = np.where(where(CL.geometry, NBH, 'nbhd').notna().values, 'City', 'County')
        CL['relevance'] = np.where((CL.under_construction > 0) | (CL.last_created >= '2024-01-01'),
                                   'Recent or active build – check for a missing permission', 'Built before the tracker window – history only')
    CL.to_file(OUT, layer='geod_new_build_outside_parcels', driver='GPKG')
    print('new-build clusters outside parcels:', len(CL), 'addresses', int(CL.new_addresses.sum()) if len(CL) else 0)
if CA is not None:
    CA[['catchment', 'catchment_type', 'CSO_LEA', 'geometry']].to_file(OUT, layer='ref_study_catchments', driver='GPKG')
pd.to_pickle({'parcels': parcels, 'pp': pp, 'T': T, 'YC': YC, 'CL': CL}, 'land_register.pkl')
