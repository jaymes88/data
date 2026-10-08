"""Dashboard workbook: council audit land, capacity, consents on and off audit land, expected delivery year.

Reads Limerick_Housing_Supply.gpkg (sites, permissions, site_reconciliation). Scheme-level delivery years are
estimated in Python from timings observed in the delivery study; every total on the Dashboard and Breakdowns sheets
is a live SUMIFS/COUNTIFS on the Sites and Schemes sheets.
"""
import numpy as np, pandas as pd, geopandas as gpd, pyogrio
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.chart import BarChart, Reference

GPKG = 'Limerick_Housing_Supply.gpkg'
OUT = 'Limerick_Housing_Supply_Dashboard.xlsx'
T0 = pd.Timestamp('2026-10-08')
YEARS = ['Q4 2026', '2027', '2028', '2029', '2030', '2031+']
YBOUND = [(2026.0, 2027.0), (2027.0, 2028.0), (2028.0, 2029.0), (2029.0, 2030.0), (2030.0, 2031.0), (2031.0, 9999.0)]
LOC = ['Audit land – within site', 'Audit land – edge (check)', 'City – outside audit land', 'County – audit not yet supplied']
SECT = ['Private', 'Public – local authority', 'Public – AHB', 'Public – LDA']
CONSENTED = ['Complete', 'Under construction', 'Not started – permission live', 'Stalled (CIS)']
STATUS = ['Complete', 'Under construction', 'Not started – permission live', 'Stalled (CIS)', 'Not started – past expiry', 'In planning']

S = gpd.read_file(GPKG, layer='sites')
R = pyogrio.read_dataframe(GPKG, layer='site_reconciliation')
P = gpd.read_file(GPKG, layer='permissions')

yr = lambda t: t.year + (t.dayofyear - 1) / (366 if t.is_leap_year else 365)
now = yr(T0)

# ------------------------------------------------------------------ timing parameters (medians from the study data)
done = P.copy()
par = {}
for b, g in done.groupby('size_band'):
    par[b] = dict(g2s=g.grant_to_start_yrs.median(), dur=g.start_to_complete_yrs.median(), rate=g.build_rate_dpa[g.build_rate_dpa > 0].median(),
                  n_g2s=g.grant_to_start_yrs.notna().sum(), n_dur=g.start_to_complete_yrs.notna().sum())
allp = dict(g2s=P.grant_to_start_yrs.median(), dur=P.start_to_complete_yrs.median(), rate=P.build_rate_dpa[P.build_rate_dpa > 0].median())
par['Unknown'] = {**allp, 'n_g2s': P.grant_to_start_yrs.notna().sum(), 'n_dur': P.start_to_complete_yrs.notna().sum()}

LOCMAP = {'Within site': LOC[0], 'Edge (≤50 m) – check': LOC[1], 'Off register': LOC[2], 'Not assessed (county sites pending)': LOC[3]}
SECTMAP = {'Private': SECT[0], 'Local authority': SECT[1], 'Approved housing body': SECT[2], 'Land Development Agency': SECT[3]}
P['location'] = P.site_match.map(LOCMAP)
P['sector'] = P.delivery_body.map(SECTMAP).fillna('Private')
P['units'] = P.units.fillna(0)
assert P.location.notna().all()


def allocate(r):
    """Spread a scheme's units across delivery years. Returns (shares by year, est start, est finish, confidence, basis)."""
    out = dict.fromkeys(YEARS, 0.0)
    u, p = r.units, par.get(r.size_band, par['Unknown'])
    if r.status == 'Complete':
        return out, None, None, 'Delivered', 'Complete (CIS)'
    student = r.tenure == 'Student (PBSA)' and 'student' in str(r.scheme).lower()   # pure PBSA: one block, finished together
    if r.status not in ('Under construction', 'Not started – permission live') or (u <= 0 and not student):
        why = {'Stalled (CIS)': 'Stalled – not projected', 'Not started – past expiry': 'Permission expired – not projected',
               'In planning': 'Not yet decided – not projected'}.get(r.status, 'No units')
        return out, None, None, 'Not projected', why
    dur = p['dur'] if student else max(p['dur'], u / p['rate'])
    if r.status == 'Under construction':
        s = yr(pd.Timestamp(r.start)) if pd.notna(r.start) else now
        conf, basis = 'High', 'On site: started ' + (str(r.start)[:7] if pd.notna(r.start) else 'date unknown')
    else:
        g = yr(pd.Timestamp(r.final_grant)) if pd.notna(r.final_grant) else now
        s = g + p['g2s']
        conf, basis = 'Medium', f'Permitted {str(r.final_grant)[:7]}; typical start {p["g2s"]:.1f} yrs after grant'
        if r.stage in ('Contract Awarded', 'Commencement Expected'):
            s, conf, basis = max(now + 0.25, min(s, now + 0.5)), 'Medium', f'{r.stage} (CIS): start assumed within 6 months'
        elif r.stage == 'Tender':
            s, conf, basis = max(now + 0.5, s), 'Medium', 'At tender (CIS): start assumed in 6–12 months'
        elif s < now + 0.25:
            s, conf, basis = now + 0.75, 'Low', f'Permitted {str(r.final_grant)[:7]}, past typical start date with no commencement: start assumed in 9 months'
        if pd.notna(r.expiry) and yr(pd.Timestamp(r.expiry)) < s:
            conf, basis = 'Low', basis + '; expiry falls before assumed start'
    if student:
        end = max(s + dur, now + 0.5)
        for y, (lo, hi) in zip(YEARS, YBOUND):
            if lo <= end < hi:
                out[y] = u
        return out, round(s, 2), round(end, 2), conf, basis + '; student block completes in one go'
    first = s + min(1.0, dur / 2)               # first homes finish about a year after start (sooner on short builds)
    end = s + dur
    a = max(first, now)
    if end - a < 1.0:                           # overdue or nearly done: remaining units over the next 12 months
        end = a + 1.0
    for y, (lo, hi) in zip(YEARS, YBOUND):
        ov = max(0.0, min(end, hi) - max(a, lo))
        out[y] = u * ov / (end - a)
    from_y = lambda f: int(f) if f < 2031 else '2031+'
    return out, round(s, 2), round(end, 2), conf, basis


