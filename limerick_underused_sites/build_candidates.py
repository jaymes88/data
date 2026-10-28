"""Rank underused commercial buildings in Limerick from the NAV valuation export and OSM footprints.

usage: python build_candidates.py <valuation.geojson> <osm_buildings.gpkg> <out.gpkg>
Everything is ITM (EPSG:2157). Transport is deliberately not scored.
"""
import json, re, sys
import numpy as np, geopandas as gpd, pandas as pd
from shapely.geometry import Point

val_path, bld_path, out_path = sys.argv[1:4]
CENTRE = Point(557400, 656900)  # approx O'Connell St, for a distance column only

# --- valuation records -> one row per property --------------------------------
rows = []
for x in json.load(open(val_path))['features']:
    c = x['geometry']['coordinates']
    if c[0] is None or c[1] is None:
        continue
    p = dict(x['properties']); rep = p.pop('ValuationReport') or []
    fu = lambda r: (r.get('FloorUse') or '').upper()
    lv = []
    for r in rep:
        try: lv.append(int(str(r['Level']).strip()))
        except (ValueError, TypeError): pass
    p['floor_area'] = sum(r.get('Area') or 0 for r in rep if 'CAR' not in fu(r) and 'YARD' not in fu(r) and 'CANOPY' not in fu(r))
    p['yard_area'] = sum(r.get('Area') or 0 for r in rep if 'YARD' in fu(r))
    p['max_level'] = max(lv) if lv else np.nan
    p['geometry'] = Point(c)
    rows.append(p)
v = gpd.GeoDataFrame(rows, crs=2157)

# --- footprints ----------------------------------------------------------------
b = gpd.read_file(bld_path).reset_index(drop=True)
b['bid'] = b.index
b['footprint_m2'] = b.geometry.area

# attach each valuation point to the building it sits in, else nearest within 25 m
j = gpd.sjoin_nearest(v, b[['bid', 'geometry']], how='inner', max_distance=25, distance_col='snap_m')
j = j.sort_values('snap_m').loc[~j.index.duplicated()]

def typology(u, cat):
    u = u.upper()
    if re.search(r'CAR PARK|YARD|VACANT|DEPOT|SERVICE STATION|MOTOR WASH', u): return 'yard / car park / vacant / fuel'
    if re.search(r'WAREHOUSE|WORKSHOP|FACTORY|STORE|MOTOR SHOWROOM|SHOWROOM \(INDUSTRIAL\)|INDUSTRIAL', u) and cat != 'RETAIL (SHOPS)': return 'warehouse / workshop / store'
    if cat == 'RETAIL (WAREHOUSE)': return 'retail warehouse'
    if cat == 'OFFICE': return 'office'
    if cat == 'RETAIL (SHOPS)': return 'shop'
    return 'other'
v_typ = {'yard / car park / vacant / fuel': 30, 'warehouse / workshop / store': 25, 'retail warehouse': 18, 'shop': 5, 'office': 5, 'other': 0}
j['typ'] = [typology(u, c) for u, c in zip(j.uses, j.category)]
j['typ_pts'] = j.typ.map(v_typ)
j['nav_m2'] = np.where(j.floor_area > 0, j.valuation / j.floor_area.replace(0, np.nan), np.nan)
j['pub_year'] = pd.to_datetime(j.publicationdate, format='%d/%m/%Y', errors='coerce').dt.year

excluded_cats = {'HEALTH', 'LEISURE', 'UTILITY', 'MINERALS', 'HOSPITALITY', 'NON-LIST', 'NON-LIST EXEMPT', 'CENTRAL VALUATION LIST', 'CHECK CATEGORY'}
j['excluded_cat'] = j.category.isin(excluded_cats)

g = j.groupby('bid').agg(
    n_records=('propertynumber', 'count'),
    address=('address', 'first'),
    names=('name', lambda s: '; '.join(sorted(set(map(str, s)))[:4])),
    uses=('uses', lambda s: '; '.join(sorted(set(s))[:4])),
    categories=('category', lambda s: '; '.join(sorted(set(s)))),
    typology=('typ', lambda s: s.value_counts().index[0]),
    typ_pts=('typ_pts', 'max'),
    floor_area_m2=('floor_area', 'sum'),
    yard_area_m2=('yard_area', 'sum'),
    max_level=('max_level', 'max'),
    total_nav=('valuation', 'sum'),
    oldest_pub=('pub_year', 'min'), newest_pub=('pub_year', 'max'),
    any_excluded=('excluded_cat', 'any'), all_excluded=('excluded_cat', 'all'),
    property_numbers=('propertynumber', lambda s: ','.join(map(str, s))),
).reset_index()
s = b.merge(g, on='bid', how='inner')  # keeps building geometry
s['nav_per_m2'] = np.where(s.floor_area_m2 > 0, s.total_nav / s.floor_area_m2.replace(0, np.nan), np.nan)
s['floor_to_footprint'] = s.floor_area_m2 / s.footprint_m2
s['dist_centre_m'] = s.geometry.centroid.distance(CENTRE).round(0)

