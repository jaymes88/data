"""Excel version of the housing land register: same two tables as the GeoPackage, parcel totals as live SUMIFS on the
permissions sheet, dropdowns on the fields people edit, and a checks panel that catches double counting."""
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule

D = pd.read_pickle('land_register.pkl')
parcels, pp, YC, CL = D['parcels'].drop(columns='geometry'), D['pp'], D['YC'], D['CL']
XL = 'Limerick_Housing_Land_Register.xlsx'
MAXR = 3000                                          # formulas cover room for new rows
F = 'Arial'
HF = PatternFill('solid', fgColor='1F3A5F')
CALC = PatternFill('solid', fgColor='EEF2F7')       # calculated columns: do not type here
SUB = PatternFill('solid', fgColor='DCE4EE')
RED = PatternFill('solid', fgColor='F8D7DA')
TH = Side(style='thin', color='B7C3D0')
STATUSES = ['Complete', 'Under construction', 'Permitted – not started', 'Stalled', 'Expired – not started', 'In planning']
SOURCES = ['Council audit', 'Council audit – reinstated', 'Planning consent – not in council audit', 'Zoned land – no consent (estimate)', 'Council audit – county']
wb = Workbook()


def hdr(ws, row, cols, fills=None):
    for j, c in enumerate(cols, 1):
        x = ws.cell(row=row, column=j, value=c)
        x.font = Font(name=F, bold=True, color='FFFFFF', size=9)
        x.fill = HF if not fills or not fills[j - 1] else PatternFill('solid', fgColor='4F6F94')
        x.alignment = Alignment(wrap_text=True, vertical='top')
    ws.row_dimensions[row].height = 42


def val(v):
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime().date()
    return v


# ------------------------------------------------------------------ Permissions sheet
WP = wb.active
WP.title = 'Permissions'
pcols = ['perm_id', 'parcel_id', 'catchment', 'planning_ref', 'register_ref', 'scheme', 'units', 'student_bedspaces', 'status', 'status_source', 'status_cis',
         'geod_new_built', 'geod_new_undercon', 'geod_suggestion', 'geod_extract', 'counts_toward_totals',
         'relationship', 'tenure', 'delivery_body', 'route', 'final_grant', 'expiry', 'start_on_site', 'est_start', 'est_last_completions',
         'confidence'] + YC + ['match_basis', 'source', 'last_updated', 'notes']
pdat = pp[pcols].sort_values(['parcel_id', 'perm_id'])
heads = pcols + ['check']
hdr(WP, 1, heads, [h == 'check' for h in heads])
for i, row in enumerate(pdat.itertuples(index=False), 2):
    for j, v in enumerate(row, 1):
        c = WP.cell(row=i, column=j, value=val(v))
        c.font = Font(name=F, size=9)
pc = {h: L(j) for j, h in enumerate(heads, 1)}
PR = lambda h: f"Permissions!${pc[h]}$2:${pc[h]}${MAXR}"
for i in range(2, MAXR + 1):
    if i <= len(pdat) + 1 or i <= len(pdat) + 200:
        f = (f'=IF({pc["perm_id"]}{i}="","",IF(COUNTIF(Parcels!$A$2:$A${MAXR},{pc["parcel_id"]}{i})=0,"Parcel not found",'
             f'IF(COUNTIF($A$2:$A${MAXR},{pc["perm_id"]}{i})>1,"Duplicate perm_id",'
             f'IF(AND({pc["counts_toward_totals"]}{i}="Yes",{pc["planning_ref"]}{i}<>"",COUNTIFS($C$2:$C${MAXR},{pc["planning_ref"]}{i},${pc["counts_toward_totals"]}$2:${pc["counts_toward_totals"]}${MAXR},"Yes")>1),"Reference counted twice",'
             f'IF(COUNTIF(Lists!$A$2:$A$7,{pc["status"]}{i})=0,"Unknown status","")))))')
        c = WP.cell(row=i, column=len(heads), value=f)
        c.font = Font(name=F, size=9, bold=True, color='9C0006')
        c.fill = CALC