rows = []
for _, r in P.iterrows():
    sh, s, e, conf, basis = allocate(r)
    rows.append({**{y: round(v, 1) for y, v in sh.items()}, 'est_start': s, 'est_finish': e, 'confidence': conf, 'basis': basis})
A = pd.concat([P.reset_index(drop=True), pd.DataFrame(rows)], axis=1)
A['Complete units'] = np.where(A.status == 'Complete', A.units, 0)
A['Not projected'] = np.where(A.confidence == 'Not projected', A.units, 0)
# rounding residue to the last projected year so each row reconciles
proj = A[YEARS].sum(axis=1)
m = A.confidence.isin(['High', 'Medium', 'Low'])
A.loc[m, '2031+'] = (A.loc[m, '2031+'] + (A.loc[m, 'units'] - proj[m])).round(1)
dec = lambda f: None if f is None or pd.isna(f) else f'{int(f)} Q{min(4, int((f % 1) * 4) + 1)}'
A['est_start_q'] = A.est_start.map(dec)
A['est_finish_q'] = A.est_finish.map(dec)

# ------------------------------------------------------------------ workbook
F = 'Arial'
HF = PatternFill('solid', fgColor='1F3A5F')
SUB = PatternFill('solid', fgColor='DCE4EE')
KP = PatternFill('solid', fgColor='F2F5F9')
TH = Side(style='thin', color='B7C3D0')
wb = Workbook()


def hdr(ws, row, cols, c0=1):
    for i, c in enumerate(cols):
        x = ws.cell(row=row, column=c0 + i, value=c)
        x.font = Font(name=F, bold=True, color='FFFFFF', size=10)
        x.fill = HF
        x.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center' if i else 'left')


