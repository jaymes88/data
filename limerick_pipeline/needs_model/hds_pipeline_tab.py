"""Add a 'Pipeline & permissions needed' tab (and its 'Pipeline calc' working sheet) to the HDS needs model.

The same method as the tracker's "permissions needed" tool (renderWhatIf in tracker/tracker.js): work back month by month
from the target, from the planning status date to December of the end year. Completions needed -> starts (less build
time) -> permissions (less time to start, grossed up for permitted homes never started) -> applications (less decision
time, grossed up for refusals and withdrawals). Anything that falls before the status date is "needed before now".
Optionally the register's expected completions are taken off first; its 2031+ tail is counted in 2031, and a running
maximum carries any surplus forward.

Targets are live from the catchment tabs (via Land and Total). Pipeline status and expected completions are values from
the land register (Limerick_Developable_Land.gpkg). Defaults for the lags come from the tracker's meta.whatif.
Run last: python hds_pipeline_tab.py <in.xlsx> <out.xlsx>
"""
import re, sys
import geopandas as gpd, openpyxl
from datetime import date
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.chart import BarChart, Reference

SRC, OUT = sys.argv[1], sys.argv[2]
STATUS_AT = date(2026, 10, 8)                       # tracker meta.planningStatusAt
WHATIF = dict(ls=16.0, lsN=136, lsIQR=(8.1, 24.8), noStart=0.176, noStartPrimary=0.311, expiredUnits=1582, noStartUnits=278,
              granted={2018: 655, 2019: 460, 2020: 622, 2021: 1132, 2022: 1616, 2023: 880, 2024: 1402, 2025: 1113})

reg = gpd.read_file('Limerick_Developable_Land.gpkg', layer='developable_land')
ST = ['complete_units', 'under_construction_units', 'permitted_not_started_units', 'stalled_units', 'expired_units', 'in_planning_units']
EST = ['est_q4_2026', 'est_2027', 'est_2028', 'est_2029', 'est_2030', 'est_2031_plus']
pipe = reg.groupby('catchment')[ST + EST].sum()

wb = openpyxl.load_workbook(SRC)
for nm in ['Pipeline & permissions needed', 'Pipeline calc']:
    if nm in wb.sheetnames:
        del wb[nm]
NAME = 'Pipeline & permissions needed'
ws = wb.create_sheet(NAME, index=wb.sheetnames.index('Opportunity sites & options') + 1)
C = wb.create_sheet('Pipeline calc', index=wb.sheetnames.index('Data') + 1)

F = 'Arial'
DARK, MUTED, BAND = 'FF0E2925', 'FF3E5853', 'FFF4EFE8'
hdr_font, hdr_fill = Font(name=F, size=10, bold=True, color='FFFFFFFF'), PatternFill('solid', fgColor=DARK)
body, bold, note = Font(name=F, size=10), Font(name=F, size=10, bold=True), Font(name=F, size=10, color=MUTED)
lever_font, lever_fill = Font(name=F, size=10, bold=True, color='FF0000FF'), PatternFill('solid', fgColor='FFE4E66A')
band = PatternFill('solid', fgColor=BAND)
INT, DEC, PCT = '#,##0;\\(#,##0\\);\\-', '#,##0.0', '0%'
h2 = Font(name=F, size=12, bold=True, color=DARK)

# ---------------- places: Limerick + the 25 catchments, in Land tab order
LAND = wb['Land']
places = [('Limerick', 'Total', None)]
for r in range(7, 32):
    nm = LAND.cell(r, 1).value
    sheet = re.match(r"='?([^'!]+)'?!", LAND.cell(r, 5).value).group(1)
    places.append((nm, sheet, r))
NP = len(places)
YEARS = list(range(2026, 2041))

