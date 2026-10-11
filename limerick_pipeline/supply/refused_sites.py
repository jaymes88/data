"""Sites refused permission for 10+ homes (council refusal not overturned, or refused on appeal), or where the applicant withdrew, since 2017,
checked against later permissions, the council sites audit and building control. Writes refused_sites.pkl."""
import json, numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import shape
from rel import desc_units

MIN_UNITS = 10
F = gpd.read_file('in_pp_full/sites.gpkg')
F['ref'] = F.ApplicationNumber.astype(str).str.strip()
F['units'] = np.fmax(pd.to_numeric(F.NumResidentialUnits, errors='coerce').fillna(0),
                     pd.to_numeric(pd.Series([desc_units(d) for d in F.DevelopmentDescription.fillna('')]), errors='coerce').fillna(0).values)
D, AD = F.Decision.fillna('').str.upper(), F.AppealDecision.fillna('').str.upper()
F['refused'] = (D.str.contains('REFUS') & ~AD.str.contains('CONDITIONAL|GRANT')) | AD.str.contains('REFUS')
F['granted'] = (D.isin(['CONDITIONAL', 'UNCONDITIONAL']) & ~AD.str.contains('REFUS')) | AD.str.contains('CONDITIONAL|GRANT')
F['withdrawn'] = (F.WithdrawnDate.notna() | F.ApplicationStatus.fillna('').str.upper().str.contains('WITHDRAWN')) & ~D.isin(['CONDITIONAL', 'UNCONDITIONAL'])
F['outcome'] = np.where(AD.str.contains('REFUS'), 'Refused on appeal', 'Refused by council')
F.loc[AD.str.contains('REFUS') & D.isin(['CONDITIONAL', 'UNCONDITIONAL']), 'outcome'] = 'Granted by council, refused on appeal'
F.loc[AD.str.contains('REFUS') & D.str.contains('REFUS'), 'outcome'] = 'Refused by council and on appeal'
F.loc[D.str.contains('REFUS') & F.ApplicationStatus.fillna('').str.upper().eq('APPEALED') & AD.eq(''), 'outcome'] = 'Refused by council, appeal pending'
F.loc[F.withdrawn, 'outcome'] = 'Withdrawn by applicant'
F['rdate'] = pd.to_datetime(F.AppealDecisionDate).fillna(pd.to_datetime(F.DecisionDate)).fillna(pd.to_datetime(F.WithdrawnDate)).fillna(pd.to_datetime(F.ReceivedDate))
R = F[(F.refused | F.withdrawn) & (F.units >= MIN_UNITS) & F.ApplicationType.str.upper().isin(['PERMISSION', 'OUTLINE PERMISSION'])].copy()

# group repeat refusals on the same land (boundaries overlapping by half or more of the smaller)
R = R.drop_duplicates('ref').reset_index(drop=True)
grp = list(range(len(R)))
def find(i):
    while grp[i] != i:
        i = grp[i]
    return i
for i in range(len(R)):
    for j in range(i + 1, len(R)):
        a, b = R.geometry[i], R.geometry[j]
        if a.intersects(b) and a.intersection(b).area >= 0.5 * min(a.area, b.area):
            grp[find(j)] = find(i)
R['site_group'] = [find(i) for i in range(len(R))]

sites = gpd.read_file('Limerick_Housing_Supply.gpkg', layer='sites')
pb = gpd.read_file('Limerick_Housing_Supply.gpkg', layer='permission_boundaries')
nb = gpd.GeoDataFrame([f['properties'] for f in json.load(open('nbh.geojson'))['features']],
                      geometry=[shape(f['geometry']) for f in json.load(open('nbh.geojson'))['features']], crs=4326).to_crs(2157)
b = pd.read_pickle('bcms_lim.pkl').drop_duplicates('IDs').dropna(subset=['CN_LAT', 'CN_LNG'])
b = b[b.CN_Proposed_use_of_building.astype(str).str.contains('residential')]
B = gpd.GeoDataFrame(b, geometry=gpd.points_from_xy(b.CN_LNG.astype(float), b.CN_LAT.astype(float)), crs=4326).to_crs(2157)
G = F[F.granted]