def cv(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    return v


def sheet_table(ws, df, widths):
    hdr(ws, 1, list(df.columns))
    for i, row in enumerate(df.itertuples(index=False), 2):
        for j, v in enumerate(row, 1):
            ws.cell(row=i, column=j, value=cv(v)).font = Font(name=F, size=9)
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[L(j)].width = w
    ws.freeze_panes = 'B2'
    ws.auto_filter.ref = f'A1:{L(df.shape[1])}{len(df) + 1}'
    return len(df) + 1


# Sites sheet
sites = R.merge(S[['site_id', 'rsca', 'density_band', 'reconcile_action']], on='site_id', how='left')
sites = sites[['site_id', 'rsca', 'neighbourhood', 'local_name', 'landowner', 'zoning', 'site_type', 'register_status', 'area_ha', 'capacity_units',
               'complete_units', 'under_construction_units', 'permitted_not_started_units', 'consented_units', 'residual_capacity',
               'expired_not_started_units', 'in_planning_units', 'edge_match_units', 'permissions_on_site', 'flag', 'reconcile_action']]
sites['landowner'] = sites.landowner.fillna('Unknown')
sites = sites.sort_values(['neighbourhood', 'rsca']).reset_index(drop=True)
WS_S = wb.active
WS_S.title = 'Sites'
ns = sheet_table(WS_S, sites.rename(columns=lambda c: c.replace('_', ' ').capitalize()), [11, 6, 20, 18, 22, 11, 11, 26, 9, 10, 10, 11, 11, 11, 10, 10, 10, 10, 9, 34, 50])

# Schemes sheet
sc = A[['perm_id', 'planning_ref', 'scheme', 'neighbourhood', 'settlement', 'location', 'site_id', 'sector', 'tenure', 'route', 'status', 'stage', 'units', 'student_bedspaces',
        'final_grant', 'start', 'expiry', 'est_start_q', 'est_finish_q', 'confidence', 'basis', 'Complete units'] + YEARS + ['Not projected']].copy()
sc = sc.rename(columns={'perm_id': 'Perm id', 'planning_ref': 'Planning ref', 'scheme': 'Scheme', 'neighbourhood': 'Neighbourhood', 'settlement': 'Settlement',
                        'location': 'Location', 'site_id': 'Site id', 'sector': 'Sector', 'tenure': 'Tenure', 'route': 'Route', 'status': 'Status', 'stage': 'CIS stage',
                        'units': 'Units', 'student_bedspaces': 'Student bedspaces', 'final_grant': 'Final grant', 'start': 'Start on site', 'expiry': 'Expiry', 'est_start_q': 'Est. start',
                        'est_finish_q': 'Est. last completions', 'confidence': 'Confidence', 'basis': 'Basis for estimate', 'Complete units': 'Complete'})
sc = sc.sort_values(['Location', 'Sector', 'Units'], ascending=[True, True, False]).reset_index(drop=True)
WS_P = wb.create_sheet('Schemes')
npr = sheet_table(WS_P, sc, [9, 11, 36, 18, 18, 26, 10, 20, 20, 22, 24, 20, 7, 9, 11, 11, 11, 10, 11, 12, 50, 9] + [8] * 6 + [10])
col = {c: L(i + 1) for i, c in enumerate(sc.columns)}
scol = {c: L(i + 1) for i, c in enumerate(sites.columns)}
PR = lambda c: f"Schemes!${col[c]}$2:${col[c]}${npr}"
SR = lambda c: f"Sites!${scol[c]}$2:${scol[c]}${ns}"

def put(ws, row, c, v, fmt='#,##0', bold=False, fill=None):
    x = ws.cell(row=row, column=c, value=v)
    x.font = Font(name=F, size=10, bold=bold)
    x.number_format = fmt or 'General'
    x.border = Border(bottom=TH)
    if fill:
        x.fill = fill
    return x


# ------------------------------------------------------------------ CSO reconciliation and small-scheme allowance
CR = pd.read_pickle('cso_recon.pkl')
Y = CR['years']
C = wb.create_sheet('CSO reconciliation')
C.sheet_view.showGridLines = False
C['A1'] = 'CSO planning permissions vs the planning register and the tracker'
C['A1'].font = Font(name=F, bold=True, size=14, color='1F3A5F')
C['A2'] = ('CSO: BHQ17, units for which permission granted, Limerick City & County Council (downloaded 08/10/2026). '
           f'Register: National Planning Applications dataset, Limerick, granted permissions with residential units, by decision date. '
           f'{int(Y.index.max())} covers {", ".join(CR["last_quarters"])} only.')
C['A2'].font = Font(name=F, size=9, italic=True)
ycols = ['CSO one-off houses', 'CSO scheme houses', 'CSO apartments', 'CSO total', 'Register: Single dwelling (one-off)', 'Register: Small scheme (2–9)',
         'Register: 10+: amendment to earlier permission', 'Register: 10+: not in tracker (mostly pre-2019 or completed before CIS window)',
         'Register: In tracker', 'Register total']
heads = ['Year', 'CSO one-off houses', 'CSO scheme houses', 'CSO apartments', 'CSO total', 'Register: single dwellings, not in tracker',
         'Register: 2–9 unit schemes, not in tracker', 'Register: 10+ amendments to earlier permissions', 'Register: other 10+ not in tracker',
         'Register: schemes in tracker', 'Register total', 'CSO minus register']
hdr(C, 4, heads)
C.row_dimensions[4].height = 54
C.column_dimensions['A'].width = 40
for j in range(2, 13):
    C.column_dimensions[L(j)].width = 13
YR0 = 5
for i, (yv, row) in enumerate(Y.iterrows()):
    rr = YR0 + i
    put(C, rr, 1, f'{int(yv)}' + (' (Q1–Q2)' if row.quarters < 4 else ''), None)
    for j, c_ in enumerate(ycols, 2):
        put(C, rr, j, float(row[c_]))
    put(C, rr, 12, f'=E{rr}-K{rr}', bold=True)
YR1 = YR0 + len(Y) - 1
full = [YR0 + i for i, (yv, row) in enumerate(Y.iterrows()) if row.quarters == 4]
rr = YR1 + 1
put(C, rr, 1, f'Total {int(Y.index.min())}–{int(Y[Y.quarters == 4].index.max())} (full years)', None, bold=True, fill=SUB)
for j in range(2, 13):
    put(C, rr, j, f'=SUM({L(j)}{full[0]}:{L(j)}{full[-1]})', bold=True, fill=SUB)
TOTROW = rr
rr += 1
C.cell(row=rr, column=1, value='Year-to-year differences are likely due to timing (decision date vs grant), appeals decided by An Bord Pleanála / An Coimisiún Pleanála, and amendments that re-permit units already counted. Over the full years the two sources are close.').font = Font(name=F, size=8, italic=True)

rr += 2
C.cell(row=rr, column=1, value='Small-scheme and one-off allowance (supply the tracker does not hold)').font = Font(name=F, bold=True, size=11, color='1F3A5F')
rr += 1
ys = [YR0 + i for i, (yv, row) in enumerate(Y.iterrows()) if 2023 <= yv <= 2025]
AL = {}
blue = Font(name=F, size=10, bold=True, color='0000FF')
for key, k, f, fmt in [('period', 'Averaging period', '2023–2025 (latest three full years)', None),
                  ('oneoff', 'One-off houses permitted per year (CSO average)', f'=AVERAGE(B{ys[0]}:B{ys[-1]})', '#,##0'),
                  ('small', '2–9 unit schemes not in tracker, units per year (register average)', f'=AVERAGE(G{ys[0]}:G{ys[-1]})', '#,##0'),
                  ('built', 'Share of permitted units built (input)', 0.73, '0%'),
                  ('annual', 'Annual allowance (completions per year)', None, '#,##0'),
                  ('q4', 'Share of 2026 remaining after 08/10/2026', '=(DATE(2027,1,1)-DATE(2026,10,8))/365', '0%')]:
    put(C, rr, 1, k, None, fill=KP)
    if key == 'annual':
        f = f'=(B{AL["oneoff"]}+B{AL["small"]})*B{AL["built"]}'
    x = put(C, rr, 2, f, fmt, bold=True, fill=KP)
    AL[key] = rr
    if key == 'built':
        x.font = blue
    rr += 1
C.cell(row=rr, column=1, value=('Share built: 73% of units in 1–9 unit schemes permitted two or more years before the report date had started (delivery study, implementation by size). '
                                 'It comes from CIS small schemes, not one-off houses, so treat it as an assumption; change the blue cell to test others. '
                                 'Steady state assumed: recent permissions run at the same rate as past ones, and each year’s completions come from permissions granted about three years earlier.')).font = Font(name=F, size=8, italic=True)
C.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=12)
C.cell(row=rr, column=1).alignment = Alignment(wrap_text=True, vertical='top')
C.row_dimensions[rr].height = 36
rr += 2
hdr(C, rr, ['Allowance by year'] + YEARS + ['Q4 2026–2030'])
rr += 1
ALROW = rr
put(C, rr, 1, 'Small schemes and one-off houses', None)
put(C, rr, 2, f'=B{AL["annual"]}*B{AL["q4"]}')
for j in range(3, 7):
    put(C, rr, j, f'=$B${AL["annual"]}')