# ---------------- Pipeline calc: inputs per place (rows 3..), monthly engine (rows 40..), summaries
C['A1'] = 'Working sheet for the Pipeline & permissions needed tab. Do not edit; change the yellow cells on that tab.'
C['A1'].font = note
lv = lambda c: f"'{NAME}'!${c[0]}${c[1:]}"   # reference to a lever on the main tab
P_ROW0 = 3
heads = ['Place', 'Tab'] + [str(y) for y in YEARS] + ['Complete', 'Under construction', 'Not started', 'Stalled', 'Expired', 'In planning'] \
        + ['Exp Q4 2026', 'Exp 2027', 'Exp 2028', 'Exp 2029', 'Exp 2030', 'Exp 2031+'] + ['1-bed', '2-bed', '3-bed', '4+ bed', 'Private', 'Affordable', 'Social']
for j, h in enumerate(heads, 1):
    C.cell(P_ROW0 - 1, j, h).font = bold
cT0, cS0, cE0, cM0 = 3, 3 + 15, 3 + 21, 3 + 27            # first column of targets, status, expected, mix
for i, (nm, sheet, lr) in enumerate(places):
    r = P_ROW0 + i
    C.cell(r, 1, nm); C.cell(r, 2, sheet)
    q = f"'{sheet}'" if re.search(r'\W', sheet) else sheet
    for k in range(15):
        C.cell(r, cT0 + k, f'={q}!B{13 + k}')
    key = None if nm == 'Limerick' else nm
    vals = pipe.sum() if key is None else (pipe.loc[key] if key in pipe.index else None)
    for k, f in enumerate(ST + EST):
        C.cell(r, cS0 + k, round(float(vals[f]), 1) if vals is not None else 0)
    mix = [f'={q}!C29', f'={q}!D29', f'={q}!E29', f'={q}!F29', f'={q}!G29+{q}!H29', f'={q}!I29+{q}!J29', f'=SUM({q}!K29:O29)']
    for k, f in enumerate(mix):
        C.cell(r, cM0 + k, f)
PEND = P_ROW0 + NP - 1
prng = f"'Pipeline calc'!$A${P_ROW0}:$A${PEND}"

# scalars (column AL..) used by the engine
SC = 40   # column for scalar block
scal = {
    'NOWM': f"=(YEAR({lv('C5')})-2026)*12+MONTH({lv('C5')})-1+(DAY({lv('C5')})-1)/30.44",
    'REM': f"=(DATE(YEAR({lv('C5')})+1,1,1)-{lv('C5')})/365",
    'WMON': '=12*(Model!$B$3-2025)',
    'PIPE': f'=IF({lv("C6")}="Yes",1,0)',
    'LD': f"={lv('C7')}", 'LS': f"={lv('C8')}", 'LB': f"={lv('C9')}",
    'KQ': f"=1/MAX(0.01,1-{lv('C10')})", 'KR': f"=1/MAX(0.01,1-{lv('C11')})",
    'LASTGRANT': None, 'LASTAPP': None, 'SPAN': None,
}
SR = {}
for i, k in enumerate(scal):
    SR[k] = f"'Pipeline calc'!${L(SC + 1)}${P_ROW0 + i}"
    C.cell(P_ROW0 + i, SC, k).font = bold
loc = lambda k: f'${L(SC + 1)}${P_ROW0 + list(scal).index(k)}'
scal['LASTGRANT'] = f"=2026+({loc('WMON')}-0.5-{loc('LB')}-{loc('LS')})/12"
scal['LASTAPP'] = f"={loc('LASTGRANT')}-{loc('LD')}/12"
scal['SPAN'] = f"=MAX(0.25,{loc('LASTGRANT')}-(2026+{loc('NOWM')}/12))"
for i, (k, f) in enumerate(scal.items()):
    C.cell(P_ROW0 + i, SC + 1, f)

