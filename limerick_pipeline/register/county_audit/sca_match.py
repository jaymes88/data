"""Match the council's settlement capacity audit (Excel, May 2026) to polygons.

Candidates per settlement: zoning polygons from the national GZT file for that town's plan, the extra polygons the council
outlined (zip: variation / non-residential zones), the Askeaton zoning file, and for Development Plan settlements the
2022 county audit polygons (which carry site numbers). Each Excel site is matched to the polygon whose area is closest,
one polygon per site, best matches first. Confidence: High = area within 5% and same zoning type; Medium = within 20%;
Low = within 50%; otherwise unmatched. Output: sca_match.csv and one review map per settlement in sca_maps/.
"""
import re, glob, os
import numpy as np, pandas as pd, geopandas as gpd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

ITM = 2157
S = pd.read_csv('in_sca2/xl_sites.csv')
S['site'] = S.site.astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
S['xid'] = S.settlement + ' ' + S.site
# a parent row split into sub-sites (Newcastle West 11 -> 11A-11D) is matched through its sub-sites
parents = [r.xid for r in S.itertuples() if (S.settlement.eq(r.settlement) & S.site.str.match(re.escape(r.site) + r'[A-Z]$')).any()]
S['role'] = np.where(S.xid.isin(parents), 'parent (split into sub-sites)', np.where(S.area.fillna(0) <= 0, 'no area (complete)', 'site'))

def cls(z):
    z = str(z).lower()
    if 'centre' in z: return 'centre'
    if 'servic' in z: return 'serviced'
    if 'existing resi' in z: return 'existing'
    if 'resi' in z or 'development area' in z: return 'resi'
    return 'other'

Z = gpd.read_file('in_zoning/gzt.gpkg').to_crs(ITM)
Z['src'] = 'GZT zoning'
ZIP = []
for f in glob.glob('in_sca2/zip/*.gpkg'):
    if 'askeaton' in f:
        continue
    g = gpd.read_file(f).to_crs(ITM); g['src'] = 'Council outline (zip): ' + os.path.basename(f); ZIP.append(g)
ZIP = pd.concat(ZIP, ignore_index=True)
AK = gpd.read_file('in_sca2/zip/askeatonresizoning.gpkg').to_crs(ITM)
AK = gpd.GeoDataFrame(dict(PLAN_NAME='Askeaton', ZONE_ORIG=AK['desc'], src='Askeaton zoning file', geometry=AK.geometry), crs=ITM)
K = gpd.read_file('in_county/rsca_settlements.gpkg', layer='RSCA').to_crs(ITM)
K = gpd.GeoDataFrame(dict(PLAN_NAME=K.settlement_name, ZONE_ORIG=K.Zone_Orig, src='County audit 2022 site ' + K['Site No.'].astype(str),
                          k_site=K['Site No.'].astype(str), geometry=K.geometry), crs=ITM)
dp_towns = set(K.PLAN_NAME)

def candidates(town):
    if town == 'Askeaton':
        c = AK.copy()
    elif town in dp_towns:
        hull = K[K.PLAN_NAME.eq(town)].union_all().buffer(800)
        c = pd.concat([K[K.PLAN_NAME.eq(town)],
                       Z[Z.PLAN_NAME.str.startswith('Limerick Development Plan') & Z.intersects(hull)]], ignore_index=True)
    else:
        c = Z[Z.PLAN_NAME.fillna('').str.lower().str.startswith(town.lower())].copy()
        z = ZIP[ZIP.PLAN_NAME.fillna('').str.lower().str.startswith(town.lower())]
        c = pd.concat([c, z], ignore_index=True)
    c = gpd.GeoDataFrame(c, crs=ITM).reset_index(drop=True)
    # the 2022 county audit polygons are copies of zoning polygons: keep one copy of each piece of land
    if town in dp_towns:
        ku = K[K.PLAN_NAME.eq(town)].union_all()
        dup = c.src.eq('GZT zoning') & (c.geometry.intersection(ku).area > 0.8 * c.area)
        c = c[~dup]
    c['cls'] = c.ZONE_ORIG.map(cls)
    c.loc[c.src.str.startswith('Council outline'), 'cls'] = 'outline'   # outlined by the council for this audit: any site type
    c = c[c.cls.ne('other')].reset_index(drop=True)
    c['ha'] = c.area / 1e4
    c['cid'] = [f'{town[:3].upper()}-{i}' for i in range(len(c))]
    return c

# permission references in the Excel (permission / note columns) anchor a site to the land of that permission
P = gpd.read_file('Limerick_Housing_Supply.gpkg', layer='permissions').to_crs(ITM)
PB = gpd.read_file('Limerick_Housing_Supply.gpkg', layer='permission_boundaries').to_crs(ITM).set_index('perm_id')
pgeom = {}
for _, r in P.iterrows():
    g = PB.loc[r.perm_id, 'geometry'] if r.perm_id in PB.index else r.geometry.buffer(25)
    for ref in {str(r.planning_ref), str(r.register_ref)} - {'None', 'nan', ''}:
        pgeom[re.sub(r'\D', '', ref)] = g
def anchors(x):
    refs = re.findall(r'\b\d{2}/?\d{3,5}\b', f'{x.permission} {x.note}')
    return [pgeom[re.sub(r'\D', '', f)] for f in refs if re.sub(r'\D', '', f) in pgeom]
PEN = {'same': 0, 'outline': 0, 'resi~serviced': 0.25, 'existing': 0.15, 'other': 0.6}
def pen(pc, xc):
    if pc == xc or pc == 'outline': return 0
    if pc == 'existing' and xc in ('resi', 'serviced'): return 0.15
    if {pc, xc} <= {'resi', 'serviced'}: return 0.25
    return 0.6