put(C, rr, 7, 0)
put(C, rr, 8, f'=SUM(B{rr}:F{rr})', bold=True)
rr += 1
C.cell(row=rr, column=1, value='2031+ left at zero: the allowance is a yearly rate, and the tracker’s 2031+ column is the tail of known schemes.').font = Font(name=F, size=8, italic=True)
ALREF = lambda j: f"'CSO reconciliation'!{L(j)}${ALROW}"

rr += 2
C.cell(row=rr, column=1, value='Register grants of 10+ units since 2021 not in CIS: checked 08/10/2026').font = Font(name=F, bold=True, size=11, color='1F3A5F')
rr += 1
G = CR['grants']
CHECKED = {'22841': 'Refused on appeal, PL91.317106 (20/10/2025). Not live.',
           '2460606': 'Refused on appeal, PL91.322380 (20/08/2025). Not live.',
           '211820': 'Change of use within 19/710 (Hassett\u2019s Cross, already tracked); expired 14/03/2026. Not new supply.',
           '20525': 'Added to tracker. Granted on appeal PL91.309917 (02/12/2021); expires 01/12/2026; no commencement notice.',
           '24151': 'Added to tracker. Granted 15/01/2025; expires 14/01/2030; no commencement notice.'}
chk = G[(G.cat.str.startswith('10+: not') | G.ref.isin(CHECKED)) & (G.yr >= 2021)].drop_duplicates('ref').sort_values('n', ascending=False)
hdr(C, rr, ['Description', 'Register ref', 'Decided', 'Units (register)', 'Address', 'Finding'])
C.column_dimensions['F'].width = 13
rr += 1
for _, g_ in chk.iterrows():
    put(C, rr, 1, str(g_.DevelopmentDescription)[:160], None)
    put(C, rr, 2, g_.ref, None)
    put(C, rr, 3, g_.dd.strftime('%d/%m/%Y'), None)
    put(C, rr, 4, float(g_.n))
    put(C, rr, 5, str(g_.DevelopmentAddress).strip(), None)
    put(C, rr, 6, CHECKED.get(g_.ref, 'Not yet checked'), None)
    rr += 1
C.cell(row=rr, column=1, value='Two live schemes (Croom, 24 homes) added to the tracker as register-only records. The others are refused or not new supply.').font = Font(name=F, size=8, italic=True)

# ------------------------------------------------------------------ Dashboard
D = wb.create_sheet('Dashboard', 0)
D.sheet_view.showGridLines = False
D.column_dimensions['A'].width = 34
for c in 'BCDEFGHIJ':
    D.column_dimensions[c].width = 14
D['A1'] = 'Limerick housing supply – audit land, consents and expected delivery'
D['A1'].font = Font(name=F, bold=True, size=14, color='1F3A5F')
D['A2'] = f'Council city sites audit (133 sites; county audit not yet supplied) and counted residential permissions. Planning status at {T0:%d/%m/%Y}.'
D['A2'].font = Font(name=F, size=9, italic=True)
r = 4




# KPI block
kpis = [
    ('Audit land (ha)', f'=SUM({SR("area_ha")})', '#,##0.0'),
    ('Audit sites', f'=COUNTA({SR("site_id")})', '#,##0'),
    ('Estimated unit capacity on audit land', f'=SUM({SR("capacity_units")})', '#,##0'),
    ('Consented on audit land (within sites)', f'=SUMIFS({PR("Units")},{PR("Location")},"{LOC[0]}",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")', '#,##0'),
    ('Share of capacity consented', '=B8/B7', '0%'),
    ('Residual capacity (sum of sites)', f'=SUM({SR("residual_capacity")})', '#,##0'),
    ('Consented on edge of audit sites (check)', f'=SUMIFS({PR("Units")},{PR("Location")},"{LOC[1]}",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")', '#,##0'),
    ('Consented in city outside audit land', f'=SUMIFS({PR("Units")},{PR("Location")},"{LOC[2]}",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")', '#,##0'),
    ('Consented in county (audit pending)', f'=SUMIFS({PR("Units")},{PR("Location")},"{LOC[3]}",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")', '#,##0'),
    ('All consented units', '=B8+B11+B12+B13', '#,##0'),
    ('Student bedspaces consented (PBSA)*', f'=SUMIFS({PR("Student bedspaces")},{PR("Tenure")},"Student (PBSA)",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")', '#,##0'),
    ('Expected completions Q4 2026–2030, tracked schemes', f'=SUM({PR("Q4 2026")})+SUM({PR("2027")})+SUM({PR("2028")})+SUM({PR("2029")})+SUM({PR("2030")})', '#,##0'),
    ('+ small schemes and one-off houses (CSO-based)', f'={ALREF(8)}', '#,##0'),
]
hdr(D, r, ['Headline', 'Value'])
r += 1
for k, f, fmt in kpis:
    put(D, r, 1, k, None, fill=KP)
    put(D, r, 2, f, fmt, bold=True, fill=KP)
    r += 1