# monthly engine: one row per month from January 2026; shared columns, then 6 columns per place
M0, NM = 40, 180
shared = ['Month', 'Year', 'Share after status date', 'Bucket: completion', 'Bucket: start', 'Bucket: permission', 'Bucket: application']
for j, h in enumerate(shared, 1):
    C.cell(M0 - 1, j, h).font = bold
PER = ['target', 'register expected', 'cum target', 'cum expected', 'still to deliver', 'new completions']
pc = lambda p, k: 8 + p * 6 + k                            # column of measure k for place p
for p, (nm, _, _) in enumerate(places):
    for k, h in enumerate(PER):
        C.cell(M0 - 1, pc(p, k), f'{nm}: {h}').font = bold
NOWM, REM, PIPE, LDc, LSc, LBc = loc('NOWM'), loc('REM'), loc('PIPE'), loc('LD'), loc('LS'), loc('LB')
for m in range(NM):
    r = M0 + m
    C.cell(r, 1, m)
    C.cell(r, 2, f'=2026+INT(A{r}/12)')
    C.cell(r, 3, f'=MAX(0,MIN(1,A{r}+1-{NOWM}))')
    for j, lag in enumerate(['0', LBc, f'{LBc}+{LSc}', f'{LBc}+{LSc}+{LDc}']):
        tau = f'(A{r}+0.5-({lag}))'
        C.cell(r, 4 + j, f'=IF({tau}<{NOWM},0,2026+INT({tau}/12))')
    for p in range(NP):
        pr = P_ROW0 + p
        t, pp, ct, cp, n, nc = (L(pc(p, k)) for k in range(6))
        tyr = f"INDEX($C${pr}:$Q${pr},1,B{r}-2025)"
        C[f'{t}{r}'] = f'=IF(B{r}=2026,{tyr}*{REM}*C{r}/MAX(0.0001,12-{NOWM}),{tyr}/12)'
        if m < 12:
            ex = f'$X${pr}*C{r}/MAX(0.0001,12-{NOWM})'
        elif m < 60:
            ex = f'INDEX($Y${pr}:$AB${pr},1,B{r}-2026)/12'
        elif m < 72:
            ex = f'$AC${pr}/12'
        else:
            ex = '0'
        C[f'{pp}{r}'] = f'={PIPE}*{ex}'
        C[f'{ct}{r}'] = f'={t}{r}' + (f'+{ct}{r - 1}' if m else '')
        C[f'{cp}{r}'] = f'={pp}{r}' + (f'+{cp}{r - 1}' if m else '')
        C[f'{n}{r}'] = f'=MAX({n}{r - 1},{ct}{r}-{cp}{r})' if m else f'=MAX(0,{ct}{r}-{cp}{r})'
        C[f'{nc}{r}'] = f'={n}{r}-{n}{r - 1}' if m else f'={n}{r}'
MEND = M0 + NM - 1

# year summaries per place: 6 measures x NP rows x 16 buckets (0 = before now, then 2026..2040)
BUCKETS = [0] + YEARS
S0 = MEND + 4
MEAS = [('Target completions', 'D', 0, ''), ('Register expected', 'D', 1, ''), ('New completions needed', 'D', 5, ''),
        ('Starts needed', 'E', 5, ''), ('Permissions needed', 'F', 5, f"*{loc('KQ')}"), ('Applications needed', 'G', 5, f"*{loc('KQ')}*{loc('KR')}")]
blk = {}
for b, (title, bcol, k, mult) in enumerate(MEAS):
    top = S0 + b * (NP + 3)
    C.cell(top, 1, title).font = bold
    for j, y in enumerate(BUCKETS):
        C.cell(top, 3 + j, 'Before' if y == 0 else y).font = bold
    for p, (nm, _, _) in enumerate(places):
        r = top + 1 + p
        C.cell(r, 1, nm)
        col = L(pc(p, k))
        for j, y in enumerate(BUCKETS):
            C.cell(r, 3 + j, f'=SUMIF(${bcol}${M0}:${bcol}${MEND},{y},{col}${M0}:{col}${MEND}){mult}')
    blk[title] = (top + 1, top + NP)