rows, maps = [], {}
for town, xs in S.groupby('settlement', sort=False):
    c = candidates(town)
    todo = xs[xs.role.eq('site')]
    pairs = []
    for i, x in todo.iterrows():
        for j, p in c.iterrows():
            if p.ha < 0.05: continue
            r = p.ha / x.area
            # a site may be the remaining part of a larger polygon ("reduced area"); a polygon much smaller than the site can't be it
            score = abs(np.log(r)) + pen(p.cls, cls(x.zoning))
            an = anchors(x)
            if an and any(p.geometry.intersection(a).area > 0.2 * min(p.geometry.area, a.area) for a in an):
                score -= 0.4                                   # the site's own permission sits on this polygon
            if town in dp_towns and str(p.get('k_site')) == x.site:
                score -= 0.15                                  # same site number in the 2022 audit
            pairs.append((score, i, j, r))
    used_x, used_p = set(), set()
    for score, i, j, r in sorted(pairs):
        if i in used_x or j in used_p or score > np.log(1.5) + 0.25:
            continue
        x, p = S.loc[i], c.loc[j]
        same = p.cls == cls(x.zoning) or p.cls == 'outline'
        an = anchors(x)
        anchored = bool(an) and any(p.geometry.intersection(a).area > 0.2 * min(p.geometry.area, a.area) for a in an)
        # another polygon of the same type within 5% of the site's area makes the pick ambiguous unless a permission anchors it
        rivals = c[(c.index != j) & (c.cls == p.cls) & ((c.ha / x.area - 1).abs() <= 0.05)]
        conf = 'High' if (abs(r - 1) <= 0.05 and same and (rivals.empty or anchored)) or (anchored and abs(r - 1) <= 0.3) else 'Medium' if abs(r - 1) <= 0.20 else 'Low'
        basis = ('permission on site; ' if anchored else '') + (f'{len(rivals)} similar-sized polygon(s) nearby; ' if len(rivals) and not anchored else '')
        used_x.add(i); used_p.add(j)
        rows.append(dict(xid=x.xid, settlement=town, site=x.site, xl_zoning=x.zoning, xl_area=x.area, poly=p.cid, poly_src=p.src,
                         poly_zoning=p.ZONE_ORIG, poly_ha=round(p.ha, 3), ratio=round(r, 2), confidence=conf, basis=basis.strip('; '), geometry=p.geometry))
    for i, x in xs.iterrows():
        if i not in used_x:
            rows.append(dict(xid=x.xid, settlement=town, site=x.site, xl_zoning=x.zoning, xl_area=x.area, poly=None, poly_src=None,
                             poly_zoning=None, poly_ha=None, ratio=None, confidence='Unmatched' if x.role == 'site' else x.role, geometry=None))
    maps[town] = (c, used_p)

M = gpd.GeoDataFrame(rows, geometry='geometry', crs=ITM)
M.drop(columns='geometry').to_csv('sca_match.csv', index=False)
M[M.geometry.notna()].to_file('sca_match.gpkg', layer='matched', driver='GPKG')

os.makedirs('sca_maps', exist_ok=True)
col = {'High': '#2e7d32', 'Medium': '#f9a825', 'Low': '#e65100'}
for town, (c, used_p) in maps.items():
    m = M[M.settlement.eq(town)]
    mm = m[m.geometry.notna()]
    fig, ax = plt.subplots(figsize=(12, 10))
    c[c.cls.isin(['resi', 'serviced', 'centre'])].plot(ax=ax, facecolor='#f2f2f2', edgecolor='#bbbbbb', linewidth=0.4)
    c[c.cls.eq('existing')].plot(ax=ax, facecolor='none', edgecolor='#dddddd', linewidth=0.3)
    o = c[c.cls.eq('outline')]
    if len(o):
        o.plot(ax=ax, facecolor='none', edgecolor='#1565c0', linewidth=1.6, linestyle='--')
    for _, r in mm.iterrows():
        gpd.GeoSeries([r.geometry], crs=ITM).plot(ax=ax, facecolor=col[r.confidence], alpha=0.6, edgecolor='black', linewidth=0.8)
        q = r.geometry.representative_point()
        ax.annotate(f'{r.site}', (q.x, q.y), fontsize=11, weight='bold', ha='center', va='center',
                    bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.8))
    if len(mm):
        x0, y0, x1, y1 = mm.total_bounds
        pad = max(x1 - x0, y1 - y0) * 0.15 + 100
        ax.set_xlim(x0 - pad, x1 + pad); ax.set_ylim(y0 - pad, y1 + pad)
    lines = [f'{r.site}: {r.xl_zoning}, {r.xl_area:g} ha in Excel; polygon {r.poly_ha:.2f} ha ({r.poly_zoning}) - {r.confidence}' for r in mm.itertuples()]
    un = m[m.geometry.isna()]
    lines += [f'{r.site}: {r.xl_zoning}, {r.xl_area:g} ha - not placed ({r.confidence})' for r in un.itertuples()]
    ax.set_title(f'{town}: council capacity audit sites as matched (green high / amber medium / orange low; blue dashed = council outline in zip)',
                 fontsize=10, loc='left')
    ax.text(1.01, 1.0, '\n'.join(lines), transform=ax.transAxes, fontsize=7.5, va='top', family='monospace')
    ax.set_axis_off()
    fig.tight_layout(); fig.savefig(f'sca_maps/{town.replace(" ", "_")}.png', dpi=120, bbox_inches='tight'); plt.close(fig)

print(M.groupby(['settlement', 'confidence']).size().unstack(fill_value=0))