D.cell(row=r, column=1, value='* PBSA schemes are counted in the unit totals by their recorded units (cluster apartments), not bedspaces. See Breakdowns.').font = Font(name=F, size=8, italic=True)
r += 1
assert D['A7'].value.startswith('Estimated') and D['A8'].value.startswith('Consented on audit') and D['A11'].value.startswith('Consented on edge')
r += 1

# table 1: land and capacity by landowner
D.cell(row=r, column=1, value='1. Audit land and capacity by landowner (city)').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(D, r, ['Landowner', 'Sites', 'Area (ha)', 'Capacity', 'Complete', 'Under constr.', 'Permitted, not started', 'Consented', 'Residual'])
r += 1
t1 = r
for o in ['Council', 'Private', 'Unknown']:
    put(D, r, 1, o, None)
    put(D, r, 2, f'=COUNTIFS({SR("landowner")},$A{r})')
    put(D, r, 3, f'=SUMIFS({SR("area_ha")},{SR("landowner")},$A{r})', '#,##0.0')
    for j, c in enumerate(['capacity_units', 'complete_units', 'under_construction_units', 'permitted_not_started_units', 'consented_units', 'residual_capacity'], 4):
        put(D, r, j, f'=SUMIFS({SR(c)},{SR("landowner")},$A{r})')
    r += 1
put(D, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 10):
    put(D, r, j, f'=SUM({L(j)}{t1}:{L(j)}{r - 1})', '#,##0.0' if j == 3 else '#,##0', bold=True, fill=SUB)
r += 2

# table 2: consents by location and status
D.cell(row=r, column=1, value='2. Residential permissions by location and status (units)').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(D, r, ['Location'] + STATUS[:4] + ['Consented total', 'Expired, not started', 'In planning'])
r += 1
t2 = r
for loc in LOC:
    put(D, r, 1, loc, None)
    for j, st in enumerate(STATUS[:4], 2):
        put(D, r, j, f'=SUMIFS({PR("Units")},{PR("Location")},$A{r},{PR("Status")},"{st}")')
    put(D, r, 6, f'=SUM(B{r}:E{r})', bold=True)
    put(D, r, 7, f'=SUMIFS({PR("Units")},{PR("Location")},$A{r},{PR("Status")},"{STATUS[4]}")')
    put(D, r, 8, f'=SUMIFS({PR("Units")},{PR("Location")},$A{r},{PR("Status")},"{STATUS[5]}")')
    r += 1
put(D, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 9):
    put(D, r, j, f'=SUM({L(j)}{t2}:{L(j)}{r - 1})', bold=True, fill=SUB)
r += 2

# table 3: consents by sector and location
D.cell(row=r, column=1, value='3. Consented units by sector and location').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(D, r, ['Sector', 'Audit land – within site', 'Audit land – edge', 'City – outside audit land', 'County', 'Total', 'Share'])
r += 1
t3 = r
for s_ in SECT:
    put(D, r, 1, s_, None)
    for j, loc in enumerate(LOC, 2):
        put(D, r, j, f'=SUMIFS({PR("Units")},{PR("Sector")},$A{r},{PR("Location")},"{loc}",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")')
    put(D, r, 6, f'=SUM(B{r}:E{r})', bold=True)
    r += 1
put(D, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 7):
    put(D, r, j, f'=SUM({L(j)}{t3}:{L(j)}{r - 1})', bold=True, fill=SUB)
for rr in range(t3, r + 1):
    put(D, rr, 7, f'=IF($F${r}=0,0,F{rr}/$F${r})', '0%', bold=rr == r, fill=SUB if rr == r else None)
put(D, r + 1, 1, 'Public subtotal (LA + AHB + LDA)', None, bold=True)
for j in range(2, 7):
    put(D, r + 1, j, f'=SUM({L(j)}{t3 + 1}:{L(j)}{t3 + 3})', bold=True)
put(D, r + 1, 7, f'=IF($F${r}=0,0,F{r + 1}/$F${r})', '0%', bold=True)
r += 3

# table 4: expected delivery by year and sector
D.cell(row=r, column=1, value='4. Expected completions by year and sector (consented, not yet complete)').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(D, r, ['Sector'] + YEARS + ['Total projected', 'Not projected*'])
r += 1
t4 = r
for s_ in SECT:
    put(D, r, 1, s_, None)
    for j, y in enumerate(YEARS, 2):
        put(D, r, j, f'=SUMIFS({PR(y)},{PR("Sector")},$A{r})')
    put(D, r, 8, f'=SUM(B{r}:G{r})', bold=True)
    put(D, r, 9, f'=SUMIFS({PR("Not projected")},{PR("Sector")},$A{r})')
    r += 1
