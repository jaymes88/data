"""Tables and charts for the Limerick delivery study. Reads delivery.pkl from delivery_data.py."""
import json, re
import numpy as np, pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from shapely.geometry import shape

REPORT_DATE = pd.Timestamp('2026-09-29')
D = pd.read_pickle('delivery.pkl')
BANDS = ['1–9', '10–24', '25–49', '50–99', '100+']
GROUPS = {'1–24 units': ['1–9', '10–24'], '25–99 units': ['25–49', '50–99'], '100+ units': ['100+']}
D['group'] = D.band.map({b: g for g, bs in GROUPS.items() for b in bs})
D['sector'] = np.where(D.owner.str.startswith('Public'), 'Public', 'Private')
NBO = ['City Centre', 'Kings Island', 'Corbally/Grove Island', 'Singland/Garryowen', 'Castletroy/Annacotty', 'Southhill',
       'Dooradoyle', 'Ballinacurra', 'Caherdavin']
OWNO = ['Public – local authority', 'Public – approved housing body', 'Public – LDA', 'Private']
PERMITTED = D[D.status != 'In planning'].copy()   # schemes with permission
STATUS4 = ['Complete', 'Under construction', 'Not started – permission live', 'Not started – past expiry']
PERMITTED['status4'] = PERMITTED.status.replace({'Stalled (CIS)': 'Not started – permission live'})
# stalled schemes with a commencement notice are under construction but paused; keep them with their start status
PERMITTED.loc[(PERMITTED.status == 'Stalled (CIS)') & PERMITTED.start.notna(), 'status4'] = 'Under construction'

# palette (reference palette, light mode, fixed slot order)
C = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
INK, INK2, GRID, SURF = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.edgecolor': GRID, 'axes.labelcolor': INK2,
                     'xtick.color': INK2, 'ytick.color': INK2, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6, 'figure.facecolor': 'white',
                     'axes.facecolor': 'white', 'axes.titlesize': 10, 'axes.titleweight': 'bold', 'axes.titlecolor': INK,
                     'legend.frameon': False})

def q(s, p):
    s = s.dropna()
    return round(float(s.quantile(p)), 1) if len(s) else np.nan

T = {}   # name -> DataFrame for Excel

# ---------- T1 sample overview ----------
t1 = PERMITTED.pivot_table(index='band', columns='status4', values='units', aggfunc='sum', fill_value=0).reindex(BANDS).reindex(columns=STATUS4, fill_value=0)
t1.insert(0, 'Schemes', PERMITTED.groupby('band').size().reindex(BANDS))
t1['Total units'] = t1[STATUS4].sum(axis=1)
t1.loc['All'] = t1.sum()
T['1 Status by size'] = t1.reset_index().rename(columns={'band': 'Size band (units)'})

# ---------- T2 timeline by band ----------
rows = []
for b in BANDS + ['All']:
    d = D if b == 'All' else D[D.band == b]
    rows.append({'Size band (units)': b,
                 'Approval: n': d.approval_yrs.notna().sum(), 'Approval: LQ': q(d.approval_yrs, .25), 'Approval: median': q(d.approval_yrs, .5), 'Approval: UQ': q(d.approval_yrs, .75),
                 'Grant to start: n': d.grant_to_start_yrs.notna().sum(), 'Grant to start: LQ': q(d.grant_to_start_yrs, .25), 'Grant to start: median': q(d.grant_to_start_yrs, .5), 'Grant to start: UQ': q(d.grant_to_start_yrs, .75),
                 'Start to completion: n': d.start_to_complete_yrs.notna().sum(), 'Start to completion: median': q(d.start_to_complete_yrs, .5),
                 'Build rate (dpa): median': q(d.build_rate_dpa, .5)})
T['2 Timeline by size'] = pd.DataFrame(rows)

# ---------- T3 cumulative start within t years of grant ----------
def start_curve(d, t):
    elig = d[d.final_grant.notna() & (d.final_grant <= REPORT_DATE - pd.DateOffset(months=int(12 * t)))]
    if len(elig) < 5:
        return np.nan, len(elig)
    ok = elig.start.notna() & ((elig.start - elig.final_grant).dt.days <= 365.25 * t)
    return round(100 * ok.mean(), 0), len(elig)