# --- neighbourhood: share of residential buildings within 150 m ----------------
res_tags = {'house', 'apartments', 'residential', 'terrace', 'semidetached_house', 'detached', 'bungalow'}
bc = b.copy(); bc['geometry'] = bc.geometry.centroid
bc['is_res'] = bc.building.isin(res_tags)
sc = s[['bid', 'geometry']].copy(); sc['geometry'] = sc.geometry.centroid
sc['geometry'] = sc.geometry.buffer(150)
nb = gpd.sjoin(bc[['is_res', 'geometry']], sc, predicate='within')
nbg = nb.groupby('bid').agg(n_bld_150m=('is_res', 'size'), n_res_150m=('is_res', 'sum'))
s = s.merge(nbg, on='bid', how='left').fillna({'n_bld_150m': 0, 'n_res_150m': 0})
s['res_share_150m'] = (s.n_res_150m / s.n_bld_150m.replace(0, np.nan)).round(2)

# --- hard exclusions -----------------------------------------------------------
res_self = s.building.isin(res_tags)
protected = s.wikidata.notna() | s.wikipedia.notna()
s['exclude_reason'] = np.select(
    [s.building.eq('construction'), res_self, protected, s.all_excluded, s.footprint_m2 < 250, s.floor_area_m2 <= 0,
     s.uses.str.contains('MULTISTOREY', case=False), (s.floor_to_footprint < 0.1) & (s.yard_area_m2 <= 0) & (s.typology != 'yard / car park / vacant / fuel')],
    ['tagged under construction', 'already residential', 'wikidata/wikipedia tagged (likely landmark)', 'hospitality/health/leisure/utility only', 'footprint under 250 m2', 'no floor area in valuation',
     'multistorey car park (active)', 'floor area under 10% of footprint (likely wrong building match)'],
    default='')

# --- score (0-100) ---------------------------------------------------------------
def pct_rank_inv(x): return 1 - x.rank(pct=True)
cand = s[s.exclude_reason == ''].copy()
f2f = cand.floor_to_footprint
# intensity: low floor area per footprint, single level
cand['pts_intensity'] = np.clip(1 - (f2f - 0.5) / 1.5, 0, 1) * 25 + np.where(cand.max_level.fillna(0) <= 0, 5, 0)
cand['pts_use'] = cand.typ_pts
cand['pts_size'] = np.clip(np.log10(cand.footprint_m2 / 250) / np.log10(8), 0, 1) * 20      # 250 m2 -> 0, 2,000 m2+ -> 20
cand['pts_value'] = pct_rank_inv(cand.nav_per_m2.fillna(cand.nav_per_m2.median())) * 10
cand['pts_yard'] = np.clip(cand.yard_area_m2 / cand.footprint_m2, 0, 1) * 5
cand['pts_residential'] = cand.res_share_150m.fillna(0) * 5
# transport is not scored; distance to the centre stands in loosely for accessibility (15 pts at the centre, 0 at 5 km+)
cand['pts_centrality'] = np.clip(1 - cand.dist_centre_m / 5000, 0, 1) * 15
# occupied industrial estates / business parks are unlikely to be released for housing: small penalty, flagged for review
cand['in_estate'] = cand.address.str.contains(r'INDUSTRIAL ESTATE|BUSINESS PARK|ENTERPRISE CENTRE|RETAIL PARK|COMMERCIAL CAMPUS', case=False, regex=True)
cand['pts_estate'] = np.where(cand.in_estate, -5, 0)
cand['pts_tenancy'] = -np.clip(cand.n_records - 2, 0, 4) * 2.5                               # many tenants = active building
cand['score'] = cand[[c for c in cand if c.startswith('pts_')]].sum(axis=1).round(1)
cand = cand.sort_values('score', ascending=False)
cand['rank'] = range(1, len(cand) + 1)

keep = ['rank', 'score', 'address', 'names', 'uses', 'categories', 'typology', 'building', 'n_records', 'footprint_m2', 'floor_area_m2',
        'floor_to_footprint', 'max_level', 'yard_area_m2', 'total_nav', 'nav_per_m2', 'oldest_pub', 'newest_pub', 'res_share_150m',
        'n_bld_150m', 'dist_centre_m', 'pts_intensity', 'pts_use', 'pts_size', 'pts_value', 'pts_yard', 'pts_residential', 'pts_centrality', 'pts_estate', 'pts_tenancy', 'in_estate',
        'property_numbers', 'id', 'geometry']
out = cand[keep].copy()
for c in out.columns:
    if out[c].dtype.kind == 'f': out[c] = out[c].round(2)
out.head(50).to_file(out_path, layer='top50', driver='GPKG')
out.to_file(out_path, layer='all_ranked', driver='GPKG')
s[s.exclude_reason != ''][['address', 'uses', 'exclude_reason', 'footprint_m2', 'floor_area_m2', 'geometry']].to_file(out_path, layer='excluded', driver='GPKG')
print(len(j), 'valuation points snapped;', len(s), 'buildings;', len(cand), 'ranked;', (s.exclude_reason != '').sum(), 'excluded')
print(s.exclude_reason.value_counts().to_dict())
