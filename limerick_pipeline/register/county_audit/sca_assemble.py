import os
"""Assemble the county settlements capacity audit (council Excel, May 2026) into one polygon layer for the register.

Placement of each Excel site: the area match from sca_match.py, kept only where it is reliable, plus placements and
corrections confirmed by the analyst against the council's maps (OVERRIDE below). Also included:
  - every polygon the council supplied (zip outlines, Askeaton zoning file), placed or not: unplaced ones carry no site
    number and no capacity, to be filled in;
  - 2022 county audit sites in settlements or positions the 2022 file covers and the Excel does not.
Writes in_county/county_audit_2026.gpkg: layer 'sites' (polygons) and layer 'unplaced' (Excel rows still without a polygon).
"""
import re
import numpy as np, pandas as pd, geopandas as gpd
from shapely.ops import unary_union

ITM = 2157
src = open('sca_match.py').read().split('rows, maps = [], {}')[0]
exec(src)                                   # S (Excel sites), candidates(), K (2022 audit), dp_towns
M = pd.read_csv('sca_match.csv')
M['site'] = M.site.astype(str)

# ---------------------------------------------------------------- placement rules (analyst review, Oct 2026)
ACCEPT_ALL = {'Kilmallock'}                                          # every match confirmed
ACCEPT = {'Rathkeale': {'2', '3', '4', '5', '7', '8', '9', '10'},
          'Caherconlish': {'1', '5'},
          'Castleconnell': {'1', '2', '3', '4', '5', '6', '8'},
          'Croom': {'1', '2', '3', '5', '6', '7', '8'}}
# site -> candidate polygon id(s) as named by candidates(); 'new' marks sites shown on the council map but not in the Excel
OVERRIDE = {('Rathkeale', '6'): (['RAT-8'], 'placed per analyst (council map); Excel area 0.82 ha vs polygon 0.38 ha'),
            ('Rathkeale', '1'): (['RAT-3'], 'placed per analyst (council map): northwest of site 2'),
            ('Caherconlish', '2'): (['CAH-3', 'CAH-19'], 'placed per analyst (council map): west of site 3; two zoning polygons together = 0.44 ha'),
            ('Caherconlish', '3'): (['CAH-38'], 'area match; confirm (analyst marked the first placement of 3 wrong)'),
            ('Caherconlish', '7'): (['CAH-42'], 'council outline; site 7 is on the council map but not in the Excel'),
            ('Castleconnell', '9'): (['CAS-64'], 'council outline; on the council map but not in the Excel; 9/10 order to confirm'),
            ('Castleconnell', '10'): (['CAS-63'], 'council outline; on the council map but not in the Excel; 9/10 order to confirm')}

rows, used = [], {}
for town in S.settlement.unique():
    c = candidates(town).set_index('cid')
    used[town] = set()
    xs = S[S.settlement.eq(town)]
    mt = M[M.settlement.eq(town)].set_index('site')
    sites = list(xs.site) + [s for (t, s) in OVERRIDE if t == town and s not in set(xs.site)]
    for s in sites:
        x = xs[xs.site.eq(s)].iloc[0] if (xs.site == s).any() else None
        if (town, s) in OVERRIDE:
            ids, how = OVERRIDE[(town, s)]
        elif s in mt.index and pd.notna(mt.at[s, 'poly']) and (
                town in ACCEPT_ALL or s in ACCEPT.get(town, set()) or (town not in ACCEPT and mt.at[s, 'confidence'] == 'High')):
            ids, how = [mt.at[s, 'poly']], f"area match ({mt.at[s, 'confidence']}){', confirmed by analyst' if town in ACCEPT_ALL or town in ACCEPT else ''}"
        else:
            ids, how = None, None
        rows.append(dict(settlement=town, site=s, ids=ids, how=how, x=x))
        if ids:
            used[town] |= set(ids)

def num(v):
    m = re.findall(r'\d+(?:\.\d+)?', str(v)) if pd.notna(v) else []
    return float(m[0]) if m else np.nan