rows = []
for g in list(GROUPS) + ['All']:
    d = PERMITTED if g == 'All' else PERMITTED[PERMITTED.group == g]
    r = {'Scheme size': g}
    for t in [1, 2, 3, 4, 5]:
        v, n = start_curve(d, t)
        r[f'Started within {t} yr (%)'] = v
        r[f'n ({t} yr)'] = n
    rows.append(r)
T['3 Share started over time'] = pd.DataFrame(rows)

# ---------- T4 implementation by LEA / type / route (cohort granted >= 2 years before report date) ----------
COH = PERMITTED[PERMITTED.final_grant <= REPORT_DATE - pd.DateOffset(years=2)].copy()
COH['started'] = COH.status4.isin(['Complete', 'Under construction'])
def impl(by, order=None):
    g = COH.groupby(by)
    t = pd.DataFrame({'Schemes': g.size(), 'Units permitted': g.units.sum(),
                      'Units started': g.apply(lambda x: x.loc[x.started, 'units'].sum()),
                      'Schemes started': g.started.sum()})
    t['Units started (%)'] = (100 * t['Units started'] / t['Units permitted']).round(0)
    t['Schemes started (%)'] = (100 * t['Schemes started'] / t['Schemes']).round(0)
    t['Median grant to start (yrs)'] = g.grant_to_start_yrs.median().round(1)
    if order:
        t = t.reindex([o for o in order if o in t.index])
    return t.reset_index()
T['4a Implementation by LEA'] = impl('lea', ['Limerick City East', 'Limerick City North', 'Limerick City West', 'Adare-Rathkeale', 'Cappamore-Kilmallock', 'Newcastle West'])
T['4b Implementation by size'] = impl('band', BANDS)
T['4c Implementation by type'] = impl('dwelling_type', ['Houses', 'Mixed', 'Apartments', 'Student', 'Unknown'])
T['4d Implementation by route'] = impl('route', ['Standard planning application', 'LRD', 'SHD (An Bord Pleanála)', 'Part 8 / council'])
T['4e Implementation by settlement'] = impl('settlement').sort_values('Units permitted', ascending=False)

T['4f Implementation by owner'] = impl('owner', OWNO)
T['4g Implementation by sector'] = impl('sector', ['Public', 'Private'])
T['4h Implementation by nbhd'] = impl('nbhd', NBO + ['Outside city neighbourhoods'])
t12 = PERMITTED.pivot_table(index='nbhd', columns='status4', values='units', aggfunc='sum', fill_value=0).reindex(NBO + ['Outside city neighbourhoods']).reindex(columns=STATUS4, fill_value=0).fillna(0)
t12.insert(0, 'Schemes', PERMITTED.groupby('nbhd').size().reindex(t12.index).fillna(0).astype(int))
t12['Total units'] = t12[STATUS4].sum(axis=1)
t12['Public units'] = PERMITTED[PERMITTED.sector == 'Public'].groupby('nbhd').units.sum().reindex(t12.index).fillna(0)
t12['Public share (%)'] = (100 * t12['Public units'] / t12['Total units'].replace(0, np.nan)).round(0)
T['12 Status by nbhd'] = t12.reset_index().rename(columns={'nbhd': 'Neighbourhood'})
rows = []
for sec in ['Public', 'Private']:
    d = D[D.sector == sec]
    rows.append({'Sector': sec, 'Schemes': len(d), 'Units': d.units.sum(),
                 'Approval: median': q(d.approval_yrs, .5), 'Grant to start: median': q(d.grant_to_start_yrs, .5),
                 'Grant to start: n': d.grant_to_start_yrs.notna().sum(), 'Start to completion: median': q(d.start_to_complete_yrs, .5),
                 'Start to completion: n': d.start_to_complete_yrs.notna().sum(), 'Build rate (dpa): median': q(d.build_rate_dpa, .5)})
T['2b Timeline by sector'] = pd.DataFrame(rows)
rows = []
for sec in ['Public', 'Private']:
    d = PERMITTED[PERMITTED.sector == sec]
    r = {'Sector': sec}
    for t in [1, 2, 3, 4, 5]:
        v, n = start_curve(d, t)
        r[f'Started within {t} yr (%)'] = v
        r[f'n ({t} yr)'] = n
    rows.append(r)