ALLOW = 'Small schemes and one-off houses (allowance)'
def allow_row(ws, row):
    put(ws, row, 1, ALLOW, None)
    for j in range(2, 8):
        put(ws, row, j, f'={ALREF(j)}')
    put(ws, row, 8, f'=SUM(B{row}:G{row})', bold=True)
allow_row(D, r)
r += 1
put(D, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 10):
    put(D, r, j, f'=SUM({L(j)}{t4}:{L(j)}{r - 1})', bold=True, fill=SUB)
t4end = r
r += 1
D.cell(row=r, column=1, value='* Stalled, expired or still in planning. Shown for reference, not placed in a year. Allowance = one-off houses and 2–9 unit schemes the tracker does not hold (CSO reconciliation sheet).').font = Font(name=F, size=8, italic=True)
r += 2

# table 5: expected delivery by year and location
D.cell(row=r, column=1, value='5. Expected completions by year and location').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(D, r, ['Location'] + YEARS + ['Total projected'])
r += 1
t5 = r
for loc in LOC:
    put(D, r, 1, loc, None)
    for j, y in enumerate(YEARS, 2):
        put(D, r, j, f'=SUMIFS({PR(y)},{PR("Location")},$A{r})')
    put(D, r, 8, f'=SUM(B{r}:G{r})', bold=True)
    r += 1
allow_row(D, r)
r += 1
put(D, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 9):
    put(D, r, j, f'=SUM({L(j)}{t5}:{L(j)}{r - 1})', bold=True, fill=SUB)
r += 2

# table 6: by confidence
D.cell(row=r, column=1, value='6. Expected completions by year and confidence').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(D, r, ['Confidence'] + YEARS + ['Total projected'])
r += 1
t6 = r
for c_ in ['High', 'Medium', 'Low']:
    put(D, r, 1, c_, None)
    for j, y in enumerate(YEARS, 2):
        put(D, r, j, f'=SUMIFS({PR(y)},{PR("Confidence")},$A{r})')
    put(D, r, 8, f'=SUM(B{r}:G{r})', bold=True)
    r += 1
allow_row(D, r)
r += 1
put(D, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 9):
    put(D, r, j, f'=SUM({L(j)}{t6}:{L(j)}{r - 1})', bold=True, fill=SUB)
r += 1
D.cell(row=r, column=1, value='High = on site. Medium = permitted and within the usual time to start, or at tender / contract awarded. Low = permitted but past the usual start date with no commencement, or expiry falls before the assumed start.').font = Font(name=F, size=8, italic=True)
r += 2

# chart: completions by year and sector
ch = BarChart()
ch.type, ch.grouping, ch.overlap = 'col', 'stacked', 100
ch.title = 'Expected completions by year and sector'
ch.y_axis.title = 'Units'
ch.y_axis.majorGridlines = None
data = Reference(D, min_col=1, max_col=7, min_row=t4, max_row=t4 + 4)
ch.add_data(data, from_rows=True, titles_from_data=True)
ch.set_categories(Reference(D, min_col=2, max_col=7, min_row=t4 - 1))
for s_, colr in zip(ch.series, ['1F3A5F', '4F81BD', '9BBB59', 'F2A541', 'A6A6A6']):
    s_.graphicalProperties.solidFill = colr
    s_.graphicalProperties.line.solidFill = colr
ch.height, ch.width = 6.6, 16.5
ch.y_axis.scaling.min = 0
ch.y_axis.delete = False
ch.x_axis.delete = False
D.add_chart(ch, 'D4')

# ------------------------------------------------------------------ interpretation (computed from the same data)
c = A[A.status.isin(CONSENTED)]
byloc = c.groupby('location').units.sum()
cap = sites.capacity_units.sum()
uc = A[A.status == 'Under construction'].units.sum()
live = A[A.status == 'Not started – permission live'].units.sum()
lowu = A[A.confidence == 'Low'].units.sum()
pub = c[c.sector != 'Private'].units.sum()
yrs = A[YEARS].sum()
peak = yrs[YEARS[1:5]].idxmax()
city = byloc.get(LOC[0], 0) + byloc.get(LOC[1], 0) + byloc.get(LOC[2], 0)
off_share = byloc.get(LOC[2], 0) / city if city else 0
off_bc = A[(A.location == LOC[2]) & A.status.isin(['Complete', 'Under construction'])].units.sum()
notes = [
    f'Consents within audit sites cover {byloc.get(LOC[0], 0) / cap:.0%} of the estimated capacity on audit land. Most audit land has no permission yet.',
    f'{off_share:.0%} of consented units in the city are outside the audit land. {off_bc:,.0f} of those are complete or under construction, so this is real supply that a site-based target would miss.',
    f'{uc:,.0f} units are under construction. These are the most reliable part of the next two years.',
    f'{live:,.0f} units have a live permission but no start. {lowu:,.0f} of them are past the usual time to start or close to expiry, so they are rated low confidence.',
    f'Public bodies (council, AHBs, LDA) hold {pub / c.units.sum():.0%} of consented units.',
    f'Projected completions peak in {peak}. Figures after 2028 depend mostly on permissions that have not started, so treat them as an upper figure.',
    (lambda F_, yy: f'CSO and the planning register agree closely over {int(F_.index.min())}–{int(F_.index.max())} ({F_["CSO total"].sum():,.0f} vs {F_["Register total"].sum():,.0f} units permitted). '
     f'The tracker holds the larger schemes; about {yy["CSO one-off houses"].mean():,.0f} one-off houses and {yy["Register: Small scheme (2–9)"].mean():,.0f} units in 2–9 unit schemes are permitted each year outside it (2023–2025). '
     f'At 73% built, that adds about {0.73 * (yy["CSO one-off houses"].mean() + yy["Register: Small scheme (2–9)"].mean()):,.0f} homes a year to the projection.')(Y[Y.quarters == 4], Y.loc[2023:2025]),
    'Delivery years are our estimates from timings observed in Limerick (see Assumptions). They are not developer programmes.',
]
D.cell(row=r, column=1, value='Interpretation').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
for n in notes:
    D.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    x = D.cell(row=r, column=1, value='• ' + n)
    x.font = Font(name=F, size=10)
    x.alignment = Alignment(wrap_text=True, vertical='top')
    D.row_dimensions[r].height = 27
    r += 1

