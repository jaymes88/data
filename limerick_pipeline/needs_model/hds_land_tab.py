"""Add a 'Zoned land vs need' tab to the HDS 2040 needs model.

Need side: live formulas into 'Land at Council density' (homes 2026-2040, Council density, land needed).
Supply side: the land register (identified land not yet built), by catchment, pasted as values with its date.
"""
import sys
import pandas as pd, geopandas as gpd, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

SRC, OUT = sys.argv[1], sys.argv[2]
REG = 'Limerick_Housing_Land_Register.gpkg'
p = gpd.read_file(REG, layer='parcel_summary')
a = p[p.parcel_status.ne('Finished')].copy()
a['dev'] = a.developable_area_ha.fillna(a.mapped_area_ha)
a['uncons_ha'] = a.dev * (a.unconsented_capacity / a.capacity_used.where(a.capacity_used > 0)).fillna(0).clip(0, 1)
man = a.capacity_manual.eq('Yes') if 'capacity_manual' in a else pd.Series(False, index=a.index)
a['fixed_homes'] = a.unconsented_capacity.where(man, 0)          # sites with a manually set capacity keep it
a.loc[man, 'uncons_ha'] = 0
a['cons_left'] = (a.consented_units - a.built_units).clip(lower=0)
# parcels shared between catchments (catchment_split, e.g. CITY-107 50/50 City Centre / Singland/Garryowen): one row per share
if 'catchment_split' in a:
    rows = []
    for _, r in a.iterrows():
        sp = str(r.catchment_split or '').strip()
        if not sp or sp in ('nan', 'None'):
            rows.append(r); continue
        for part in sp.split(';'):
            cat, w = part.rsplit(':', 1); w = float(w)
            x = r.copy(); x['catchment'] = cat.strip()
            for c in ['cons_left', 'uncons_ha', 'unconsented_capacity', 'fixed_homes']:
                x[c] = r[c] * w
            rows.append(x)
    a = pd.DataFrame(rows)
reg = a.groupby('catchment').agg(cons_left=('cons_left', 'sum'), uncons_ha=('uncons_ha', 'sum'), uncons_units=('unconsented_capacity', 'sum'), fixed=('fixed_homes', 'sum'),
                                 parcels=('parcel_id', 'size'))

wb = openpyxl.load_workbook(SRC)
L = wb['Land at Council density']
if 'Zoned land vs need' in wb.sheetnames:
    del wb['Zoned land vs need']
ws = wb.create_sheet('Zoned land vs need', index=wb.sheetnames.index('Land at Council density') + 1)

F = 'Arial'
DARK, MUTED, BAND = 'FF0E2925', 'FF3E5853', 'FFF4EFE8'
hdr_font, hdr_fill = Font(name=F, size=10, bold=True, color='FFFFFFFF'), PatternFill('solid', fgColor=DARK)
body, bold = Font(name=F, size=10), Font(name=F, size=10, bold=True)
note = Font(name=F, size=10, color=MUTED)
lever_font, lever_fill = Font(name=F, size=10, bold=True, color='FF0000FF'), PatternFill('solid', fgColor='FFE4E66A')
band = PatternFill('solid', fgColor=BAND)
INT, DEC = '#,##0;\\(#,##0\\);\\-', '#,##0.0;\\(#,##0.0\\);\\-'
SIGNED = '+#,##0;-#,##0;0'

ws['A1'] = 'Zoned land against 2040 need, at Council densities'; ws['A1'].font = Font(name=F, size=16, bold=True, color=DARK)
ws['A2'] = ('Homes needed 2026–2040 by catchment (this model) against the land already identified in the Limerick housing land register, '
            'with the identified land valued at the Council density used in the Land at Council density tab.')
ws['A2'].font = note
ws['A4'] = 'Headroom on the 2040 need'; ws['A4'].font = bold
ws['C4'] = 0.4; ws['C4'].font, ws['C4'].fill, ws['C4'].number_format = lever_font, lever_fill, '0%'
ws['D4'] = 'Change to test other headroom levels. The guidelines allow up to 50%.'; ws['D4'].font = note