T['3b Started over time by sector'] = pd.DataFrame(rows)

# ---------- T5 planning process effects ----------
rows = []
for lab, m in [('No further information, no appeal', ~D.fi & ~D.appealed), ('Further information requested', D.fi & ~D.appealed),
               ('Appealed', D.appealed)]:
    d = D[m & D.route.isin(['Standard planning application', 'LRD'])]
    rows.append({'Planning path': lab, 'Schemes': len(d), 'Median approval (yrs)': q(d.approval_yrs, .5),
                 'LQ': q(d.approval_yrs, .25), 'UQ': q(d.approval_yrs, .75), 'Units': d.units.sum()})
T['5 Planning path'] = pd.DataFrame(rows)

# ---------- T6 expiry profile of unstarted permissions ----------
NS = PERMITTED[PERMITTED.status4.isin(['Not started – permission live', 'Not started – past expiry'])].copy()
NS['expiry'] = pd.to_datetime(NS.expiry)
def win(e):
    if pd.isna(e):
        return 'No expiry date (mainly Part 8)'
    if e < REPORT_DATE:
        return 'Already past expiry'
    m = (e - REPORT_DATE).days / 30.44
    return 'Within 12 months' if m <= 12 else ('12–24 months' if m <= 24 else ('24–36 months' if m <= 36 else 'More than 36 months'))
NS['window'] = NS.expiry.map(win)
WIN = ['Already past expiry', 'Within 12 months', '12–24 months', '24–36 months', 'More than 36 months', 'No expiry date (mainly Part 8)']
t6 = NS.pivot_table(index='window', columns='lea', values='units', aggfunc='sum', fill_value=0).reindex(WIN).fillna(0)
t6 = t6.drop(columns=[c for c in t6.columns if c in ('Unknown', 'Outside county')])
t6['Total units'] = t6.sum(axis=1)
t6.insert(0, 'Schemes', NS.groupby('window').size().reindex(WIN).fillna(0).astype(int))
T['6 Expiry of unstarted'] = t6.reset_index().rename(columns={'window': 'Expiry window'})
watch = NS.sort_values(['expiry', 'units'], ascending=[True, False])[['ref', 'site', 'heading', 'settlement', 'lea', 'nbhd', 'owner', 'units', 'band', 'dwelling_type', 'final_grant', 'expiry', 'window', 'stage', 'last_updated', 'barriers_noted']]
T['7 Expiry watchlist'] = watch.rename(columns={'ref': 'Planning ref', 'site': 'Site ID', 'heading': 'Scheme', 'settlement': 'Settlement', 'lea': 'LEA', 'nbhd': 'Neighbourhood', 'owner': 'Owner', 'units': 'Units', 'band': 'Size band', 'dwelling_type': 'Type', 'final_grant': 'Permission granted', 'expiry': 'Expiry', 'window': 'Expiry window', 'stage': 'CIS stage', 'last_updated': 'Last CIS update', 'barriers_noted': 'CIS notes'})

# ---------- T8 annual flows ----------
yrs = list(range(2018, 2027))
t8 = pd.DataFrame({'Year': yrs,
                   'Units granted': [PERMITTED.loc[PERMITTED.grant_year == y, 'units'].sum() for y in yrs],
                   'Units started': [PERMITTED.loc[PERMITTED.start_year == y, 'units'].sum() for y in yrs],
                   'Units completed (CIS)': [PERMITTED.loc[PERMITTED.complete_year == y, 'units'].sum() for y in yrs]})
T['8 Annual flows'] = t8

# ---------- T9 build rates by type ----------
comp = D[D.build_rate_dpa.notna()]
rows = []
for lab, d in [('All completed', comp)] + [(b, comp[comp.band == b]) for b in BANDS] + [(t, comp[comp.dwelling_type == t]) for t in ['Houses', 'Apartments', 'Mixed']]:
    rows.append({'Group': lab, 'Completed schemes': len(d), 'Median build period (yrs)': q(d.start_to_complete_yrs, .5),
                 'Median build rate (dpa)': q(d.build_rate_dpa, .5), 'LQ dpa': q(d.build_rate_dpa, .25), 'UQ dpa': q(d.build_rate_dpa, .75)})