# ------------------------------------------------------------------ Breakdowns: neighbourhood and tenure
B = wb.create_sheet('Breakdowns', 1)
B.sheet_view.showGridLines = False
B.column_dimensions['A'].width = 30
for c_ in 'BCDEFGHIJ':
    B.column_dimensions[c_].width = 14
B['A1'] = 'Breakdowns'
B['A1'].font = Font(name=F, bold=True, size=14, color='1F3A5F')
r = 3
B.cell(row=r, column=1, value='City neighbourhoods: audit land, capacity and consents').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(B, r, ['Neighbourhood', 'Audit sites', 'Area (ha)', 'Capacity', 'Consented within sites', 'Residual', 'Consented, edge', 'Consented outside audit land', 'All consented'])
r += 1
b1 = r
for nb in sorted(sites.neighbourhood.dropna().unique()):
    put(B, r, 1, nb, None)
    put(B, r, 2, f'=COUNTIFS({SR("neighbourhood")},$A{r})')
    put(B, r, 3, f'=SUMIFS({SR("area_ha")},{SR("neighbourhood")},$A{r})', '#,##0.0')
    put(B, r, 4, f'=SUMIFS({SR("capacity_units")},{SR("neighbourhood")},$A{r})')
    for j, loc in [(5, LOC[0]), (7, LOC[1]), (8, LOC[2])]:
        put(B, r, j, f'=SUMIFS({PR("Units")},{PR("Neighbourhood")},$A{r},{PR("Location")},"{loc}",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")')
    put(B, r, 6, f'=SUMIFS({SR("residual_capacity")},{SR("neighbourhood")},$A{r})')
    put(B, r, 9, f'=E{r}+G{r}+H{r}', bold=True)
    r += 1
put(B, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 10):
    put(B, r, j, f'=SUM({L(j)}{b1}:{L(j)}{r - 1})', '#,##0.0' if j == 3 else '#,##0', bold=True, fill=SUB)
r += 1
B.cell(row=r, column=1, value='Consents within sites are counted by the scheme’s own neighbourhood, so a few may sit in a different row from the site they fall on near a boundary.').font = Font(name=F, size=8, italic=True)
r += 2

B.cell(row=r, column=1, value='Consented units by tenure and location').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(B, r, ['Tenure', 'Audit land – within site', 'Audit land – edge', 'City – outside audit land', 'County', 'Total'])
r += 1
b2 = r
for tn in ['Market (incl. Part V)', 'Social', 'Affordable / cost rental', 'Student (PBSA)']:
    put(B, r, 1, tn, None)
    for j, loc in enumerate(LOC, 2):
        put(B, r, j, f'=SUMIFS({PR("Units")},{PR("Tenure")},$A{r},{PR("Location")},"{loc}",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")')
    put(B, r, 6, f'=SUM(B{r}:E{r})', bold=True)
    r += 1
put(B, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 7):
    put(B, r, j, f'=SUM({L(j)}{b2}:{L(j)}{r - 1})', bold=True, fill=SUB)
r += 2

B.cell(row=r, column=1, value='Consented units by sector and status').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(B, r, ['Sector'] + STATUS)
r += 1
b3 = r
for s_ in SECT:
    put(B, r, 1, s_, None)
    for j, st in enumerate(STATUS, 2):
        put(B, r, j, f'=SUMIFS({PR("Units")},{PR("Sector")},$A{r},{PR("Status")},"{st}")')
    r += 1
put(B, r, 1, 'Total', None, bold=True, fill=SUB)
for j in range(2, 8):
    put(B, r, j, f'=SUM({L(j)}{b3}:{L(j)}{r - 1})', bold=True, fill=SUB)

r += 2
B.cell(row=r, column=1, value='Purpose-built student accommodation: units and bedspaces').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
hdr(B, r, ['Scheme', 'Planning ref', 'Location', 'Status', 'Units (in totals)', 'Bedspaces', 'Est. start', 'Est. last completions', 'Confidence'])
r += 1
pb = sc[sc.Tenure == 'Student (PBSA)'].sort_values('Student bedspaces', ascending=False)
b4 = r
for _, d in pb.iterrows():
    vals = [d['Scheme'], d['Planning ref'], d['Location'], d['Status'], d['Units'], d['Student bedspaces'], d['Est. start'], d['Est. last completions'], d['Confidence']]
    for j, v in enumerate(vals, 1):
        put(B, r, j, cv(v), '#,##0' if j in (5, 6) else None)
    r += 1