widths = {'status_source': 18, 'status_cis': 18, 'geod_suggestion': 26, 'perm_id': 10, 'parcel_id': 16, 'planning_ref': 12, 'register_ref': 12, 'scheme': 36, 'units': 7, 'student_bedspaces': 9, 'status': 20,
          'counts_toward_totals': 9, 'relationship': 22, 'tenure': 18, 'delivery_body': 18, 'route': 20, 'notes': 30, 'check': 22, 'source': 18}
for h, c in pc.items():
    WP.column_dimensions[c].width = widths.get(h, 11)
WP.freeze_panes = 'C2'
WP.auto_filter.ref = f'A1:{L(len(heads))}{len(pdat) + 1}'

# ------------------------------------------------------------------ Parcels sheet
WS = wb.create_sheet('Parcels', 0)
inputs = ['parcel_id', 'parcel_source', 'scope', 'catchment', 'catchment_type', 'catchment_share', 'catchment_basis', 'rsca', 'neighbourhood', 'lea', 'local_name', 'landowner', 'zoning', 'site_type', 'density_band',
          'developable_area_ha', 'mapped_area_ha', 'capacity_units', 'capacity_basis', 'plan_name', 'zone_gzt', 'phase', 'density_tier', 'density_dph',
          'density_basis', 'rzlt_2027_share', 'geod_addresses_now', 'geod_new_since_2019', 'register_status', 'notes', 'last_reviewed', 'reviewed_by']
calc = ['complete_units', 'under_construction_units', 'permitted_not_started_units', 'stalled_units', 'consented_units', 'expired_units',
        'in_planning_units', 'unconsented_capacity', 'total_supply_units', 'future_supply_units'] + YC + ['permissions', 'geod_new_built', 'parcel_status', 'flag']
heads = inputs + calc
hdr(WS, 1, heads, [h in calc for h in heads])
sc = {h: L(j) for j, h in enumerate(heads, 1)}
pdata = parcels[inputs].sort_values(['parcel_source', 'scope', 'neighbourhood', 'parcel_id'])
n = len(pdata)
for i, row in enumerate(pdata.itertuples(index=False), 2):
    for j, v in enumerate(row, 1):
        WS.cell(row=i, column=j, value=val(v)).font = Font(name=F, size=9)
    A = f'$A{i}'
    cnt = f'{PR("counts_toward_totals")},"Yes"'
    sm = lambda st: f'SUMIFS({PR("units")},{PR("parcel_id")},{A},{PR("status")},"{st}",{cnt})'
    f = {
        'complete_units': f'={sm("Complete")}', 'under_construction_units': f'={sm("Under construction")}',
        'permitted_not_started_units': f'={sm("Permitted – not started")}', 'stalled_units': f'={sm("Stalled")}',
        'consented_units': f'={sc["complete_units"]}{i}+{sc["under_construction_units"]}{i}+{sc["permitted_not_started_units"]}{i}+{sc["stalled_units"]}{i}',
        'expired_units': f'={sm("Expired – not started")}', 'in_planning_units': f'={sm("In planning")}',
        'unconsented_capacity': f'=IF({sc["capacity_units"]}{i}="",0,MAX({sc["capacity_units"]}{i}-{sc["consented_units"]}{i},0))',
        'total_supply_units': f'={sc["consented_units"]}{i}+{sc["unconsented_capacity"]}{i}',
        'future_supply_units': f'={sc["total_supply_units"]}{i}-{sc["complete_units"]}{i}',
        'permissions': f'=COUNTIFS({PR("parcel_id")},{A},{cnt})',
        'geod_new_built': f'=SUMIFS({PR("geod_new_built")},{PR("parcel_id")},{A},{cnt})',
        'parcel_status': (f'=IF(AND({sc["consented_units"]}{i}>0,{sc["complete_units"]}{i}>={sc["consented_units"]}{i},{sc["unconsented_capacity"]}{i}=0),"Built out",'
                          f'IF({sc["complete_units"]}{i}>0,"Partly built",IF({sc["consented_units"]}{i}>0,"Consented – not built","No consent")))'),
        'flag': (f'=IF(AND({sc["capacity_units"]}{i}<>"",{sc["consented_units"]}{i}>1.1*{sc["capacity_units"]}{i}),"Consented above capacity",'
                 f'IF(AND(LEFT({sc["parcel_source"]}{i},8)="Planning",{sc["permissions"]}{i}=0),"Consent parcel with no permission",'
                 f'IF(COUNTIF($A$2:$A${MAXR},{A})>1,"Duplicate parcel_id","")))'),
    }
    for y in YC:
        f[y] = f'=SUMIFS({PR(y)},{PR("parcel_id")},{A},{cnt})'
    for h in calc:
        c = WS.cell(row=i, column=heads.index(h) + 1, value=f[h])
        c.font = Font(name=F, size=9, bold=h in ('total_supply_units', 'flag'), color='9C0006' if h == 'flag' else '000000')
        c.fill = CALC
        c.number_format = '#,##0' if h not in YC else '#,##0.0'
        if h == 'parcel_status':
            c.font = Font(name=F, size=9, bold=True)
