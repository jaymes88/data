"""Limerick opportunity sites register: eyeballed sites that may be underused, for the council to investigate against the
2040 housing shortfall. Kept separate from the land register; homes here are indicative and are not part of supply.

Input: the analyst's polygons (in_opp/opp.gpkg: id, site, area, opp_area). Output: Limerick_Opportunity_Sites.gpkg, layer
opportunity_sites, with desk-based fields filled from data already held and blank fields (with pick-lists) for the
investigation. Fields marked (auto) are recalculated on each run; the rest are for people to fill in.
"""
import re, sqlite3, datetime
import numpy as np, pandas as pd, geopandas as gpd, openpyxl
from shapely.ops import unary_union

ITM = 2157
IN, OUT = 'in_opp/opp.gpkg', 'Limerick_Opportunity_Sites.gpkg'
TODAY = datetime.date.today().isoformat()
NET = 0.91          # developable share used in the land register (council city audit ratio); editable per site

import os, sys
MASTER = sys.argv[1] if len(sys.argv) > 1 else None     # a returned copy of the register: its entries are kept
C = gpd.read_file('Limerick_Housing_Land_Register.gpkg', layer='ref_study_catchments').to_crs(ITM)
if MASTER:
    M = gpd.read_file(MASTER, layer='opportunity_sites').to_crs(ITM).reset_index(drop=True)
    M['geometry'] = M.geometry.make_valid().buffer(0)
    new = M.opp_id.isna() | M.opp_id.astype(str).str.strip().isin(['', 'nan', 'None'])
    # sites added without a settlement: the catchment they sit in, else the nearest existing site's settlement (within
    # 1.5 km), else the nearest catchment
    for i in M.index[new & (M.settlement.isna() | M.settlement.astype(str).str.strip().eq(''))]:
        g = M.at[i, 'geometry']; p = g.representative_point()
        inside = C[C.contains(p)]
        old = M[~new]
        d = old.distance(p)
        if len(inside):
            st = inside.catchment.iloc[0]
            st = {'Moroe': 'Murroe'}.get(st, st)
        elif len(d) and d.min() <= 1500:
            st = old.at[d.idxmin(), 'settlement']
        else:
            st = C.loc[C.distance(p).idxmin(), 'catchment']
        M.at[i, 'settlement'] = st
    M['_new'] = new
    rail = M.site_category.fillna('').str.startswith('Rail')
    O = gpd.GeoDataFrame(dict(id=pd.to_numeric(M.source_id, errors='coerce'),
                              site=M.settlement + np.where(rail, ' EXP', ''),
                              area=M.area / 1e4,
                              opp_area=np.where(M.council_opportunity_site.eq('Yes'), 'Y, ' + M.council_reference.fillna(''), ''),
                              geometry=M.geometry), crs=ITM)
else:
    O = gpd.read_file(IN).to_crs(ITM).reset_index(drop=True)
    O['geometry'] = O.geometry.make_valid().buffer(0)

# ---------------------------------------------------------------- identity and location
raw = O.site.fillna('').str.strip()
O['expansion'] = raw.str.contains(r'\bEXP\b', case=False)
name = raw.str.replace(r'\s*\bEXP\b', '', regex=True, case=False).str.strip()
name = name.replace({'Singland/Garrowen': 'Singland/Garryowen'})
O['settlement'] = name
O['site_category'] = np.where(O.expansion, 'Rail corridor new town (long term)', 'Opportunity site')   # 'EXP' sites: new towns on rail lines
O['_n'] = O.groupby('settlement').cumcount() + 1
pref = 'OPP-' + O.settlement.str.upper().str.replace(r'[^A-Z]', '', regex=True).str[:12] + '-'
O['opp_id'] = pref + O._n.astype(str).str.zfill(3)
if MASTER:                                                     # existing IDs never change; new sites continue the numbering
    O.loc[~M._new, 'opp_id'] = M.loc[~M._new, 'opp_id']
    for i in O.index[M._new]:
        used = O.loc[O.opp_id.str.startswith(pref[i]) & ~M._new, 'opp_id'].tolist() + O.loc[:i - 1][M._new.loc[:i - 1]].opp_id.tolist()
        n = max([int(x.rsplit('-', 1)[1]) for x in used if x.startswith(pref[i])] + [0]) + 1
        O.at[i, 'opp_id'] = pref[i] + str(n).zfill(3)
    assert O.opp_id.is_unique