put(B, r, 1, 'Total (consented, excl. expired)', None, bold=True, fill=SUB)
for j, c_ in [(5, 'Units'), (6, 'Student bedspaces')]:
    put(B, r, j, f'=SUMIFS({PR(c_)},{PR("Tenure")},"Student (PBSA)",{PR("Status")},"<>Not started – past expiry",{PR("Status")},"<>In planning")', bold=True, fill=SUB)
r += 1
B.cell(row=r, column=1, value='Units are as recorded by CIS (usually cluster apartments). Bedspaces from the PBSA schedule or the planning register. Whitebox (25/60113): 196 units, 1,400 bedspaces. Existing PBSA stock is not pipeline and is not included.').font = Font(name=F, size=8, italic=True)

# ------------------------------------------------------------------ Assumptions
N = wb.create_sheet('Assumptions')
N.column_dimensions['A'].width = 28
N.column_dimensions['B'].width = 110
N['A1'] = 'Method and assumptions'
N['A1'].font = Font(name=F, bold=True, size=14, color='1F3A5F')
text = [
    ('Audit land', 'Council city sites audit (in_sca/sca.gpkg): sites drawn twice under one reference merged; rsca 2 and 112 reinstated (removed in the council’s 04/12/25 review with no reason recorded; checked as still developable). County audit not yet supplied.'),
    ('Capacity', 'The council’s estimate per site (area × density band). Not a design-led figure. rsca 112 has a narrow, irregular shape, so its capacity is likely an upper figure.'),
    ('Permissions', 'Counted residential schemes from the pipeline tracker after primacy rules (no double counting of amendments, repeats or superseded applications), plus register-only Part 8s, KPMG additions and granted PBSA. PBSA counted in the units recorded for the scheme (cluster apartments); bedspaces are shown separately and are not added to unit totals.'),
    ('Location', 'Within site = scheme point inside an audit polygon. Edge = within 50 m of a site, not inside (point precision; check against the site boundary). City – outside audit land = more than 50 m from any audit site. County = outside the city audit area; cannot be assessed until the county audit is supplied. Scheme points come from the planning register where available.'),
    ('Consented', 'Complete + under construction + permitted not started (live) + stalled. Expired permissions and applications still in planning are shown separately and not counted as consent.'),
    ('Sector', 'Private; Public – local authority (incl. Part 8 and council own-build); Public – AHB; Public – LDA. From the tracker’s owner classification.'),
    ('Delivery year: on site', 'Build period = the larger of (a) the median start-to-completion time for the scheme’s size band and (b) units ÷ median build rate for the band. First homes complete a year after start, or halfway through the build if shorter. Units are spread evenly from then until the end of the build, counting only time after 08/10/2026. Schemes past their estimated finish, or within a year of it, have their units spread over the next 12 months.'),
    ('Delivery year: student (PBSA)', 'Purpose-built student schemes finish as one block: all units placed in the year the build ends (start + median build period for the size band). The Castletroy mixed scheme (26/60089) is phased like housing.'),
    ('Delivery year: permitted', 'Start = final grant + median grant-to-start time for the size band. Contract awarded / commencement expected (CIS): start within 6 months. At tender: start in 6–12 months. Past the usual start date with no commencement notice: start assumed in 9 months, low confidence. Then the same build profile as above.'),
    ('Not projected', 'Stalled (CIS), expired and in-planning units are not placed in a year.'),
    ('No probability weighting', 'Every permitted unit is assumed to be built. In practice some live permissions will lapse; the study found a share of permissions never start. Read Medium and Low rows as upper figures.'),
    ('Timings used', 'Medians from Limerick schemes with recorded dates (building control commencements and CIS completions):'),
]
r = 3
for k, v in text:
    N.cell(row=r, column=1, value=k).font = Font(name=F, bold=True, size=10)
    x = N.cell(row=r, column=2, value=v)
    x.font = Font(name=F, size=10)
    x.alignment = Alignment(wrap_text=True, vertical='top')
    N.cell(row=r, column=1).alignment = Alignment(vertical='top')
    r += 1
r += 1
hdr(N, r, ['Size band', 'Grant to start (yrs)', 'Schemes', 'Start to completion (yrs)', 'Schemes', 'Build rate (homes / yr)'])
for j, w in zip('CDEF', [10, 22, 10, 22]):
    N.column_dimensions[j].width = w
r += 1
for b in ['1–9', '10–24', '25–49', '50–99', '100+']:
    p = par[b]
    for j, v in enumerate([b, round(p['g2s'], 2), int(p['n_g2s']), round(p['dur'], 2), int(p['n_dur']), round(p['rate'], 1)], 1):
        N.cell(row=r, column=j, value=v).font = Font(name=F, size=10)
    r += 1
N.cell(row=r, column=1, value='Start-to-completion medians for 50–99 and 100+ rest on few schemes, so the build-rate rule usually sets the build period for large schemes.').font = Font(name=F, size=8, italic=True)

for ws in (D, B):
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
wb.save(OUT)
print('saved', OUT)
print('consented by loc', byloc.to_dict())
print('years', yrs.round(0).to_dict(), 'not projected', A['Not projected'].sum())
print(A.confidence.value_counts().to_dict())
for n in notes:
    print('-', n)