T['9 Build rates'] = pd.DataFrame(rows)

# ---------- T10 barriers evidence ----------
app = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Applications')
rel = app['Final Relationship'].value_counts()
b = [
    ('Permitted schemes not started, permission live', (PERMITTED.status4 == 'Not started – permission live').sum(), PERMITTED.loc[PERMITTED.status4 == 'Not started – permission live', 'units'].sum()),
    ('Permitted schemes not started, past expiry', (PERMITTED.status4 == 'Not started – past expiry').sum(), PERMITTED.loc[PERMITTED.status4 == 'Not started – past expiry', 'units'].sum()),
    ('Schemes recorded by CIS as stalled or suspended', (D.stage == 'Stalled or Suspended').sum(), D.loc[D.stage == 'Stalled or Suspended', 'units'].sum()),
    ('Schemes with CIS note: on hold / no movement', D.barriers_noted.str.contains('On hold').sum(), D.loc[D.barriers_noted.str.contains('On hold'), 'units'].sum()),
    ('Schemes with CIS note: legal challenge / quashed', D.barriers_noted.str.contains('Legal').sum(), D.loc[D.barriers_noted.str.contains('Legal'), 'units'].sum()),
    ('Schemes with CIS note: site for sale / sold', D.barriers_noted.str.contains('sale').sum(), D.loc[D.barriers_noted.str.contains('sale'), 'units'].sum()),
    ('Schemes where further information was requested', D.fi.sum(), D.loc[D.fi, 'units'].sum()),
    ('Schemes that went to appeal', D.appealed.sum(), D.loc[D.appealed, 'units'].sum()),
    ('Applications refused or withdrawn (not counted)', rel.get('Not live', 0), app.loc[app['Final Relationship'] == 'Not live', 'Units'].sum()),
    ('Applications superseded by a later application', rel.get('Superseded', 0), app.loc[app['Final Relationship'] == 'Superseded', 'Units'].sum()),
    ('Extensions of duration sought', rel.get('Extension of duration', 0) + rel.get('Extension of duration (parent not in CIS)', 0), np.nan),
]
T['10 Barrier indicators'] = pd.DataFrame(b, columns=['Indicator', 'Schemes / applications', 'Units'])

# ---------- T11 data coverage ----------
cc = D[D.stage == 'Complete']
T['11 Data sources'] = pd.DataFrame([
    ('Schemes in study (counted applications)', len(D)),
    ('Schemes with permission', len(PERMITTED)),
    ('Start date from building control commencement notice', (D.start_source == 'Commencement notice').sum()),
    ('Start date from CIS only', (D.start_source == 'CIS start date').sum()),
    ('Completed schemes (CIS and Department social housing report)', len(cc)),
    ('Completed schemes with a completion certificate', (cc.ccc_count > 0).sum()),
    ('Units on completed schemes', cc.units.sum()),
    ('Units on completion certificates for those schemes', cc.ccc_units.sum()),
    ('Part 8 schemes in study', (D.route == 'Part 8 / council').sum()),
    ('Part 8 schemes added from the register (not in CIS)', (D.source != 'CIS').sum()),
    ('Units on Part 8 schemes added from the register', D.loc[D.source != 'CIS', 'units'].sum()),
    ('Public schemes (local authority, AHB, LDA)', (D.sector == 'Public').sum()),
    ('Units on public schemes', D.loc[D.sector == 'Public', 'units'].sum()),
], columns=['Item', 'Value'])

# ================= CHARTS =================
def save(fig, name):
    fig.savefig(f'charts/{name}.png', dpi=220, bbox_inches='tight')
    plt.close(fig)

import os
os.makedirs('charts', exist_ok=True)