for h, c in sc.items():
    WS.column_dimensions[c].width = {'parcel_id': 18, 'parcel_source': 24, 'local_name': 32, 'notes': 34, 'capacity_basis': 22,
                                      'register_status': 18, 'flag': 22, 'parcel_status': 18, 'neighbourhood': 16, 'lea': 16}.get(h, 10)
WS.freeze_panes = 'B2'
WS.auto_filter.ref = f'A1:{L(len(heads))}{n + 1}'
SR = lambda h: f"Parcels!${sc[h]}$2:${sc[h]}${MAXR}"

# ------------------------------------------------------------------ Lists + validation
WL = wb.create_sheet('Lists')
for j, (h, vals) in enumerate([('status', STATUSES), ('counts_toward_totals', ['Yes', 'No']), ('parcel_source', SOURCES), ('scope', ['City', 'County'])], 1):
    WL.cell(row=1, column=j, value=h).font = Font(name=F, bold=True)
    for i, v in enumerate(vals, 2):
        WL.cell(row=i, column=j, value=v)
    WL.column_dimensions[L(j)].width = 36
for ws, col, src in [(WP, pc['status'], '=Lists!$A$2:$A$7'), (WP, pc['counts_toward_totals'], '=Lists!$B$2:$B$3'),
                     (WP, pc['parcel_id'], f'=Parcels!$A$2:$A${MAXR}'), (WS, sc['parcel_source'], '=Lists!$C$2:$C$6'),
                     (WS, sc['scope'], '=Lists!$D$2:$D$3')]:
    dv = DataValidation(type='list', formula1=src, allow_blank=True, showErrorMessage=True, errorTitle='Not in list', error='Pick a value from the list.')
    ws.add_data_validation(dv)
    dv.add(f'{col}2:{col}{MAXR}')
WP.conditional_formatting.add(f'{pc["check"]}2:{pc["check"]}{MAXR}', FormulaRule(formula=[f'LEN({pc["check"]}2)>0'], fill=RED))
WS.conditional_formatting.add(f'{sc["flag"]}2:{sc["flag"]}{MAXR}', FormulaRule(formula=[f'LEN({sc["flag"]}2)>0'], fill=RED))

# ------------------------------------------------------------------ Summary
SM = wb.create_sheet('Summary', 0)
SM.sheet_view.showGridLines = False
SM.column_dimensions['A'].width = 40
for c in 'BCDEFGHI':
    SM.column_dimensions[c].width = 14
SM['A1'] = 'Limerick housing land register'
SM['A1'].font = Font(name=F, bold=True, size=14, color='1F3A5F')
SM['A2'] = 'Council audit parcels plus parcels for residential consents outside the audit. Every permission is linked to one parcel; totals are calculated from the Permissions sheet.'
SM['A2'].font = Font(name=F, size=9, italic=True)


def put(r, c, v, fmt='#,##0', bold=False, fill=None):
    x = SM.cell(row=r, column=c, value=v)
    x.font = Font(name=F, size=10, bold=bold)
    x.number_format = fmt or 'General'
    x.border = Border(bottom=TH)
    if fill:
        x.fill = fill