out, unplaced = [], []
for r in rows:
    x = r['x']
    if r['ids'] is None:
        if x is not None and x.role == 'site':
            unplaced.append(x.drop(labels=['role']).to_dict())
        continue
    c = candidates(r['settlement']).set_index('cid')
    geom = unary_union(list(c.loc[r['ids'], 'geometry']))
    if x is None:          # site from the council map, not in the Excel
        out.append(dict(settlement_name=r['settlement'], site_no=r['site'], Zone_Orig=None, Area=round(geom.area / 1e4, 3), Densities=None,
                        Capacity=np.nan, TAZ_Tier=np.nan, Taz_Type=None, wastewater=None, permission=None, site_status=None,
                        note='On the council map, not in the Excel: fill in area, density and capacity', placement=r['how'],
                        source='Council map (Oct 2026)', geometry=geom))
        continue
    dens = num(x.density)
    cap = x.capacity if pd.notna(x.capacity) else (round(x.area * dens, 1) if pd.notna(dens) and pd.notna(x.area) else np.nan)
    out.append(dict(settlement_name=r['settlement'], site_no=r['site'], Zone_Orig=x.zoning, Area=x.area, Densities=x.density,
                    Capacity=cap, TAZ_Tier=x.tier, Taz_Type=x.stype if x.stype != 'nan' else None, wastewater=x.ww,
                    permission=x.permission, site_status=x.status, note=x.note, placement=r['how'],
                    source='Council capacity audit Excel (May 2026)', geometry=geom))

# council-supplied polygons not used by a placed site: include, unnumbered
for town in S.settlement.unique():
    c = candidates(town)
    extra = c[c.src.str.startswith('Council outline') | c.src.eq('Askeaton zoning file')]
    extra = extra[~extra.cid.isin(used[town])]
    for i, p in enumerate(extra.itertuples(), 1):
        out.append(dict(settlement_name=town, site_no=f'U{i}', Zone_Orig=p.ZONE_ORIG, Area=round(p.ha, 3), Densities=None, Capacity=np.nan,
                        TAZ_Tier=np.nan, Taz_Type=None, wastewater=None, permission=None, site_status=None,
                        note='Council site with no Excel row matched yet: fill in site number, density and capacity',
                        placement='council-supplied polygon, unmatched', source=p.src, geometry=p.geometry))

A26 = gpd.GeoDataFrame(out, crs=ITM)
# 2022 audit sites the Excel does not cover: the 8 settlements missing from it, and 2022 sites left over in the 5 it shares
cov = unary_union(list(A26.geometry)).buffer(1)
for _, k in gpd.read_file('in_county/rsca_settlements.gpkg', layer='RSCA').to_crs(ITM).iterrows():
    if k.settlement_name in set(S.settlement) and k.geometry.intersection(cov).area > 0.5 * k.geometry.area:
        continue
    A26 = pd.concat([A26, gpd.GeoDataFrame([dict(
        settlement_name=k.settlement_name, site_no=str(k['Site No.']), Zone_Orig=k.Zone_Orig, Area=k.Area, Densities=k.Densities,
        Capacity=np.nan, TAZ_Tier=k.TAZ_Tier, Taz_Type=k['Taz Type'], wastewater=None, permission=None, site_status=None, note=None,
        placement='2022 polygon', source='County audit 2022 (not in the May 2026 Excel)', geometry=k.geometry)], crs=ITM)], ignore_index=True)