O['source_id'] = O.id.map(lambda v: '' if pd.isna(v) else str(int(v)))

LEA = gpd.read_file('Limerick_Housing_Supply.gpkg', layer='ref_local_electoral_areas').to_crs(ITM)
pt = gpd.GeoDataFrame(geometry=O.representative_point(), crs=ITM)
j = gpd.sjoin(pt, C[['catchment', 'catchment_type', 'geometry']], how='left', predicate='within')
j = j[~j.index.duplicated()]
# the analyst's settlement label decides the catchment where it names one (sites just past a catchment line still belong
# to the town); otherwise the catchment the site sits in; otherwise outside the study catchments
ALIAS = {'Murroe': 'Moroe', 'Kilfinane': 'Kilfinnane', 'Southill': 'Southhill'}
ctype = C.set_index('catchment').catchment_type.to_dict()
lab = O.settlement.map(lambda s: ALIAS.get(s, s))
O['catchment'] = np.where(lab.isin(ctype.keys()), lab, j.catchment.fillna('Outside study catchments'))
O['catchment_type'] = O.catchment.map(ctype).fillna('Outside study catchments')
# rail-corridor new towns are a longer-term strategy: kept out of the neighbourhood and settlement totals
O.loc[O.expansion, ['catchment', 'catchment_type']] = 'Rail corridor (long term)'
jl = gpd.sjoin(pt, LEA[['ENGLISH', 'geometry']], how='left', predicate='within')
O['lea'] = jl[~jl.index.duplicated()].ENGLISH.str.replace(' LEA-\\d+', '', regex=True).str.title().fillna('')
O['area_ha'] = (O.area / 1e4).round(3)

oa = O.opp_area.fillna('').str.strip()
O['council_opportunity_site'] = np.where(oa.str.match(r'^(Y\b|Opportunity)', case=False), 'Yes', 'Not known')
O['council_reference'] = oa.str.replace(r'^Y\s*,?\s*', '', regex=True).where(O.council_opportunity_site.eq('Yes'), '')
O['identified_by'] = 'Analyst (desk review)'
O['identified_on'] = '2026-10'

# ---------------------------------------------------------------- what is there now (auto where possible)
O['current_use'] = 'Not yet recorded'
# the review targets infill: town and village opportunity sites start as Infill (to confirm); city sites are left to record,
# since they may be infill or brownfield
O['site_type'] = 'Not yet recorded'
O.loc[O.catchment_type.isin(['Key town', 'Large village']), 'site_type'] = 'Infill'
G = gpd.read_file('in_geodir/limerick_geod_residential_points.gpkg', columns=['vacant', 'derelict']).to_crs(ITM)
gj = gpd.sjoin(G, O[['opp_id', 'geometry']], predicate='within')
O['geod_addresses'] = O.opp_id.map(gj.groupby('opp_id').size()).fillna(0).astype(int)
O['geod_vacant'] = O.opp_id.map(gj[gj.vacant.eq('Y')].groupby('opp_id').size()).fillna(0).astype(int)
O['geod_derelict'] = O.opp_id.map(gj[gj.derelict.eq('Y')].groupby('opp_id').size()).fillna(0).astype(int)

R = gpd.read_file('Limerick_Housing_Land_Register.gpkg', layer='parcels').to_crs(ITM)
ov_ids, ov_share = [], []
for g in O.geometry:
    hit = R[R.intersects(g)]
    a = hit.geometry.intersection(g).area
    keep = a[a > 0.05 * g.area]
    ov_ids.append('; '.join(hit.loc[keep.index, 'parcel_id']))
    ov_share.append(round(min(keep.sum() / g.area, 1), 2) if len(keep) else 0.0)
O['overlaps_land_register'] = ov_ids
O['land_register_share'] = ov_share