heads = ['Catchment', 'Type of place', 'Council density (homes/ha)', 'Homes needed 2026–2040', 'Land needed at Council density (ha)',
         'Consented homes not yet built', 'Zoned land without consent (ha)', 'Homes on that land at Council density',
         'Identified supply (homes)', 'Identified supply as land (ha)', 'Surplus (+) / shortfall (−), homes', 'Enough zoned land?',
         'Additional land needed to 2040 (ha)', 'Homes to plan for with headroom', 'Additional land needed with headroom (ha)',
         'Register capacity of the unconsented land (homes)', 'Sites with a manually set capacity (homes, unconsented)']
HR = 6
for j, h in enumerate(heads, 1):
    c = ws.cell(HR, j, h); c.font, c.fill = hdr_font, hdr_fill
    c.alignment = Alignment(wrap_text=True, vertical='top')
ws.cell(HR - 1, 6, 'From the land register').font = bold
ws.cell(HR - 1, 4, 'From this model').font = bold

r0 = HR + 1
for k in range(24):                                    # neighbourhoods and settlements: rows 7-30 of 'Land at Council density'
    r, s = r0 + k, 7 + k
    name = L.cell(s, 1).value
    rg = reg.loc[name] if name in reg.index else None
    f = {1: f"='Land at Council density'!A{s}", 2: f"='Land at Council density'!B{s}", 3: f"='Land at Council density'!C{s}",
         4: f"='Land at Council density'!T{s}", 5: f"='Land at Council density'!U{s}",
         6: round(float(rg.cons_left), 0) if rg is not None else 0, 7: round(float(rg.uncons_ha), 2) if rg is not None else 0,
         8: f'=G{r}*C{r}+Q{r}', 9: f'=F{r}+H{r}', 10: f'=IF(C{r}>0,G{r}+F{r}/C{r},0)', 11: f'=I{r}-D{r}',
         12: f'=IF(K{r}>=0,"Yes","No")', 13: f'=IF(C{r}>0,MAX(D{r}-I{r},0)/C{r},0)', 14: f'=D{r}*(1+$C$4)',
         15: f'=IF(C{r}>0,MAX(N{r}-I{r},0)/C{r},0)', 16: round(float(rg.uncons_units), 0) if rg is not None else 0,
         17: round(float(rg.fixed), 0) if rg is not None else 0}
    for j, v in f.items():
        c = ws.cell(r, j, v); c.font = bold if j in (11, 13, 15) else body
        c.number_format = {3: '0.0', 5: DEC, 7: DEC, 10: DEC, 11: SIGNED, 13: DEC, 15: DEC}.get(j, INT if j not in (1, 2, 12) else 'General')
        if j in (6, 7, 16, 17):
            c.font = Font(name=F, size=10, color='FF000000')
rt = r0 + 24
ws.cell(rt, 1, 'Neighbourhoods and settlements').font = bold
for j in range(1, 18):
    c = ws.cell(rt, j); c.fill = band; c.font = bold
for j, L_ in [(4, 'D'), (5, 'E'), (6, 'F'), (7, 'G'), (8, 'H'), (9, 'I'), (10, 'J'), (11, 'K'), (13, 'M'), (14, 'N'), (15, 'O'), (16, 'P'), (17, 'Q')]:
    c = ws.cell(rt, j, f'=SUM({L_}{r0}:{L_}{rt - 1})'); c.number_format = ws.cell(r0, j).number_format
ws.cell(rt, 3, f'=IF(E{rt}>0,D{rt}/E{rt},0)').number_format = '0.0'
ws.cell(rt, 12, f'=COUNTIF(L{r0}:L{rt - 1},"No")&" of 24 short"')
# the remainder of the county is outside the study: its homes are shown for completeness only, in muted text
rr = rt + 1
for j, v in {1: 'Remainder of county (not analysed)', 2: "='Land at Council density'!B31", 4: "='Land at Council density'!T31"}.items():
    c = ws.cell(rr, j, v); c.font = note; c.number_format = INT if j == 4 else 'General'
ws.cell(rr, 5, 'Outside the scope of this study; not assessed against land').font = note