r = 4
cols = ['Parcels', 'Developable ha', 'Consented', 'of which complete', 'Unconsented capacity', 'Total supply', 'Future supply']
fields = [None, 'developable_area_ha', 'consented_units', 'complete_units', 'unconsented_capacity', 'total_supply_units', 'future_supply_units']
for title, key, groups in [('By parcel source', 'parcel_source', SOURCES[:4]), ('By scope', 'scope', ['City', 'County']),
                          ('By catchment type', 'catchment_type', ['City neighbourhood', 'Key town', 'Large village', 'Rest of county']),
                          ('By parcel status', 'parcel_status', ['Built out', 'Partly built', 'Consented – not built', 'No consent'])]:
    SM.cell(row=r, column=1, value=title).font = Font(name=F, bold=True, size=11, color='1F3A5F')
    r += 1
    for j, h in enumerate([''] + cols, 1):
        x = SM.cell(row=r, column=j, value=h)
        x.font = Font(name=F, bold=True, color='FFFFFF', size=9)
        x.fill = HF
        x.alignment = Alignment(wrap_text=True)
    r += 1
    r0 = r
    for g in groups:
        put(r, 1, g, None)
        for j, fld in enumerate(fields, 2):
            put(r, j, f'=COUNTIFS({SR(key)},$A{r})' if fld is None else f'=SUMIFS({SR(fld)},{SR(key)},$A{r})', '#,##0.0' if fld == 'developable_area_ha' else '#,##0')
        r += 1
    put(r, 1, 'Total', None, bold=True, fill=SUB)
    for j in range(2, 9):
        put(r, j, f'=SUM({L(j)}{r0}:{L(j)}{r - 1})', '#,##0.0' if j == 3 else '#,##0', bold=True, fill=SUB)
    r += 2

SM.cell(row=r, column=1, value='Expected completions (consented schemes; estimates)').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
for j, y in enumerate(YC, 2):
    x = SM.cell(row=r, column=j, value=y.replace('est_', '').replace('_plus', '+').replace('_', ' ').upper().replace('Q4 2026', 'Q4 2026'))
    x.font = Font(name=F, bold=True, color='FFFFFF', size=9)
    x.fill = HF
SM.cell(row=r, column=1).fill = HF
r += 1
put(r, 1, 'All parcels', None)
for j, y in enumerate(YC, 2):
    put(r, j, f'=SUM({SR(y)})')
r += 2

SM.cell(row=r, column=1, value='Checks (all should be zero)').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
chk0 = r
for label, f in [
    ('Permissions with a problem (see check column)', f'=COUNTIF({PR("check")},"?*")'),
    ('Parcels with a flag', f'=COUNTIF({SR("flag")},"?*")-COUNTIF({SR("flag")},"Consented above capacity")'),
    ('Units on Permissions not reaching a parcel', f'=SUMIFS({PR("units")},{PR("counts_toward_totals")},"Yes")-SUM({SR("consented_units")})-SUM({SR("expired_units")})-SUM({SR("in_planning_units")})'),
    ('Permissions with no parcel_id', f'=COUNTIFS({PR("perm_id")},"?*",{PR("parcel_id")},"")'),
]:
    put(r, 1, label, None)
    put(r, 2, f, '#,##0', bold=True)
    r += 1
SM.conditional_formatting.add(f'B{chk0}:B{r - 1}', FormulaRule(formula=[f'B{chk0}<>0'], fill=RED))
put(r, 1, 'Parcels consented above council capacity (review capacity)', None)
put(r, 2, f'=COUNTIF({SR("flag")},"Consented above capacity")', '#,##0')
r += 2
SM.cell(row=r, column=1, value='Blue-grey columns are calculated. Edit only the white columns. capacity_units (council estimate on audit parcels, zoning estimate on zoned-land parcels) is the only unit figure typed on the Parcels sheet.').font = Font(name=F, size=9, italic=True)