# ---------------------------------------------------------------- planning position (auto)
Z = gpd.read_file('in_zoning/gzt.gpkg').to_crs(ITM)
ZA = gpd.read_file('in_zoning/askeaton_zoning.gpkg').to_crs(ITM)
ZA = gpd.GeoDataFrame(dict(ZONE_GZT=np.where(ZA.zone.str.startswith('RDA'), 'R1', 'R3'), ZONE_ORIG=ZA['desc'], geometry=ZA.geometry), crs=ITM)
Z = pd.concat([Z[['ZONE_GZT', 'ZONE_ORIG', 'geometry']], ZA], ignore_index=True)
def resi(code, orig):
    code, orig = str(code), str(orig).lower()
    if code.startswith('R'): return 'Yes'
    if code.startswith('M') or 'centre' in orig or 'mixed' in orig: return 'Mixed use'
    return 'No'
zon, zall, rz, rshare = [], [], [], []
for g in O.geometry:
    h = Z[Z.intersects(g)].copy()
    h['a'] = h.geometry.intersection(g).area
    h = h[h.a > 0.02 * g.area].sort_values('a', ascending=False)
    if h.empty:
        zon.append('Unzoned'); zall.append(''); rz.append('No (unzoned)'); rshare.append(0.0); continue
    zon.append(h.ZONE_ORIG.iloc[0])
    zall.append('; '.join(f'{z} {a / g.area:.0%}' for z, a in h.groupby('ZONE_ORIG').a.sum().sort_values(ascending=False).items()))
    kinds = h.assign(k=[resi(c, o) for c, o in zip(h.ZONE_GZT, h.ZONE_ORIG)]).groupby('k').a.sum()
    rz.append(kinds.idxmax() if kinds.max() >= 0.5 * g.area else 'Partly')
    rshare.append(round(kinds.get('Yes', 0) / g.area, 2))
O['zoning'] = zon
O['zoning_detail'] = zall
O['residential_permitted_in_zone'] = rz
O['residential_zoned_share'] = rshare
RZ = unary_union(list(gpd.read_file('in_zoning/rzlt2027.gpkg').to_crs(ITM).geometry))
O['rzlt_share'] = [round(g.intersection(RZ).area / g.area, 2) for g in O.geometry]

PL = gpd.read_file('in_pp_full/sites.gpkg').to_crs(ITM)
PL = PL[PL.geometry.notna() & ~PL.geometry.is_empty]
ph, pn = [], []
for g in O.geometry:
    h = PL[PL.intersects(g)].copy()
    h = h[h.geometry.intersection(g).area > 0.2 * h.area.clip(lower=1)]          # the application site lies mostly on this site
    pn.append(len(h))
    if h.empty:
        ph.append(''); continue
    r = h.sort_values('ReceivedDate').iloc[-1]
    dec = str(r.Decision or r.ApplicationStatus or '').strip().title()
    units = f', {int(r.NumResidentialUnits)} homes' if pd.notna(r.NumResidentialUnits) and r.NumResidentialUnits > 0 else ''
    ph.append(f"{r.ApplicationNumber} ({pd.Timestamp(r.ReceivedDate):%Y}), {dec}{units}: {str(r.DevelopmentDescription)[:90]}")
O['planning_applications'] = pn
O['latest_application'] = ph
O['derelict_or_vacant_sites_register'] = 'Not checked'
for c in ['flood_zone', 'protected_structure_or_aca', 'archaeology', 'ecology', 'access', 'contamination']:
    O['constraint_' + c] = 'Not checked'