rows = []
for gid, g in R.groupby('site_group'):
    g = g.sort_values('rdate')
    last = g.iloc[-1]
    geom = g.geometry.union_all()
    ha = geom.area / 1e4
    def ovl(df, min_share=0.3):
        hit = df[df.intersects(geom)]
        if not len(hit):
            return hit.iloc[0:0], []
        inter = hit.geometry.intersection(geom).area
        share = np.maximum(inter / geom.area, inter / hit.geometry.area)
        return hit[share >= min_share], share[share >= min_share]
    s_hit, s_sh = ovl(sites)
    later = G[(pd.to_datetime(G.ReceivedDate) > g.rdate.min()) & ~G.ref.isin(g.ref)]
    l_hit, _ = ovl(later)
    l_res = l_hit[l_hit.units >= 1]
    p_hit, _ = ovl(pb)
    bc = B[B.within(geom.buffer(10)) & (pd.to_datetime(B.CN_Commencement_Date) > g.rdate.min())]
    nbh = nb[nb.intersects(geom.representative_point())]
    city = len(nbh) > 0
    if len(s_hit):
        cat = 'Already in council audit'
    elif len(p_hit) or len(l_res[l_res.units >= MIN_UNITS]):
        cat = 'Since permitted for housing (in pipeline)'
    elif len(bc):
        cat = 'Since commenced (building control)'
    elif len(l_hit):
        cat = 'Since permitted for other use / small scheme – check'
    else:
        cat = 'Candidate – city' if city else 'Candidate – county (for county audit)'
    rows.append(dict(
        category=cat, refs=' / '.join(g.ref), applications=len(g), latest_ref=last.ref, address=str(last.DevelopmentAddress).strip(),
        units_sought=int(g.units.max()), outcome=last.outcome, appeal_ref=str(last.AppealRefNumber or '').strip(),
        outcomes=' / '.join(sorted(set(g.outcome))), refused_or_withdrawn=last.rdate.strftime('%d/%m/%Y') if pd.notna(last.rdate) else '', area_ha=round(ha, 2),
        units_per_ha=round(g.units.max() / ha, 1) if ha else np.nan,
        neighbourhood=nbh.nbhd.iloc[0] if city else 'County', audit_site=', '.join(s_hit.site_id) if len(s_hit) else '',
        later_permissions=', '.join(f'{r.ref} ({int(r.units)} units)' if r.units else f'{r.ref} (non-residential)' for r in l_hit.itertuples())[:200],
        in_pipeline=', '.join(p_hit.planning_ref.astype(str)) if len(p_hit) else '',
        commencements=len(bc), description=str(last.DevelopmentDescription)[:300].replace('\r', ' ').replace('\n', ' '),
        link=last.LinkAppDetails, geometry=geom))
OUT = gpd.GeoDataFrame(rows, crs=2157).sort_values(['category', 'units_sought'], ascending=[True, False])
OUT['lead_type'] = np.where(OUT.outcomes.str.contains('efused'), 'Refused', 'Withdrawn only')
OUT.to_pickle('refused_sites.pkl')
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 45)
print(OUT.groupby('category').agg(sites=('refs', 'size'), units=('units_sought', 'sum'), ha=('area_ha', 'sum')))
print(OUT[OUT.category.str.startswith(('Candidate', 'Since permitted for other'))].drop(columns=['geometry', 'description', 'link']).to_string())

# ------------------------------------------------------------------ outputs: GeoPackage layer + workbook
ORDER = ['Candidate – city', 'Candidate – county (for county audit)', 'Since permitted for other use / small scheme – check',
         'Already in council audit', 'Since permitted for housing (in pipeline)', 'Since commenced (building control)']