# C1 timeline medians by band
t2 = T['2 Timeline by size'].set_index('Size band (units)').loc[BANDS]
fig, ax = plt.subplots(figsize=(7.2, 3.0))
segs = [('Approval: median', 'Application to permission'), ('Grant to start: median', 'Permission to start on site'), ('Start to completion: median', 'Start to completion')]
left = np.zeros(len(BANDS))
for k, (col, lab) in enumerate(segs):
    v = t2[col].fillna(0).values
    ax.barh(BANDS, v, left=left, color=C[k], height=0.55, label=lab, edgecolor='white', linewidth=1.5)
    for i, (l, w) in enumerate(zip(left, v)):
        if w >= 0.35:
            ax.text(l + w / 2, i, f'{w:.1f}', ha='center', va='center', color='white', fontsize=8, fontweight='bold')
    left += v
for i, tot in enumerate(left):
    ax.text(tot + 0.08, i, f'{tot:.1f} yrs', va='center', color=INK, fontsize=8)
ax.invert_yaxis()
ax.set_xlabel('Median years')
ax.set_ylabel('Scheme size (units)')
ax.grid(axis='y', visible=False)
ax.legend(loc='lower center', bbox_to_anchor=(0.45, -0.42), ncol=3, fontsize=8)
ax.set_xlim(0, max(left) + 1)
save(fig, 'c1_timeline')

# C2 share started within t years
t3 = T['3 Share started over time'].set_index('Scheme size')
fig, ax = plt.subplots(figsize=(6.4, 3.2))
xs = [1, 2, 3, 4, 5]
for k, g in enumerate(GROUPS):
    ys = [t3.loc[g, f'Started within {t} yr (%)'] for t in xs]
    ax.plot(xs, ys, color=C[k], lw=2, marker='o', ms=6, markeredgecolor='white', markeredgewidth=1.5, label=g)
    last = [(x, y) for x, y in zip(xs, ys) if pd.notna(y)][-1]
    ax.text(last[0] + 0.1, last[1], g, color=INK2, fontsize=8, va='center')
ax.set_xticks(xs)
ax.set_xticklabels([f'{x} yr' for x in xs])
ax.set_ylim(0, 100)
ax.set_ylabel('% of permitted schemes started')
ax.set_xlabel('Time since permission granted')
ax.set_xlim(0.8, 5.9)
ax.legend(loc='upper left', fontsize=8)
save(fig, 'c2_started_over_time')

# C3 annual flows
fig, ax = plt.subplots(figsize=(7.2, 3.2))
w = 0.26
for k, col in enumerate(['Units granted', 'Units started', 'Units completed (CIS)']):
    ax.bar(t8.Year + (k - 1) * w, t8[col], width=w - 0.03, color=C[k], label=col.replace(' (CIS)', ''))
ax.set_xticks(t8.Year)
ax.set_xticklabels([str(y) if y < 2026 else '2026*' for y in t8.Year])
ax.set_ylabel('Units')
ax.grid(axis='x', visible=False)
ax.legend(loc='upper left', ncol=3, fontsize=8)
save(fig, 'c3_annual_flows')

# C4 status of permitted units by LEA
LEAO = ['Limerick City East', 'Limerick City North', 'Limerick City West', 'Adare-Rathkeale', 'Cappamore-Kilmallock', 'Newcastle West']
t4 = PERMITTED.pivot_table(index='lea', columns='status4', values='units', aggfunc='sum', fill_value=0).reindex(LEAO).reindex(columns=STATUS4, fill_value=0)
fig, ax = plt.subplots(figsize=(7.2, 3.0))
left = np.zeros(len(LEAO))
for k, s in enumerate(STATUS4):
    v = t4[s].values
    ax.barh(LEAO, v, left=left, color=C[k], height=0.55, label=s, edgecolor='white', linewidth=1.5)
    left += v
for i, tot in enumerate(left):
    ax.text(tot + 15, i, f'{int(tot):,}', va='center', fontsize=8, color=INK)
ax.invert_yaxis()
ax.set_xlabel('Units with permission')
ax.grid(axis='y', visible=False)
ax.legend(loc='lower center', bbox_to_anchor=(0.4, -0.45), ncol=2, fontsize=8)
save(fig, 'c4_status_by_lea')

# C5 expiry profile
t6s = T['6 Expiry of unstarted'].set_index('Expiry window')['Total units'].reindex(WIN)
fig, ax = plt.subplots(figsize=(6.6, 2.8))
cols = [C[3]] + [C[2]] * 4 + ['#b7b6b0']
ax.bar(range(len(WIN)), t6s.values, color=cols, width=0.6)
for i, v in enumerate(t6s.values):
    ax.text(i, v + 20, f'{int(v):,}', ha='center', fontsize=8, color=INK)