# ---------------------------------------------------------------- constraints from the council layers (auto), in_constraints/
# Flood Zones A and B, Record of Protected Structures (county Oct 2026 layer + 2010 City Development Plan),
# ACAs (2010 city and county development plans), Derelict Sites Register (Oct 2026), GeoDirectory vacant residential points.
CN = 'in_constraints/'
if os.path.exists(CN + 'flooda.gpkg'):
    site = O[['opp_id', 'geometry']].copy(); site['a'] = site.area
    SITEBOX = site.geometry.buffer(20).union_all()
    # flood: per site, Zone A part and the part of Zone B outside Zone A (snap-rounded overlay copes with invalid flood polygons)
    import shapely
    def parts(layer):
        L_ = gpd.read_file(CN + layer, bbox=tuple(site.total_bounds)).to_crs(ITM).geometry
        L_ = L_[L_.intersects(SITEBOX)].reset_index(drop=True); ix = L_.sindex
        out = []
        for g in site.geometry:
            k = ix.query(g, predicate='intersects')
            bits = [p for q in k for p in shapely.get_parts(shapely.intersection(L_[q], g, grid_size=0.01)) if p.geom_type == 'Polygon']
            out.append(shapely.union_all(bits, grid_size=0.01) if bits else shapely.Polygon())
        return out
    pa = parts('flooda.gpkg')
    O['flood_zone_a_share'] = [round(min(1, p.area / a), 3) if a else 0 for p, a in zip(pa, site.a)]
    if os.path.exists(CN + 'floodb.gpkg'):
        pb = parts('floodb.gpkg')
        O['flood_zone_b_share'] = [round(min(1, shapely.difference(b, p, grid_size=0.01).area / a), 3) if a else 0 for b, p, a in zip(pb, pa, site.a)]
    else:
        O['flood_zone_b_share'] = np.nan
    # protected structures: on the site, or within 50 m (setting)
    R = gpd.read_file(CN + 'rps.gpkg').to_crs(ITM)
    R['ref'] = np.where(R.reg_no.notna(), 'RPS ' + R.reg_no.astype('Int64').astype(str), R.rps_cpd_10.fillna('').str.replace('RSP', 'RPS'))
    R = R[R.ref.str.strip().ne('') & R.geometry.x.between(450000, 620000)]
    def refs(pts, dist):
        j = gpd.sjoin(pts[['ref', 'geometry']], site[['opp_id', 'geometry']].assign(geometry=site.buffer(dist)) if dist else site[['opp_id', 'geometry']],
                      predicate='within')
        return j.groupby('opp_id').ref.apply(lambda v: '; '.join(sorted(set(v), key=lambda t: (len(t), t))))
    on, near = refs(R, 0), refs(R, 50)
    O['rps_on_site'] = O.opp_id.map(on).fillna('')
    O['rps_within_50m'] = O.opp_id.map(near).fillna('')
    O['rps_on_site_count'] = O.rps_on_site.apply(lambda t: len(t.split('; ')) if t else 0)
    # ACAs
    A = gpd.read_file(CN + 'aca.gpkg').to_crs(ITM); A['geometry'] = A.geometry.make_valid()
    A['label'] = A.name.where(A.name.notna(), 'City ACA ' + A.pgid.astype(str) + ' (2010 City Development Plan)')
    x = gpd.overlay(site, A[['label', 'geometry']], how='intersection', keep_geom_type=True); x['s'] = x.area
    O['aca_share'] = O.opp_id.map(x.groupby('opp_id').s.sum() / site.set_index('opp_id').a).fillna(0).clip(0, 1).round(3)
    O['aca_name'] = O.opp_id.map(x.sort_values('s', ascending=False).groupby('opp_id').label.apply(lambda v: '; '.join(dict.fromkeys(v)))).fillna('')
    # Derelict Sites Register: entry point on the site or within 25 m (points are geocoded to the address)
    DS = gpd.read_file(CN + 'derelict_sites.gpkg').to_crs(ITM).rename(columns={'SITE ID': 'ref'})
    O['derelict_sites_register'] = O.opp_id.map(refs(DS, 25)).fillna('')
    # ACA parts named only by letter ("B: 19th & Early 20th Century Core") get the settlement in front
    part = O.aca_name.ne('') & ~O.aca_name.str.contains('ACA')
    O.loc[part, 'aca_name'] = O.settlement[part] + ' ACA, ' + O.aca_name[part]
    # vacants.gpkg (GeoDirectory vacant residential points) gives the same counts as geod_vacant, so it is not added again
    # judgement thresholds for the pick-list fields
    fab = O.flood_zone_a_share + O.flood_zone_b_share.fillna(0)
    O['constraint_flood_zone'] = np.select([(O.flood_zone_a_share >= 0.25) | (fab >= 0.5), fab > 0.01], ['Yes – significant', 'Yes – minor'], 'No')
    # heritage share: the part of the site in an ACA or within RPS_SETTING m of a protected structure (the RPS points mark the
    # building, not its curtilage), so one structure on a large site affects only the land around it
    RPS_SETTING = 30
    rb = R.buffer(RPS_SETTING); rix = rb.sindex; aix = A.sindex
    hs, rs = [], []
    for g, a in zip(site.geometry, site.a):
        rp = [shapely.intersection(rb.iloc[q], g, grid_size=0.01) for q in rix.query(g, predicate='intersects')]
        ap = [shapely.intersection(A.geometry.iloc[q], g, grid_size=0.01) for q in aix.query(g, predicate='intersects')]
        ru = shapely.union_all(rp, grid_size=0.01) if rp else shapely.Polygon()
        hu = shapely.union_all(rp + ap, grid_size=0.01) if rp or ap else shapely.Polygon()
        rs.append(round(min(1, ru.area / a), 3) if a else 0); hs.append(round(min(1, hu.area / a), 3) if a else 0)
    O['rps_setting_share'], O['heritage_share'] = rs, hs
    O['constraint_protected_structure_or_aca'] = np.select(
        [O.heritage_share >= 0.25, O.rps_within_50m.ne('') | (O.heritage_share > 0.01)], ['Yes – significant', 'Yes – minor'], 'No')
    O['derelict_or_vacant_sites_register'] = np.where(O.derelict_sites_register.ne(''), 'Yes', 'No')