# per-place headline figures
H0 = S0 + len(MEAS) * (NP + 3) + 1
hh = ['Place', 'Still to deliver', 'Permissions before now', 'Permissions from now', 'Per year', 'Applications from now']
for j, h in enumerate(hh, 1):
    C.cell(H0, j, h).font = bold
g0, a0 = blk['Permissions needed'][0], blk['Applications needed'][0]
for p, (nm, _, _) in enumerate(places):
    r = H0 + 1 + p
    C.cell(r, 1, nm)
    C.cell(r, 2, f'={L(pc(p, 4))}{MEND}')
    C.cell(r, 3, f'=C{g0 + p}')
    C.cell(r, 4, f'=SUM(D{g0 + p}:R{g0 + p})')
    C.cell(r, 5, f"=D{r}/{loc('SPAN')}")
    C.cell(r, 6, f'=SUM(D{a0 + p}:R{a0 + p})')
HEND = H0 + NP

# ---------------- main tab
ws['A1'] = 'Planning pipeline and permissions needed'; ws['A1'].font = Font(name=F, size=16, bold=True, color=DARK)
ws['A2'] = ('What is in the planning pipeline, what it is expected to complete, and how many homes need planning permission each year to meet '
            'the target. Works back from the target: each home completed needs a start, a permission and an application earlier. '
            'The same method as the tracker\'s forecasting tool.')
ws['A2'].font = note; ws['A2'].alignment = Alignment(wrap_text=True, vertical='top'); ws.merge_cells('A2:H2'); ws.row_dimensions[2].height = 40

levers = [
    (4, 'Place', 'Limerick', 'Limerick or any catchment.'),
    (5, 'Planning status at', STATUS_AT, 'Date the register\'s permission statuses refer to. Targets before this date are treated as past.'),
    (6, 'Take off the register\'s expected completions', 'Yes', 'Yes: only homes the register does not already expect need new permissions. No: the whole target from the status date.'),
    (7, 'Application to decision (months)', 4.5, 'Default 4.5: the Central Bank\'s median council decision time for schemes not appealed (Quarterly Bulletin, September 2026, as reported by the Irish Times). No Limerick figure in the register.'),
    (8, 'Permission to start on site (months)', WHATIF['ls'], f'Default {WHATIF["ls"]:g}: median for Limerick permissions with a start date in the register ({WHATIF["lsN"]}; middle half {WHATIF["lsIQR"][0]} to {WHATIF["lsIQR"][1]} months). National average 14, apartments 18 (Central Bank, 2024).'),
    (9, 'Start to completion (months)', 15, 'Default 15: midpoint of the 12 to 18 months the Central Bank assumes (Quarterly Bulletin 2, 2024). No Limerick figure in the register.'),
    (10, 'Permitted homes never started', round(WHATIF['noStart'], 2), f'Default {round(WHATIF["noStart"] * 100):g}%: of {WHATIF["expiredUnits"]:,} homes in Limerick permissions past their expiry date, {WHATIF["noStartUnits"]} never started. Counting primary permissions only, {round(WHATIF["noStartPrimary"] * 100):g}%. Small sample.'),
    (11, 'Applications refused or withdrawn', 0, 'Default 0%: no Limerick refusal or withdrawal rate in hand. Set it if known.'),
]
for r, k, v, d in levers:
    ws.cell(r, 1, k).font = bold
    c = ws.cell(r, 3, v); c.font, c.fill = lever_font, lever_fill
    c.number_format = {5: 'dd/mm/yyyy', 10: PCT, 11: PCT}.get(r, '0.0' if r in (7, 8, 9) else 'General')
    ws.cell(r, 4, d).font = note
