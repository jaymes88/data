"""Excel companion to the Limerick delivery study."""
import pandas as pd, numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter as L

D = pd.read_pickle('delivery.pkl')
P = pd.read_pickle('permitted.pkl')
T = pd.read_pickle('tables.pkl')
F = 'Arial'
HF = PatternFill('solid', fgColor='1F3A5F')
OUT = 'Limerick_Delivery_Study_Data.xlsx'
BANDS = ['1–9', '10–24', '25–49', '50–99', '100+']
STATUS4 = ['Complete', 'Under construction', 'Not started – permission live', 'Not started – past expiry']
LEAO = ['Limerick City East', 'Limerick City North', 'Limerick City West', 'Adare-Rathkeale', 'Cappamore-Kilmallock', 'Newcastle West']

wb = Workbook()

def hdr(ws, row, cols):
    for i, c in enumerate(cols, 1):
        x = ws.cell(row=row, column=i, value=c)
        x.font = Font(name=F, bold=True, color='FFFFFF', size=10)
        x.fill = HF
        x.alignment = Alignment(wrap_text=True, vertical='top')

def clean(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.to_pydatetime()
    if v is pd.NaT:
        return None
    return v

# ---------- README ----------
R = wb.active
R.title = 'README'
lines = [
    ('Limerick residential delivery study – data companion', None),
    ('', None),
    ('Scheme', 'A counted residential application from the Limerick pipeline workbook (after primacy rules), plus residential Part 8 schemes in the planning register that CIS does not hold (Source column).'),
    ('Owner / sector', 'Public = Limerick City and County Council (incl. Part 8), approved housing bodies, Land Development Agency. From CIS grantee and promoter, building control local-authority and AHB flags, and Part 8 file numbers (yy/8nnn). Turnkey purchases not identified in these sources are classed as private.'),
    ('City neighbourhood', 'Nine neighbourhoods defined by Limerick City and County Council from 42 Electoral Divisions (King\u2019s Island, code 1a, shown separately). Schemes outside them are labelled Outside city neighbourhoods.'),
    ('Planning dates', 'National Planning Applications dataset (Department of Housing, Local Government and Heritage), Limerick County Council records, queried 29/09/2026. An Coimisiún Pleanála case pages for SHD. CIS dates for Part 8 schemes.'),
    ('Start on site', 'Earliest commencement date on a building control commencement notice (National Building Control Office open data, 2014–present) matched by planning reference, including extensions of duration and appeal references. CIS start date used only where no notice matched and CIS records the scheme on site or complete.'),
    ('Completion', 'CIS. Date of the first dated CIS update recording the scheme as complete; CIS finish date where no such update exists. Completion certificates were tested but record 328 of the 1,226 units CIS reports complete on the same schemes, so they are not used for completions.'),
    ('Status', 'Complete (CIS); Under construction (commencement notice or CIS on site / part complete); Not started – permission live; Not started – past expiry (register expiry, including extensions of duration, before 29/09/2026). Part 8 schemes have no register expiry.'),
    ('Size bands', '1–9, 10–24, 25–49, 50–99, 100+ units (CIS units).'),
    ('LEA', 'Point-in-polygon against Local Electoral Areas 2019 (Tailte Éireann, generalised 20m).'),
    ('Durations', 'Approval = application received to final grant (appeal decision date where appealed). Grant to start = final grant to first commencement. Build period = start to completion. Negative intervals (data errors) are dropped.'),
    ('Formulas', 'Status, expiry and LEA count/sum tables are live formulas on the Schemes sheet. Medians, quartiles and cumulative start shares were calculated in Python (delivery_analysis.py) and are values.'),
    ('Contacts', 'No personal data. Scheme names are CIS project headings.'),
]
for i, (k, v) in enumerate(lines, 1):
    a = R.cell(row=i, column=1, value=k or None)
    a.font = Font(name=F, bold=True, size=14 if i == 1 else 10)
    if v:
        b = R.cell(row=i, column=2, value=v)
        b.font = Font(name=F, size=10)
        b.alignment = Alignment(wrap_text=True, vertical='top')
R.column_dimensions['A'].width = 18
R.column_dimensions['B'].width = 120

# ---------- Schemes ----------
S = wb.create_sheet('Schemes')
cols = [('ref', 'Planning ref'), ('register_ref', 'Register ref'), ('source', 'Source'), ('site', 'Site ID'), ('heading', 'Scheme'), ('settlement', 'Settlement'), ('lea', 'LEA'), ('nbhd', 'City neighbourhood'),
        ('lat', 'Latitude'), ('lon', 'Longitude'), ('units', 'Units'), ('band', 'Size band'), ('dwelling_type', 'Type'),
        ('route', 'Route'), ('owner', 'Owner'), ('sector', 'Sector'), ('stage', 'CIS stage'), ('status', 'Status'), ('received', 'Application received'),
        ('final_grant', 'Permission granted'), ('fi', 'Further information'), ('appealed', 'Appealed'), ('expiry', 'Expiry'),
        ('start', 'Start on site'), ('start_source', 'Start source'), ('bc_notices', 'Commencement notices'),
        ('bc_units_commenced', 'Units on notices'), ('completion', 'Completion (CIS)'), ('ccc_count', 'Completion certificates'),
        ('ccc_units', 'Units on certificates'), ('approval_yrs', 'Approval (yrs)'), ('grant_to_start_yrs', 'Grant to start (yrs)'),
        ('start_to_complete_yrs', 'Build period (yrs)'), ('build_rate_dpa', 'Build rate (dpa)'), ('relationship', 'Relationship'),
        ('rel_conf', 'Relationship confidence'), ('barriers_noted', 'CIS notes on barriers'),
        ('completion_source', 'Completion source'), ('sh_no', 'Social housing project no.'), ('sh_programme', 'Social housing programme'),
        ('sh_stage', 'Social housing stage'), ('sh_quarter', 'Social housing stage quarter'), ('sh_mode', 'Public delivery mode')]
Dx = D.copy()
Dx['sector'] = np.where(Dx.owner.str.startswith('Public'), 'Public', 'Private')
Dx['status'] = Dx.status.replace({'Stalled (CIS)': 'Not started – permission live'})
Dx.loc[(D.status == 'Stalled (CIS)') & D.start.notna(), 'status'] = 'Under construction'
Dx = Dx.sort_values(['lea', 'units'], ascending=[True, False])
hdr(S, 1, [c[1] for c in cols])
CS = {c[1]: L(i) for i, c in enumerate(cols, 1)}
for i, (_, r) in enumerate(Dx.iterrows(), start=2):
    for j, (k, _) in enumerate(cols, 1):
        v = r[k]
        if isinstance(v, (bool, np.bool_)):
            v = 'Yes' if v else 'No'
        c = S.cell(row=i, column=j, value=clean(v))
        if k in ('received', 'final_grant', 'expiry', 'start', 'completion'):
            c.number_format = 'dd/mm/yyyy'
        if k.endswith('_yrs') or k == 'build_rate_dpa':
            c.number_format = '0.0'
SL = len(Dx) + 1
for k, w in {'Scheme': 44, 'Settlement': 20, 'LEA': 20, 'Route': 22, 'Status': 26, 'CIS notes on barriers': 30, 'Relationship': 22}.items():
    S.column_dimensions[CS[k]].width = w
S.freeze_panes = 'D2'
S.auto_filter.ref = f'A1:{L(len(cols))}{SL}'
S.row_dimensions[1].height = 30
rng = lambda k: f"Schemes!${CS[k]}$2:${CS[k]}${SL}"

# ---------- live summary tables ----------
def live_table(ws, r0, title, rows_key, rows, colsdef):
    ws.cell(row=r0, column=1, value=title).font = Font(name=F, bold=True, size=11)
    hdr(ws, r0 + 1, [rows_key] + [c[0] for c in colsdef])
    for i, rv in enumerate(rows, start=r0 + 2):
        ws.cell(row=i, column=1, value=rv)
        for j, (_, f) in enumerate(colsdef, start=2):
            c = ws.cell(row=i, column=j, value=f(i))
            c.number_format = '#,##0;(#,##0);-'
    return r0 + 2 + len(rows)

W = wb.create_sheet('Status (live)')
st = lambda s: (lambda i, s=s: f'=SUMIFS({rng("Units")},{rng("Size band")},$A{i},{rng("Status")},"{s}")')
end = live_table(W, 1, 'Units with permission by status and size band', 'Size band', BANDS,
                 [('Schemes', lambda i: f'=COUNTIFS({rng("Size band")},$A{i},{rng("Status")},"<>In planning")')] +
                 [(s, st(s)) for s in STATUS4] + [('Total units', lambda i: f'=SUM(C{i}:F{i})')])
W.cell(row=end, column=1, value='All').font = Font(name=F, bold=True)
for j in range(2, 8):
    W.cell(row=end, column=j, value=f'=SUM({L(j)}3:{L(j)}{end - 1})').number_format = '#,##0'
stl = lambda s: (lambda i, s=s: f'=SUMIFS({rng("Units")},{rng("LEA")},$A{i},{rng("Status")},"{s}")')
end2 = live_table(W, end + 3, 'Units with permission by status and LEA', 'LEA', LEAO,
                  [('Schemes', lambda i: f'=COUNTIFS({rng("LEA")},$A{i},{rng("Status")},"<>In planning")')] +
                  [(s, stl(s)) for s in STATUS4] + [('Total units', lambda i: f'=SUM(C{i}:F{i})')])
NBO = ['City Centre', 'Kings Island', 'Corbally/Grove Island', 'Singland/Garryowen', 'Castletroy/Annacotty', 'Southhill', 'Dooradoyle', 'Ballinacurra', 'Caherdavin', 'Outside city neighbourhoods']
stn = lambda s_: (lambda i, s_=s_: f'=SUMIFS({rng("Units")},{rng("City neighbourhood")},$A{i},{rng("Status")},"{s_}")')
end3 = live_table(W, end2 + 2, 'Units with permission by status and city neighbourhood', 'Neighbourhood', NBO,
                  [('Schemes', lambda i: f'=COUNTIFS({rng("City neighbourhood")},$A{i},{rng("Status")},"<>In planning")')] +
                  [(s_, stn(s_)) for s_ in STATUS4] + [('Total units', lambda i: f'=SUM(C{i}:F{i})')])
sts = lambda s_: (lambda i, s_=s_: f'=SUMIFS({rng("Units")},{rng("Sector")},$A{i},{rng("Status")},"{s_}")')
live_table(W, end3 + 2, 'Units with permission by status and sector', 'Sector', ['Public', 'Private'],
           [('Schemes', lambda i: f'=COUNTIFS({rng("Sector")},$A{i},{rng("Status")},"<>In planning")')] +
           [(s_, sts(s_)) for s_ in STATUS4] + [('Total units', lambda i: f'=SUM(C{i}:F{i})')])
W.column_dimensions['A'].width = 28
for j in range(2, 8):
    W.column_dimensions[L(j)].width = 16

# ---------- static analysis tables ----------
for name, t in T.items():
    ws = wb.create_sheet(name[:31])
    hdr(ws, 1, list(t.columns))
    for i, row in enumerate(t.itertuples(index=False), start=2):
        for j, v in enumerate(row, 1):
            c = ws.cell(row=i, column=j, value=clean(v))
            if isinstance(v, pd.Timestamp):
                c.number_format = 'dd/mm/yyyy'
    for j, col in enumerate(t.columns, 1):
        ws.column_dimensions[L(j)].width = min(max(12, len(str(col)) * 0.9), 44 if col in ('Scheme', 'Indicator', 'Item') else 22)
    ws.row_dimensions[1].height = 42
    ws.freeze_panes = 'B2'
    note = ws.cell(row=len(t) + 3, column=1, value='Values calculated in delivery_analysis.py from the Schemes sheet.')
    note.font = Font(name=F, italic=True, size=9)

for ws in wb:
    for row in ws.iter_rows():
        for c in row:
            if c.font.name != F:
                c.font = Font(name=F, size=10, bold=c.font.b, italic=c.font.i, color=c.font.color)
wb.save(OUT)
print('saved', OUT)