# ---------------------------------------------------------------- indicative capacity (auto)
D = openpyxl.load_workbook('Limerick-HDS-2040-needs-model.xlsx', data_only=True)['Land at Council density']
dens = {D.cell(r, 1).value: (D.cell(r, 3).value, D.cell(r, 4).value) for r in range(7, 31)}
cent = C.copy(); cent['geometry'] = cent.representative_point()
dd, db = [], []
for i, r in O.iterrows():
    if r.catchment in dens:
        d, basis = dens[r.catchment]
        dd.append(round(d, 1)); db.append(f'Council density for {r.catchment}: {basis}')
    else:                                                      # outside the study catchments: nearest catchment's density
        near = cent.loc[cent.distance(r.geometry.representative_point()).idxmin(), 'catchment']
        d, basis = dens.get(near, (22, ''))
        if O.at[i, 'expansion']:
            d, basis = 35, 'Placeholder: no Council density for new rail towns; 35/ha (suburban / urban extension minimum) used'
        dd.append(round(d, 1)); db.append(f'Outside the study catchments: density of the nearest catchment ({near}) used' if 'placeholder' not in basis else basis)
O['density_assumed'] = dd
O['density_basis'] = db
O['developable_share'] = NET
O['indicative_homes'] = (O.area_ha * O.developable_share * O.density_assumed).round(0)
O['indicative_homes_not_in_register'] = (O.indicative_homes * (1 - O.land_register_share)).round(0)
O['capacity_confidence'] = 'Low'

# ---------------------------------------------------------------- deliverability (to be filled in)
O['ownership_status'] = 'Not yet checked'
O['ownership_type'] = 'Not yet checked'
O['folio_ref'] = ''
O['energy'] = ''
O['ue_water'] = ''
# wastewater status the council gives by settlement in its HDAP 2027-2030 submission (Sept 2026); blank elsewhere
WW = {'Askeaton': 'Red', 'Croagh': 'Red', 'Shanagolden': 'Red', 'Murroe': 'Red', 'Oola': 'Red', 'Elton': 'Red',
      'Adare': 'Amber', 'Croom': 'Amber', 'Ballingarry': 'Amber', 'Pallaskenry': 'Amber', 'Cappamore': 'Amber', 'Doon': 'Amber',
      'Kilfinnane': 'Amber'}
O['ue_wastewater'] = O.settlement.map(lambda s: f'{WW[s]} (HDAP 2027–2030, settlement level)' if s in WW else '')
O['likely_route'] = 'Not yet assessed'
O['timeframe'] = np.where(O.expansion, '10+ years', 'Not yet assessed')
O['barriers'] = ''