# ------------------------------------------------------------------ How to update + dictionary
H = wb.create_sheet('How to update', 1)
H.column_dimensions['A'].width = 30
H.column_dimensions['B'].width = 120
steps = [
    ('The rule', 'One permission, one parcel. Units live only on the Permissions sheet. Parcel totals add them up, so a home cannot be counted twice. Parcels do not overlap.'),
    ('New permission on an existing parcel', 'Add a row to Permissions with a new perm_id, pick the parcel_id from the list, enter units and status, counts_toward_totals = Yes. The parcel totals update.'),
    ('New permission on new land', 'Draw a parcel in the GeoPackage from the planning boundary (clip out any existing parcel), id PC-<planning ref without slashes>, parcel_source = Planning consent – not in council audit. Add the same parcel row here, then the permission row.'),
    ('Amendment, repeat or extension of duration', 'Add the row with counts_toward_totals = No unless it replaces the counted permission. If it replaces it (e.g. a new scheme on the same land), set the old row to No and the new row to Yes.'),
    ('Status changes', 'Change status on the Permissions row (Permitted – not started → Under construction → Complete). Use building control commencement and completion notices as the source; note it in notes and update last_updated.'),
    ('Expired permissions', 'Set status to Expired – not started. The units drop out of consented supply; on an audit parcel the council capacity becomes unconsented capacity again.'),
    ('Capacity', 'Audit parcels: council estimate. Zoned-land parcels: zoned area x developable share x density (see density_basis). If a permission shows the capacity was wrong, update capacity_units and say why in notes. Consent parcels have no capacity figure: their supply is the consented units.'),
    ('Zoned land (interim)', 'Zoned-land parcels are estimates from new residential zoning not in any other parcel and not built on. When a permission is granted on one, draw the consent parcel and cut it out of the zoned parcel. When the county audit arrives, replace them.'),
    ('County audit', 'Add county audit parcels with parcel_source = Council audit – county and scope = County. Move county permissions onto them by changing parcel_id, then retire any consent parcel left empty (flag: Consent parcel with no permission).'),
    ('GeoDirectory', 'Each quarter, rerun the build with the new GeoDirectory extract. A scheme whose new built addresses reach 95% of its units moves to Complete (status_source says so); other differences are listed on the GeoDirectory checks sheet for a person to confirm.'),
    ('Retiring a parcel', 'Do not delete. parcel_status turns to Built out when every counted home is complete and no council capacity is left; filter Built out parcels off the map. Their homes stay in the delivery record.'),
    ('Checks', 'Summary sheet checks must all be zero before figures are reported. Red cells on Permissions (check column) and Parcels (flag) show what to fix.'),
]
for i, (k, v) in enumerate(steps, 1):
    H.cell(row=i, column=1, value=k).font = Font(name=F, bold=True, size=10)
    x = H.cell(row=i, column=2, value=v)
    x.font = Font(name=F, size=10)
    x.alignment = Alignment(wrap_text=True, vertical='top')
    H.cell(row=i, column=1).alignment = Alignment(vertical='top', wrap_text=True)
CW = wb.create_sheet('Catchments', 1)
CW.sheet_view.showGridLines = False
CW['A1'] = 'Supply by study catchment'
CW['A1'].font = Font(name=F, bold=True, size=14, color='1F3A5F')
CW['A2'] = 'Each parcel is assigned to the catchment it overlaps most. Parcels just outside a key town or village are added to it when zoned in its LAP, within 500 m, or named in the scheme and within 2 km (catchment_basis on Parcels). Live formulas on the Parcels sheet.'
CW['A2'].font = Font(name=F, size=9, italic=True)
ccols = [('Parcels', None), ('Developable ha', 'developable_area_ha'), ('Consented', 'consented_units'), ('Complete', 'complete_units'),
         ('Under construction', 'under_construction_units'), ('Permitted, not started', 'permitted_not_started_units'),
         ('Unconsented capacity', 'unconsented_capacity'), ('Total supply', 'total_supply_units'), ('Future supply', 'future_supply_units')] + \
        [(y.replace('est_', '').replace('_plus', '+').replace('_', ' ').upper(), y) for y in YC]