ax.set_xticks(range(len(WIN)))
ax.set_xticklabels(['Already past\nexpiry', 'Within\n12 months', '12–24\nmonths', '24–36\nmonths', 'More than\n36 months', 'No expiry date\n(mainly Part 8)'], fontsize=8)
ax.set_ylabel('Units not started')
ax.grid(axis='x', visible=False)
save(fig, 'c5_expiry_profile')

# C6 map
lea = json.load(open('lea.geojson'))
fig, ax = plt.subplots(figsize=(7.2, 5.2))
for f in lea['features']:
    g = shape(f['geometry'])
    polys = [g] if g.geom_type == 'Polygon' else list(g.geoms)
    for p in polys:
        x, y = p.exterior.xy
        ax.fill(x, y, color='#f3f2ef', edgecolor='#b7b6b0', linewidth=0.8)
    c = g.representative_point()
    nm = re.sub(r'\s*LEA-\d+$', '', f['properties']['ENGLISH']).title()
    if 'City' not in nm:
        ax.text(c.x, c.y - 0.03, nm, fontsize=7.5, color=INK2, ha='center', bbox=dict(facecolor='#f3f2ef', edgecolor='none', pad=1, alpha=0.8))
MAP3 = {'Complete': 'Started or complete', 'Under construction': 'Started or complete',
        'Not started – permission live': 'Not started – permission live', 'Not started – past expiry': 'Not started – past expiry'}
PERMITTED['map3'] = PERMITTED.status4.map(MAP3)
for k, s in enumerate(['Started or complete', 'Not started – permission live', 'Not started – past expiry']):
    d = PERMITTED[PERMITTED.map3 == s]
    ax.scatter(d.lon, d.lat, s=np.clip(d.units.fillna(1), 1, 400) * 0.6 + 8, color=[C[0], C[2], C[3]][k], alpha=0.85,
               edgecolor='white', linewidth=0.8, label=s, zorder=3)
ax.set_aspect(1 / np.cos(np.radians(52.5)))
ax.axis('off')
ax.legend(handles=[Line2D([0], [0], marker='o', color='w', markerfacecolor=c, markersize=8, label=l) for c, l in zip([C[0], C[2], C[3]], ['Started or complete', 'Not started – permission live', 'Not started – past expiry'])], loc='upper center', bbox_to_anchor=(0.5, -0.01), ncol=3, fontsize=8)
ax.text(0.99, 0.01, 'Circle area ∝ units. LEA boundaries: Tailte Éireann (2019).', transform=ax.transAxes, ha='right', fontsize=7, color=INK2)
save(fig, 'c6_map_county')
# city map with neighbourhood boundaries
nbh = json.load(open('nbh.geojson'))
fig, ax = plt.subplots(figsize=(7.2, 5.6))
for f in lea['features']:
    g = shape(f['geometry'])
    for p in ([g] if g.geom_type == 'Polygon' else list(g.geoms)):
        x, y = p.exterior.xy
        ax.fill(x, y, color='#fafaf8', edgecolor='#d6d5d0', linewidth=0.5)
XL, YL = (-8.72, -8.47), (52.605, 52.705)
from shapely.geometry import box
VIEW = box(XL[0], YL[0], XL[1], YL[1])
for f in nbh['features']:
    g = shape(f['geometry'])
    for p in ([g] if g.geom_type == 'Polygon' else list(g.geoms)):
        x, y = p.exterior.xy
        ax.fill(x, y, color='#eceae4', edgecolor='#5b5a56', linewidth=1.2, zorder=1)
for k, st_ in enumerate(['Started or complete', 'Not started – permission live', 'Not started – past expiry']):
    d = PERMITTED[PERMITTED.map3 == st_]
    ax.scatter(d.lon, d.lat, s=np.clip(d.units.fillna(1), 1, 400) * 0.8 + 10, color=[C[0], C[2], C[3]][k], alpha=0.85,
               edgecolor='white', linewidth=0.8, zorder=3)