# ---------------------------------------------------------------- tracking
O['status'] = 'Identified'
O['priority'] = 'Not set'
O['next_action'] = ''
O['last_updated'] = TODAY
O['updated_by'] = ''
O['notes'] = np.where(O.opp_area.fillna('').str.contains('green space', case=False), 'Council identifies it for green space', '')

cols = ['opp_id', 'source_id', 'site_category', 'settlement', 'catchment', 'catchment_type', 'lea', 'area_ha',
        'council_opportunity_site', 'council_reference', 'identified_by', 'identified_on',
        'current_use', 'site_type', 'geod_addresses', 'geod_vacant', 'geod_derelict', 'overlaps_land_register', 'land_register_share',
        'zoning', 'zoning_detail', 'residential_permitted_in_zone', 'residential_zoned_share', 'rzlt_share',
        'planning_applications', 'latest_application', 'derelict_or_vacant_sites_register'] + \
       ['derelict_sites_register', 'flood_zone_a_share', 'flood_zone_b_share', 'rps_on_site', 'rps_on_site_count', 'rps_within_50m', 'rps_setting_share', 'aca_name', 'aca_share', 'heritage_share'] + \
       ['constraint_' + c for c in ['flood_zone', 'protected_structure_or_aca', 'archaeology', 'ecology', 'access', 'contamination']] + \
       ['density_assumed', 'density_basis', 'developable_share', 'indicative_homes', 'indicative_homes_not_in_register', 'capacity_confidence',
        'ownership_status', 'ownership_type', 'folio_ref', 'energy', 'ue_water', 'ue_wastewater', 'likely_route', 'timeframe', 'barriers',
        'status', 'priority', 'next_action', 'last_updated', 'updated_by', 'notes']
# entries made in the returned register are kept over the defaults (auto fields are always recalculated)
MANUAL = ['site_category', 'council_opportunity_site', 'council_reference', 'identified_by', 'identified_on', 'current_use', 'site_type',
          'derelict_or_vacant_sites_register', 'constraint_flood_zone', 'constraint_protected_structure_or_aca', 'constraint_archaeology',
          'constraint_ecology', 'constraint_access', 'constraint_contamination', 'developable_share', 'capacity_confidence',
          'ownership_status', 'ownership_type', 'folio_ref', 'energy', 'ue_water', 'ue_wastewater', 'likely_route', 'timeframe',
          'barriers', 'status', 'priority', 'next_action', 'updated_by', 'notes']
if MASTER:
    for c in MANUAL:
        if c in M:
            v = M[c]
            ok = v.notna() & ~v.astype(str).str.strip().isin(['', 'nan', 'None', 'Not checked'])
            O.loc[ok, c] = v[ok]
    O.loc[M._new, 'identified_on'] = TODAY[:7]
    O['developable_share'] = pd.to_numeric(O.developable_share, errors='coerce').fillna(NET)
    O['indicative_homes'] = (O.area_ha * O.developable_share * O.density_assumed).round(0)
    O['indicative_homes_not_in_register'] = (O.indicative_homes * (1 - O.land_register_share)).round(0)
OUTG = gpd.GeoDataFrame(O[cols + ['geometry']], geometry='geometry', crs=ITM)
OUTG.to_file(OUT, layer='opportunity_sites', driver='GPKG')