hdr(CW, 4, ['Catchment type', 'Catchment'] + [c[0] for c in ccols])
ORDER = ['City neighbourhood', 'Key town', 'Large village', 'Rest of county']
cat = parcels[['catchment_type', 'catchment']].drop_duplicates()
cat['o'] = cat.catchment_type.map({k: i for i, k in enumerate(ORDER)})
r = 5
for t in ORDER:
    sub = cat[cat.catchment_type.eq(t)].sort_values('catchment')
    r0 = r
    for c_ in sub.catchment:
        put = lambda rr, cc, v, fmt='#,##0', bold=False: (CW.cell(row=rr, column=cc, value=v), None)[0]
        CW.cell(row=r, column=1, value=t).font = Font(name=F, size=9)
        CW.cell(row=r, column=2, value=c_).font = Font(name=F, size=9)
        for j, (lab, fld) in enumerate(ccols, 3):
            f = f'=COUNTIFS({SR("catchment")},$B{r})' if fld is None else f'=SUMIFS({SR(fld)},{SR("catchment")},$B{r})'
            x = CW.cell(row=r, column=j, value=f)
            x.font = Font(name=F, size=9)
            x.number_format = '#,##0.0' if fld == 'developable_area_ha' else '#,##0'
        r += 1
    CW.cell(row=r, column=1, value=f'{t} total').font = Font(name=F, size=9, bold=True)
    for j in range(3, 3 + len(ccols)):
        x = CW.cell(row=r, column=j, value=f'=SUM({L(j)}{r0}:{L(j)}{r - 1})')
        x.font = Font(name=F, size=9, bold=True)
        x.fill = SUB
        x.number_format = '#,##0'
    CW.cell(row=r, column=1).fill = SUB
    CW.cell(row=r, column=2).fill = SUB
    r += 2
CW.column_dimensions['A'].width = 20
CW.column_dimensions['B'].width = 24
for j in range(3, 3 + len(ccols)):
    CW.column_dimensions[L(j)].width = 11
CW.freeze_panes = 'C5'

GW = wb.create_sheet('GeoDirectory checks')
GW['A1'] = 'GeoDirectory checks'
GW['A1'].font = Font(name=F, bold=True, size=14, color='1F3A5F')
ext = pp.geod_extract.iloc[0] if len(pp) else ''
GW['A2'] = f'GeoDirectory residential addresses, extract to {ext}. Counts only; no address data is held in this workbook.'
GW['A2'].font = Font(name=F, size=9, italic=True)
r = 4
GW.cell(row=r, column=1, value='1. Permissions where GeoDirectory and the recorded status differ').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
cols1 = ['perm_id', 'parcel_id', 'planning_ref', 'scheme', 'units', 'status_cis', 'status', 'geod_new_built', 'geod_new_undercon', 'geod_suggestion']
hdr(GW, r, cols1)
for row in pp[pp.geod_suggestion.ne('')].sort_values(['geod_suggestion', 'units'], ascending=[True, False])[cols1].itertuples(index=False):
    r += 1
    for j, v in enumerate(row, 1):
        GW.cell(row=r, column=j, value=val(v)).font = Font(name=F, size=9)
r += 3
GW.cell(row=r, column=1, value='2. Clusters of new addresses (since 2019) outside every parcel').font = Font(name=F, bold=True, size=11, color='1F3A5F')
r += 1
cols2 = ['cluster_id', 'scope', 'relevance', 'new_addresses', 'built', 'under_construction', 'streets', 'first_created', 'last_created', 'register_applications']
hdr(GW, r, cols2)
if len(CL):
    for row in CL.sort_values(['relevance', 'new_addresses'], ascending=[False, False])[cols2].itertuples(index=False):
        r += 1
        for j, v in enumerate(row, 1):
            GW.cell(row=r, column=j, value=val(v)).font = Font(name=F, size=9)
for j, w in enumerate([11, 16, 40, 36, 8, 18, 18, 10, 10, 30], 1):
    GW.column_dimensions[L(j)].width = w
DD = wb.create_sheet('Data dictionary')
import pyogrio
dd = pyogrio.read_dataframe('Limerick_Housing_Land_Register.gpkg', layer='data_dictionary')
for j, h in enumerate(['table', 'field', 'meaning'], 1):
    DD.cell(row=1, column=j, value=h).font = Font(name=F, bold=True)
for i, row in enumerate(dd.itertuples(index=False), 2):
    for j, v in enumerate(row, 1):
        x = DD.cell(row=i, column=j, value=v)
        x.alignment = Alignment(wrap_text=True, vertical='top')
DD.column_dimensions['A'].width = 18
DD.column_dimensions['B'].width = 34
DD.column_dimensions['C'].width = 110
wb.save(XL)
print('saved', XL, n, 'parcels', len(pdat), 'permissions')