dv = DataValidation(type='list', formula1=f"'Pipeline calc'!$A${P_ROW0}:$A${PEND}", allow_blank=False); ws.add_data_validation(dv); dv.add('C4')
dv2 = DataValidation(type='list', formula1='"Yes,No"', allow_blank=False); ws.add_data_validation(dv2); dv2.add('C6')
for cell, lo, hi in [('C7', 0, 36), ('C8', 0, 60), ('C9', 0, 60)]:
    d = DataValidation(type='decimal', operator='between', formula1=str(lo), formula2=str(hi)); ws.add_data_validation(d); d.add(cell)
for cell in ['C10', 'C11']:
    d = DataValidation(type='decimal', operator='between', formula1='0', formula2='0.95'); ws.add_data_validation(d); d.add(cell)
PI = f"MATCH($C$4,{prng},0)"
pick = lambda col: f"INDEX('Pipeline calc'!${col}${P_ROW0}:${col}${PEND},{PI})"

# pipeline now
r = 13
ws.cell(r, 1, 'Pipeline now (land register)').font = h2
ws.cell(r + 1, 1, '="Homes in permissions in "&$C$4&", by status at "&TEXT($C$5,"d mmmm yyyy")').font = note
labels = ['Complete', 'Under construction', 'Permitted, not started', 'Stalled', 'Expired, not started', 'In planning']
for j, h in enumerate(labels + ['Consented (first four)'], 2):
    c = ws.cell(r + 2, j, h); c.font, c.fill = hdr_font, hdr_fill; c.alignment = Alignment(wrap_text=True, vertical='top')
ws.cell(r + 3, 1, 'Homes').font = bold
for j in range(6):
    ws.cell(r + 3, 2 + j, '=' + pick(L(cS0 + j))).number_format = INT
ws.cell(r + 3, 8, f'=SUM(B{r + 3}:E{r + 3})').number_format = INT; ws.cell(r + 3, 8).font = bold
for j, h in enumerate(['Q4 2026', '2027', '2028', '2029', '2030', '2031+', 'Total'], 2):
    c = ws.cell(r + 5, j, h); c.font, c.fill = hdr_font, hdr_fill
ws.cell(r + 6, 1, 'Expected completions').font = bold
for j in range(6):
    ws.cell(r + 6, 2 + j, '=' + pick(L(cE0 + j))).number_format = INT
ws.cell(r + 6, 8, f'=SUM(B{r + 6}:G{r + 6})').number_format = INT; ws.cell(r + 6, 8).font = bold
ws.cell(r + 7, 1, 'The register\'s own delivery estimates for its permissions. Expired and in-planning homes are not expected.').font = note

# headline results
GR = 31 + len(BUCKETS) + 2       # register grants row, below the year table
r = 22
ws.cell(r, 1, 'Results').font = h2
hi = f"MATCH($C$4,'Pipeline calc'!$A${H0 + 1}:$A${HEND},0)"
hp = lambda col: f"INDEX('Pipeline calc'!${col}${H0 + 1}:${col}${HEND},{hi})"
res = [
    ('Homes still to deliver', '=' + hp('B'), f'=IF($C$6="Yes","Target from the status date, less the register\'s expected completions","The whole target from the status date")'),
    ('Permissions needed from now', '=' + hp('D'), f'="About "&TEXT({hp("E")},"#,##0")&" homes a year, to "&TEXT(DATE(INT({SR["LASTGRANT"]}),1+INT(MOD({SR["LASTGRANT"]},1)*12),1),"mmmm yyyy")'),
    ('Permissions a year', '=' + hp('E'), f'=IF($C$4="Limerick","The register shows "&TEXT(AVERAGE($C${GR}:$J${GR}),"#,##0")&" homes a year granted in 2018–2025 (row {GR})","Spread evenly from the status date to the last useful permission date")'),
    ('Applications needed from now', '=' + hp('F'), f'="Lodged by "&TEXT(DATE(INT({SR["LASTAPP"]}),1+INT(MOD({SR["LASTAPP"]},1)*12),1),"mmmm yyyy")'),
    ('Needed before now', '=' + hp('C'), f'=IF(C{r + 5}>0.5,"Homes that would already need permission to complete in time: new permissions cannot deliver these by their target year","None: new permissions can still meet every year")'),
]
for i, (k, f, d) in enumerate(res):
    rr = r + 1 + i
    ws.cell(rr, 1, k).font = bold
    c = ws.cell(rr, 3, f); c.number_format = INT; c.font = Font(name=F, size=12, bold=True, color=DARK)
    ws.cell(rr, 4, d).font = note