for f in nbh['features']:
    g = shape(f['geometry']).intersection(VIEW)
    if g.is_empty:
        continue
    c = g.representative_point()
    nm = f['properties']['nbhd'].replace('Kings Island', "King's Island")
    ax.text(c.x, c.y, nm, fontsize=7.5, color=INK, ha='center', va='center', zorder=4,
            bbox=dict(facecolor='white', edgecolor='#b7b6b0', boxstyle='round,pad=0.25', alpha=0.9))
ax.set_xlim(*XL); ax.set_ylim(*YL)
ax.set_aspect(1 / np.cos(np.radians(52.65)))
ax.axis('off')
ax.legend(handles=[Line2D([0], [0], marker='o', color='w', markerfacecolor=c, markersize=8, label=l) for c, l in
                   zip([C[0], C[2], C[3]], ['Started or complete', 'Not started – permission live', 'Not started – past expiry'])],
          loc='upper center', bbox_to_anchor=(0.5, -0.01), ncol=3, fontsize=8)
save(fig, 'c7_map_city')

# C9 status by neighbourhood
t12c = T['12 Status by nbhd'].set_index('Neighbourhood').loc[NBO]
fig, ax = plt.subplots(figsize=(7.2, 3.6))
left = np.zeros(len(NBO))
for k, st_ in enumerate(STATUS4):
    v = t12c[st_].values
    ax.barh(NBO, v, left=left, color=C[k], height=0.6, label=st_, edgecolor='white', linewidth=1.5)
    left += v
for i, tot in enumerate(left):
    ax.text(tot + 15, i, f'{int(tot):,}', va='center', fontsize=8, color=INK)
ax.invert_yaxis()
ax.set_xlabel('Units with permission')
ax.grid(axis='y', visible=False)
ax.legend(loc='lower center', bbox_to_anchor=(0.4, -0.38), ncol=2, fontsize=8)
save(fig, 'c9_status_by_nbhd')

# C10 public vs private start curves
t3b = T['3b Started over time by sector'].set_index('Sector')
fig, ax = plt.subplots(figsize=(6.4, 3.0))
for k, sec in enumerate(['Public', 'Private']):
    ys = [t3b.loc[sec, f'Started within {t} yr (%)'] for t in xs]
    ax.plot(xs, ys, color=C[k], lw=2, marker='o', ms=6, markeredgecolor='white', markeredgewidth=1.5, label=sec)
    last = [(x_, y_) for x_, y_ in zip(xs, ys) if pd.notna(y_)][-1]
    ax.text(last[0] + 0.1, last[1], sec, color=INK2, fontsize=8, va='center')
ax.set_xticks(xs); ax.set_xticklabels([f'{x} yr' for x in xs]); ax.set_ylim(0, 100); ax.set_xlim(0.8, 5.7)
ax.set_ylabel('% of permitted schemes started'); ax.set_xlabel('Time since permission granted')
ax.legend(loc='upper left', fontsize=8)
save(fig, 'c10_started_by_sector')

# C8 build rates by band
t9 = T['9 Build rates'].set_index('Group')
fig, ax = plt.subplots(figsize=(6.4, 2.6))
bb = [b for b in BANDS if t9.loc[b, 'Completed schemes'] > 0]
ax.bar(bb, [t9.loc[b, 'Median build rate (dpa)'] for b in bb], color=C[0], width=0.55)
for i, b in enumerate(bb):
    ax.text(i, t9.loc[b, 'Median build rate (dpa)'] + 1.5, f"{t9.loc[b, 'Median build rate (dpa)']:.0f} dpa\n(n={int(t9.loc[b, 'Completed schemes'])})", ha='center', fontsize=8, color=INK)
ax.set_ylabel('Median dwellings per annum')
ax.set_xlabel('Scheme size (units)')
ax.grid(axis='x', visible=False)
ax.set_ylim(0, max(t9.loc[bb, 'Median build rate (dpa)']) * 1.35)
save(fig, 'c8_build_rates')

pd.to_pickle(T, 'tables.pkl')
PERMITTED.to_pickle('permitted.pkl')
for k, v in T.items():
    print('=====', k)
    print(v.to_string(index=False, max_colwidth=40)[:2500])