# ---------------------------------------------------------------- pick-lists (GeoPackage schema extension: QGIS shows drop-downs)
LISTS = {
    'site_category': ['Opportunity site', 'Rail corridor new town (long term)'],
    'council_opportunity_site': ['Yes', 'No', 'Not known'],
    'current_use': ['Not yet recorded', 'Vacant land', 'Vacant or derelict building', 'Surface car park', 'Yard / industrial',
                    'Low-density commercial', 'Backland', 'Underused open space', 'Agricultural', 'Other'],
    'site_type': ['Not yet recorded', 'Brownfield', 'Infill', 'Greenfield'],
    'derelict_or_vacant_sites_register': ['Not checked', 'Yes', 'No'],
    'capacity_confidence': ['Low', 'Medium', 'High'],
    'ownership_status': ['Not yet checked', 'Single owner', 'Multiple owners', 'Disputed / unclear', 'Unknown after checking'],
    'ownership_type': ['Not yet checked', 'Council', 'Other public body', 'Approved housing body', 'Private', 'Mixed', 'Unknown'],
    'likely_route': ['Not yet assessed', 'Council acquisition / CPO', 'Land Development Agency', 'Approved housing body', 'Private',
                     'Funding-led (URDF, Croí Cónaithe)', 'Not viable'],
    'timeframe': ['Not yet assessed', '0–5 years', '5–10 years', '10+ years'],
    'status': ['Identified', 'Desk review done', 'Ownership checked', 'Under investigation', 'Brought forward', 'Not pursued'],
    'priority': ['Not set', 'High', 'Medium', 'Low'],
}
CONSTRAINT = ['Not checked', 'No', 'Yes – minor', 'Yes – significant']
for c in ['flood_zone', 'protected_structure_or_aca', 'archaeology', 'ecology', 'access', 'contamination']:
    LISTS['constraint_' + c] = CONSTRAINT
con = sqlite3.connect(OUT)
con.executescript("""
CREATE TABLE IF NOT EXISTS gpkg_data_columns (table_name TEXT NOT NULL, column_name TEXT NOT NULL, name TEXT, title TEXT,
  description TEXT, mime_type TEXT, constraint_name TEXT, CONSTRAINT pk_gdc PRIMARY KEY (table_name, column_name));
CREATE TABLE IF NOT EXISTS gpkg_data_column_constraints (constraint_name TEXT NOT NULL, constraint_type TEXT NOT NULL, value TEXT,
  min NUMERIC, min_is_inclusive BOOLEAN, max NUMERIC, max_is_inclusive BOOLEAN, description TEXT,
  CONSTRAINT gdcc_ntv UNIQUE (constraint_name, constraint_type, value));
""")
for ext in [('gpkg_data_columns', None), ('gpkg_data_column_constraints', None)]:
    con.execute("INSERT OR IGNORE INTO gpkg_extensions (table_name, column_name, extension_name, definition, scope) VALUES (?, ?, 'gpkg_schema', 'http://www.geopackage.org/spec/#extension_schema', 'read-write')", ext)
for col, vals in LISTS.items():
    cname = 'list_' + col
    con.execute('DELETE FROM gpkg_data_column_constraints WHERE constraint_name = ?', (cname,))
    for v in vals:
        con.execute("INSERT INTO gpkg_data_column_constraints (constraint_name, constraint_type, value, description) VALUES (?, 'enum', ?, ?)", (cname, v, v))
    con.execute('INSERT OR REPLACE INTO gpkg_data_columns (table_name, column_name, name, constraint_name) VALUES (?, ?, ?, ?)',
                ('opportunity_sites', col, col, cname))
con.commit(); con.close()

# ---------------------------------------------------------------- summary by settlement (non-spatial layer in the same file)
T = OUTG.drop(columns='geometry').assign(homes_where_zoning_allows=lambda d: d.indicative_homes_not_in_register.where(
    d.residential_permitted_in_zone.isin(['Yes', 'Mixed use']), 0))
S = T.groupby(['catchment_type', 'catchment', 'site_category']).agg(homes_where_zoning_allows=('homes_where_zoning_allows', 'sum'),
    sites=('opp_id', 'size'), area_ha=('area_ha', 'sum'), indicative_homes=('indicative_homes', 'sum'),
    indicative_homes_not_in_register=('indicative_homes_not_in_register', 'sum'),
    council_named=('council_opportunity_site', lambda s: (s == 'Yes').sum())).round(1).reset_index()
import pyogrio
pyogrio.write_dataframe(S, OUT, layer='summary_by_catchment', driver='GPKG')
pd.set_option('display.width', 220, 'display.max_rows', 80)
print(len(OUTG), 'sites ->', OUT)
print(S.to_string())
print(OUTG.residential_permitted_in_zone.value_counts().to_dict(), 'overlapping register:', int((OUTG.land_register_share > 0).sum()))