# year table
r = 29
ws.cell(r, 1, 'By year').font = h2
cols = ['Year', 'Target completions', 'Register expected', 'New completions needed', 'Starts needed', 'Permissions needed', 'Applications needed']
for j, h in enumerate(cols, 1):
    c = ws.cell(r + 1, j, h); c.font, c.fill = hdr_font, hdr_fill; c.alignment = Alignment(wrap_text=True, vertical='top')
ws.row_dimensions[r + 1].height = 30
YT0 = r + 2
for i, y in enumerate(BUCKETS):
    rr = YT0 + i
    ws.cell(rr, 1, '="Before "&TEXT($C$5,"d mmm yyyy")' if y == 0 else (y if y != 2026 else '="2026 (from "&TEXT($C$5,"d mmm")&")"'))
    for j, (title, *_rest) in enumerate(MEAS):
        top, _ = blk[title]
        cl = L(3 + i)
        ws.cell(rr, 2 + j, f"=INDEX('Pipeline calc'!${cl}${top}:${cl}${top + NP - 1},{PI})").number_format = INT
    if y == 0:
        for j in range(1, 8):
            ws.cell(rr, j).fill = band
YTE = YT0 + len(BUCKETS) - 1
ws.cell(YTE + 1, 1, 'Total').font = bold
for j in range(2, 8):
    c = ws.cell(YTE + 1, j, f'=SUM({L(j)}{YT0}:{L(j)}{YTE})'); c.number_format = INT; c.font = bold
# register grants (reference row, Limerick only); row 45
assert GR == YTE + 3, GR
ws.cell(GR - 1, 1, 'Homes granted per year in the register (Limerick, for comparison)').font = bold
for j, (y, v) in enumerate(WHATIF['granted'].items()):
    ws.cell(GR - 1, 3 + j, y).font = bold
    ws.cell(GR, 3 + j, v).number_format = INT
ws.cell(GR, 1, 'Homes granted').font = body
ws.cell(GR + 1, 1, 'The schemes the register records, not every permission in Limerick, so this is a floor.').font = note

# split of permissions needed from now
r = GR + 3
ws.cell(r, 1, 'Permissions needed from now, by bedrooms and tenure').font = h2
ws.cell(r + 1, 1, '="Using "&$C$4&"\'s own mix from its tab (set by the Intro levers), applied to every year."').font = note
for j, h in enumerate(['1-bed', '2-bed', '3-bed', '4+ bed', 'Private', 'Affordable', 'Social'], 2):
    c = ws.cell(r + 2, j, h); c.font, c.fill = hdr_font, hdr_fill
ws.cell(r + 3, 1, 'Share').font = bold; ws.cell(r + 4, 1, 'Homes to permit').font = bold
for j in range(7):
    ws.cell(r + 3, 2 + j, '=' + pick(L(cM0 + j))).number_format = PCT
    ws.cell(r + 4, 2 + j, f'={L(2 + j)}{r + 3}*$C$24').number_format = INT

# all places compared
r = r + 7
ws.cell(r, 1, 'All places compared (same settings)').font = h2
cmp_h = ['Place', 'Homes still to deliver', 'Permissions needed before now', 'Permissions needed from now', 'Permissions a year', 'Applications needed from now']
for j, h in enumerate(cmp_h, 1):
    c = ws.cell(r + 1, j, h); c.font, c.fill = hdr_font, hdr_fill; c.alignment = Alignment(wrap_text=True, vertical='top')