OUT['category'] = pd.Categorical(OUT.category, ORDER, ordered=True)
OUT = OUT.sort_values(['category', 'lead_type', 'units_sought'], ascending=[True, True, False])
cols = ['category', 'lead_type', 'refs', 'address', 'units_sought', 'outcomes', 'appeal_ref', 'refused_or_withdrawn', 'area_ha', 'units_per_ha',
        'neighbourhood', 'audit_site', 'later_permissions', 'in_pipeline', 'commencements', 'description', 'link']
L = OUT[cols + ['geometry']].copy()
L['category'] = L.category.astype(str)
L.to_file('Limerick_Housing_Supply.gpkg', layer='ref_refused_withdrawn_sites', driver='GPKG')

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
wb = Workbook()
ws = wb.active
ws.title = 'Sites'
heads = ['Category', 'Lead type', 'Planning ref(s)', 'Address', 'Homes sought', 'Outcome', 'Appeal ref', 'Refused / withdrawn', 'Site (ha)',
         'Homes per ha', 'Neighbourhood', 'Council audit site', 'Later permissions on the land', 'In our pipeline', 'Commencement notices since',
         'Description (latest application)', 'Planning file']
for j, h in enumerate(heads, 1):
    c = ws.cell(row=1, column=j, value=h)
    c.font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
    c.fill = PatternFill('solid', fgColor='1F3A5F')
    c.alignment = Alignment(wrap_text=True, vertical='top')
for i, r in enumerate(L[cols].itertuples(index=False), 2):
    for j, v in enumerate(r, 1):
        v = None if (isinstance(v, float) and np.isnan(v)) else (int(v) if isinstance(v, (np.integer,)) else v)
        c = ws.cell(row=i, column=j, value=v)
        c.font = Font(name='Arial', size=9)
for j, w in enumerate([30, 14, 20, 40, 10, 30, 14, 12, 8, 9, 18, 12, 34, 16, 10, 70, 30], 1):
    ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = w
ws.freeze_panes = 'C2'
ws.auto_filter.ref = f'A1:Q{len(L) + 1}'
n = wb.create_sheet('Method')
notes = [
    ('Source', 'National Planning Application Sites layer (application boundaries), Limerick, downloaded 11/10/2026.'),
    ('Selection', f'Applications for permission or outline permission for {MIN_UNITS} or more homes (register unit count or the number in the description), received since 2017, that were refused by the council and not granted on appeal, refused on appeal, or withdrawn by the applicant. Appeals withdrawn after a council grant are excluded: the permission stands.'),
    ('Same land', 'Applications whose boundaries overlap by at least half of the smaller one are treated as one site; all their references are listed.'),
    ('Already in council audit', 'The boundary overlaps a council audit site by at least 30% (of the boundary or the site).'),
    ('Since permitted for housing', 'A later granted application, or a scheme in our pipeline, overlaps the land by at least 30%.'),
    ('Since commenced', 'A residential commencement notice has been lodged within the boundary since the refusal or withdrawal.'),
    ('Since permitted for other use / small scheme', 'A later grant overlaps the land but is non-residential or under 10 homes. Check whether the land is still available.'),
    ('Candidate', 'None of the above. City candidates are inside the nine city neighbourhoods; county candidates are for the county audit when it arrives.'),
    ('Not checked', 'Zoning, refusal reasons and ownership are not in the register. Refusal reasons are on the planning file (link) and, for appeals, the An Coimisiún Pleanála inspector’s report. SHD applications made directly to An Bord Pleanála are covered only where the council register holds a copy.'),
]
for i, (k, v) in enumerate(notes, 1):
    n.cell(row=i, column=1, value=k).font = Font(name='Arial', bold=True, size=10)
    c = n.cell(row=i, column=2, value=v)
    c.font = Font(name='Arial', size=10)
    c.alignment = Alignment(wrap_text=True, vertical='top')
n.column_dimensions['A'].width = 34
n.column_dimensions['B'].width = 110
wb.save('Limerick_Refused_Withdrawn_Sites.xlsx')
print('saved', len(L))