# sites with no council capacity: area x the town's average density for that type of site in the council Excel
# (median of the Excel densities for the town and site type; else the town's new residential figure; else the county median)
S['cls'] = S.zoning.map(cls).replace({'existing': 'resi'})
S['dn'] = S.density.map(num)
town_d = S.groupby(['settlement', 'cls']).dn.median().to_dict()
cty_d = S.groupby('cls').dn.median().to_dict()
A26['cap_basis'] = np.where(A26.Capacity.notna(), 'Council capacity (' + A26.source + ')', 'Council area x density (' + A26.source + ')')
for i, r in A26.iterrows():
    if pd.notna(r.Capacity) or (pd.notna(r.Densities) and str(r.Densities).strip() not in ('', 'None', 'nan')):
        continue
    c_ = cls(r.Zone_Orig)
    c_ = c_ if c_ in ('serviced', 'centre') else 'resi'
    d = town_d.get((r.settlement_name, c_), town_d.get((r.settlement_name, 'resi'), cty_d.get(c_)))
    basis = 'town' if (r.settlement_name, c_) in town_d or (r.settlement_name, 'resi') in town_d else 'county'
    A26.at[i, 'Densities'] = f'{d:g}'
    A26.at[i, 'Capacity'] = round(r.Area * d, 1)
    A26.at[i, 'cap_basis'] = f'Area x {basis} average density for {c_} sites in the council audit ({d:g}/ha)'
    A26.at[i, 'note'] = (str(r.note) if pd.notna(r.note) else '').replace('fill in area, density and capacity', 'site number and figures to confirm').replace(
        'fill in site number, density and capacity', 'site number to confirm')
# council settlement audit polygons (23/10/2026 file): for the towns it covers, the council's own numbered polygons replace
# everything above (our matches, outlines and the 2022 audit). Standardised and checked by rsca26_load.py.
RS = 'in_county/rsca26_sites.gpkg'
if os.path.exists(RS):
    G = gpd.read_file(RS).to_crs(ITM)
    towns26 = set(G.settlement)
    A26 = A26[~A26.settlement_name.isin(towns26)]
    pick = lambda a, b: [x if isinstance(x, str) and x not in ('nan', 'None') else (y if isinstance(y, str) else None) for x, y in zip(a, b)]
    R26 = gpd.GeoDataFrame(dict(
        settlement_name=G.settlement, site_no=G.site_no, Zone_Orig=pick(G.xl_zoning, G.zoning_file), Area=(G.area / 1e4).round(3),
        Densities=G.Densities, Capacity=G.Capacity, TAZ_Tier=pd.to_numeric(G.xl_tier.fillna(G.tier_file), errors='coerce'),
        Taz_Type=G.xl_stype, wastewater=G.xl_ww, permission=G.xl_permission, site_status=pick(G.xl_status, G.status_file),
        note=G.xl_note, placement='council polygon (settlement audit file, 23 Oct 2026)',
        source='Council settlement audit polygons (Oct 2026)', cap_basis=G.cap_basis, geometry=G.geometry), crs=ITM)
    A26 = pd.concat([R26, A26], ignore_index=True)
    U_towns = towns26
else:
    U_towns = set()
A26 = gpd.GeoDataFrame(A26, geometry='geometry', crs=ITM)
A26['geometry'] = A26.geometry.make_valid().buffer(0)
A26 = gpd.GeoDataFrame(A26, crs=ITM)
# polygons must not overlap: a later row loses the overlap to an earlier one (Excel sites come first)
taken = None
for i in A26.index:
    g = A26.at[i, 'geometry'] if taken is None else A26.at[i, 'geometry'].difference(taken)
    A26.at[i, 'geometry'] = g
    taken = g if taken is None else taken.union(g)
A26 = A26[A26.area > 100]
for c_ in ['TAZ_Tier']:
    A26[c_] = pd.to_numeric(A26[c_], errors='coerce')
for c_ in ['Densities', 'Zone_Orig', 'Taz_Type', 'wastewater', 'permission', 'site_status', 'note', 'site_no', 'cap_basis']:
    A26[c_] = A26[c_].astype('string')
A26.to_file('in_county/county_audit_2026.gpkg', layer='sites', driver='GPKG')
U = pd.DataFrame(unplaced)
U = U[~U.settlement.isin(U_towns)] if len(U) else U
U.to_csv('in_county/county_audit_2026_unplaced.csv', index=False)
gpd.GeoDataFrame(U.assign(geometry=None), geometry='geometry', crs=ITM).to_file('in_county/county_audit_2026.gpkg', layer='unplaced', driver='GPKG')
print(A26.groupby('source').size().to_string())
print('unplaced Excel sites', len(U)); print(U.groupby('settlement').site.apply(list).to_string())