# by type of place
tr = rt + 3
ws.cell(tr, 1, 'By type of place').font = Font(name=F, size=12, bold=True, color=DARK)
for j, h in enumerate(['Type of place', '', '', 'Homes needed', 'Land needed (ha)', 'Consented not built', 'Zoned land without consent (ha)',
                       'Homes on that land', 'Identified supply', 'Supply as land (ha)', 'Surplus / shortfall', 'Catchments short',
                       'Additional land to 2040 (ha)', 'Homes with headroom', 'Additional land with headroom (ha)', 'Register capacity', 'Manually set (homes)'], 1):
    c = ws.cell(tr + 1, j, h); c.font, c.fill = hdr_font, hdr_fill; c.alignment = Alignment(wrap_text=True, vertical='top')
for k, t in enumerate(['City neighbourhood', 'Key town', 'Village']):
    r = tr + 2 + k
    ws.cell(r, 1, t).font = body
    for j, L_ in [(4, 'D'), (5, 'E'), (6, 'F'), (7, 'G'), (8, 'H'), (9, 'I'), (10, 'J'), (11, 'K'), (13, 'M'), (14, 'N'), (15, 'O'), (16, 'P'), (17, 'Q')]:
        c = ws.cell(r, j, f'=SUMIFS({L_}${r0}:{L_}${rt - 1},$B${r0}:$B${rt - 1},$A{r})'); c.font = body
        c.number_format = ws.cell(r0, j).number_format
    ws.cell(r, 12, f'=COUNTIFS($B${r0}:$B${rt - 1},$A{r},$L${r0}:$L${rt - 1},"No")').font = body

nr = tr + 7
notes = [
    'How to read it',
    'Identified supply = consented homes not yet built + the register’s zoned land without consent valued at the Council density. Surplus or shortfall = identified supply − homes needed 2026–2040.',
    'Additional land needed = the shortfall ÷ the Council density (net residential ha). With headroom: (homes needed × (1 + headroom) − identified supply) ÷ Council density. A catchment in surplus needs no additional land; its surplus is not moved to other catchments.',
    'Manually set capacity: where the register holds a capacity set by hand (column Q; e.g. the masterplanned city-centre site CITY-107, 2,500 homes), that figure is used instead of land × Council density, and its land is left out of column G.',
    'Shared sites: the masterplanned city-centre site CITY-107 straddles City Centre and Singland/Garryowen, so its land and its 2,500 homes are split 50/50 between them.',
    'Supply as land = zoned land without consent + consented homes ÷ Council density, for comparison with the land needed column.',
    'Land register: Limerick_Housing_Land_Register.gpkg, parcels not yet finished (built-out parcels excluded), as at the October 2026 build. Zoned land without consent = developable area × the share of the parcel’s capacity not yet consented. It includes the city and county council audits, the analyst’s zoned-land estimates for towns the county audit does not cover, and council-supplied sites.',
    'The register’s own capacity for the same land (last column) uses the council audit and site densities, not the Variation No. 3 ranges, so it differs from “Homes on that land at Council density”.',
    'Homes completed in 2026 count in the need but not in the supply (the register nets them off as built), so shortfalls are slightly overstated for 2026.',
    'The study covers the city neighbourhoods, key towns and villages. The remainder of the county is shown below the total for completeness only; it has not been assessed against land.',
    'Land is net residential land; it excludes roads, open space, schools and land that will not activate. See the activation discussion before treating the headroom figures as a zoning target.',
]
for i, t in enumerate(notes):
    c = ws.cell(nr + i, 1, t); c.font = Font(name=F, size=12, bold=True, color=DARK) if i == 0 else note

widths = [24, 18, 11, 11, 12, 12, 12, 12, 12, 12, 13, 10, 13, 12, 13, 13, 13]
for j, w in enumerate(widths, 1):
    ws.column_dimensions[openpyxl.utils.get_column_letter(j)].width = w
ws.row_dimensions[HR].height = 54; ws.row_dimensions[tr + 1].height = 42
ws.freeze_panes = 'C7'
# list the tab on the Intro sheet
I = wb['Intro']
for r in range(31, 40):
    if I.cell(r, 2).value == 'Land at Council density':
        I.insert_rows(r + 1)
        I.cell(r + 1, 2, 'Zoned land vs need').font = I.cell(r, 2).font.copy()
        I.cell(r + 1, 4, 'Land already identified in the land register against the 2040 need at Council densities: shortfall, additional land to 2040, and with headroom (yellow lever).').font = I.cell(r, 4).font.copy()
        break
wb.save(OUT)
print('saved', OUT)