ws.row_dimensions[r + 1].height = 30
for p in range(NP):
    rr = r + 2 + p
    for j in range(6):
        c = ws.cell(rr, 1 + j, f"='Pipeline calc'!{L(1 + j)}{H0 + 1 + p}")
        if j:
            c.number_format = INT
        if p == 0:
            c.font = bold; c.fill = band
CMP_END = r + 1 + NP
nrow = CMP_END + 2
ws.cell(nrow, 1, 'Notes').font = h2
notes = [
    'Method: the target is spread evenly within each year from the status date; the 2026 target is cut to the part of the year after the status date. Each month\'s new completions are moved back by the build time to give starts, by the time to start to give permissions (divided by 1 − never started) and by the decision time to give applications (divided by 1 − refused). Anything that lands before the status date is "needed before now".',
    'Expected completions: the register\'s Q4 2026 figure is spread from the status date to December, 2027–2030 within each year, and the 2031+ tail within 2031. Years where the register already covers the target need no new homes; any surplus carries forward.',
    'Each step uses an average time, so the timing is approximate: real schemes spread around these averages.',
    'Targets come live from the catchment tabs, so they follow the Intro levers. Pipeline figures are values from the land register (Limerick_Developable_Land.gpkg); rebuild the tab to refresh them.',
    'Small schemes and one-off houses are not in the register, so they are inside the homes still to deliver here; they need permission too.',
    'Permissions needed are homes, not applications or schemes. Student bedspaces in the register count as homes in its expected completions, as in the tracker.',
]
for i, t in enumerate(notes):
    c = ws.cell(nrow + 1 + i, 1, t); c.font = note; c.alignment = Alignment(wrap_text=True, vertical='top')
    ws.merge_cells(start_row=nrow + 1 + i, start_column=1, end_row=nrow + 1 + i, end_column=8); ws.row_dimensions[nrow + 1 + i].height = 42

# chart: permissions needed by year
ch = BarChart(); ch.type = 'col'; ch.title = 'Homes needing permission each year'; ch.style = 10
ch.add_data(Reference(ws, min_col=6, min_row=YT0 - 1, max_row=YTE), titles_from_data=True)
ch.set_categories(Reference(ws, min_col=1, min_row=YT0, max_row=YTE))
ch.legend = None; ch.height, ch.width = 7.5, 16; ch.y_axis.numFmt = '#,##0'
ch.series[0].graphicalProperties.solidFill = '3F9B7E'
ws.add_chart(ch, 'J29')

for col, w in zip('ABCDEFGH', [34, 13, 13, 13, 13, 13, 13, 13]):
    ws.column_dimensions[col].width = w
for rr in range(4, 12):
    ws.cell(rr, 4).alignment = Alignment(wrap_text=False)
C.column_dimensions['A'].width = 24
C.sheet_state = 'visible'

I = wb['Intro']
for rr in range(31, 46):
    if I.cell(rr, 2).value == 'Opportunity sites & options':
        I.insert_rows(rr + 1)
        I.cell(rr + 1, 2, NAME).font = I.cell(rr, 2).font.copy()
        I.cell(rr + 1, 4, 'The planning pipeline, its expected completions, and how many homes need permission each year to meet the target (yellow levers for the timings).').font = I.cell(rr, 4).font.copy()
        break
for rr in range(31, 50):
    if I.cell(rr, 2).value == 'Data':
        I.insert_rows(rr + 1)
        I.cell(rr + 1, 2, 'Pipeline calc').font = I.cell(rr, 2).font.copy()
        I.cell(rr + 1, 4, 'Month-by-month working for the pipeline tab.').font = I.cell(rr, 4).font.copy()
        break
wb.save(OUT)
print('saved', OUT)
