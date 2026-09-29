import re, json
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule

SRC = 'lp.xlsx'
x = pd.read_excel(SRC, sheet_name=None, dtype={'Reference': str})
full = x['Full Project Pipeline'].copy()
ex = x['Existing Site Pipeline'].copy()
expiry = x['Existing Expiry Review'].set_index('Site Group ID')
reg = pd.read_pickle('reg.pkl')
reg['ref'] = reg.ApplicationNumber.astype(str).str.strip()
reg = reg.drop_duplicates('ref')
abp = json.load(open('abp.json'))

full['ref'] = full.Reference.fillna('').str.strip()
full['Units'] = pd.to_numeric(full.Units, errors='coerce')
for c in ['Application Date', 'Decision Date', 'Start Date', 'Finish Date', 'Last Updated']:
    full[c] = pd.to_datetime(full[c], errors='coerce')

def nz(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NaT or (hasattr(pd, 'isna') and pd.isna(v)) else v

def dist(lat1, lon1, lat2, lon2):
    return np.sqrt(((lat1 - lat2) * 111000) ** 2 + ((lon1 - lon2) * 67000) ** 2)

# ---------- extension of duration lookup (parent ref parsed from EoD description) ----------
eod = {}
for _, r in reg[reg.ApplicationType == 'EXTENSION OF DURATION'].sort_values('ReceivedDate').iterrows():
    for yy, n in re.findall(r'(\d{2})\s*/\s*(\d+)', str(r.DevelopmentDescription)):
        eod[yy + n] = r

# ---------- register outcome per application ----------
def outcome(r):
    ad = str(r.AppealDecision or '').upper()
    st = str(r.ApplicationStatus or '').upper()
    dc = str(r.Decision or '').upper()
    if ad in ('CONDITIONAL', 'MODIFIED'):
        return 'Granted on appeal'
    if ad == 'REFUSED':
        return 'Refused on appeal'
    if 'WITHDRAWN' in st:
        return 'Withdrawn'
    if 'INCOMPLETE' in st:
        return 'Invalid'
    if dc == 'REFUSED':
        return 'Refused'
    if dc in ('CONDITIONAL', 'UNCONDITIONAL'):
        return 'Granted'
    if st.startswith('APPEALED') or st == 'LEAVE TO APPEAL':
        return 'Under appeal'
    return 'Pending'

regpts = reg[reg.lat.notna() & (reg.NumResidentialUnits.fillna(0) > 0) & (reg.ApplicationType != 'EXTENSION OF DURATION')]

CISREFS = set(full.ref)

def later_nearby(lat, lon, after, own):
    if lat is None or pd.isna(lat) or pd.isna(after):
        return ''
    d = dist(regpts.lat, regpts.lon, lat, lon)
    c = regpts[(d < 150) & (regpts.ReceivedDate > after) & (regpts.ref != own) & (regpts.NumResidentialUnits >= 3)]
    if c.empty:
        return ''
    r = c.sort_values(['NumResidentialUnits', 'ReceivedDate']).iloc[-1]
    tag = 'in CIS' if r.ref in CISREFS else 'NOT in CIS'
    return f"{r.ref} ({r.ReceivedDate:%d/%m/%Y}, {outcome(r)}, {int(r.NumResidentialUnits)} units, {tag})"

apps = []
for _, a in full.iterrows():
    rec = dict(found='No reference', reg_ref='', status='', decision='', appeal='', outcome='', reg_dec=None,
               grant=None, reg_exp=None, eod='', exp_final=None, reg_units=None, reg_desc='', locdiff=None,
               later='', link='')
    ref = a.ref
    if ref and ref in set(reg.ref):
        r = reg[reg.ref == ref].iloc[0]
        o = outcome(r)
        rec.update(found='Council register', reg_ref=ref, status=r.ApplicationStatus, decision=r.Decision,
                   appeal=r.AppealDecision or '', outcome=o, reg_dec=nz(r.DecisionDate), grant=nz(r.GrantDate),
                   reg_exp=nz(r.ExpiryDate), reg_units=nz(r.NumResidentialUnits) or None,
                   reg_desc=str(r.DevelopmentDescription)[:300], link=r.LinkAppDetails or '')
        if pd.notna(a.Latitude) and pd.notna(r.lat):
            rec['locdiff'] = round(float(dist(a.Latitude, a.Longitude, r.lat, r.lon)))
        rec['exp_final'] = rec['reg_exp']
        if ref in eod:
            e = eod[ref]
            rec['eod'] = f"{e.ref}: {outcome(e)}" + (f", expires {e.ExpiryDate:%d/%m/%Y}" if pd.notna(e.ExpiryDate) else '')
            if outcome(e) in ('Granted', 'Granted on appeal') and pd.notna(e.ExpiryDate):
                rec['exp_final'] = e.ExpiryDate
        if o in ('Refused', 'Refused on appeal', 'Withdrawn', 'Invalid'):
            rec['later'] = later_nearby(a.Latitude, a.Longitude, r.ReceivedDate, ref)
    elif ref.startswith('ABPREF') and ref[6:] in abp:
        b = abp[ref[6:]]
        signed = pd.to_datetime(b['signed'], dayfirst=True)
        yrs = 10 if 'ten year' in b['desc'].lower() else 5
        rec.update(found='An Coimisiún Pleanála', reg_ref='ABP-' + ref[6:], decision=b['decision'],
                   outcome='Granted' if 'grant' in b['decision'].lower() else ('Refused' if 'refus' in b['decision'].lower() else 'Pending'),
                   reg_dec=signed, reg_exp=signed + pd.DateOffset(years=yrs) - pd.Timedelta(days=1),
                   reg_desc=b['desc'][:300], link=b['url'])
        rec['exp_final'] = rec['reg_exp']
        m = re.search(r'(\d+)\s*no\.?\s*(?:residential units|Build to Rent apartments)', b['desc'])
        rec['reg_units'] = int(m.group(1)) if m else None
        rec['status'] = f'{yrs}-year permission (expiry = date signed + {yrs} years)'
    elif ref:
        rec['found'] = 'Not in council register'
        rec['outcome'] = 'Not in council register'
    else:
        rec['outcome'] = 'No reference'
    apps.append(rec)
A = pd.concat([full.reset_index(drop=True), pd.DataFrame(apps)], axis=1)

# ---------- site assignment ----------
pid2site = {}
for _, s in ex.iterrows():
    for p in str(s['Related Project IDs']).split(','):
        pid2site[int(p)] = s['Site Group ID']
granted = A[A['Source Dataset'].str.startswith('Granted')]
up = A[A['Source Dataset'].str.startswith('Latest') & (A['Residential Pipeline Included'] == 'Yes')]

SETTLE = ['Mungret', 'Annacotty', 'Patrickswell', 'Newcastle West', 'Kilmallock', 'Adare', 'Bruff', 'Cappamore',
          'Rathkeale', 'Castleconnel', 'Caherconlish', 'Abbeyfeale']
CITY = ['Limerick City', 'Moyross', 'Thomondgate', 'Thomondghate', 'Singland', 'Dooradoyle', 'Raheen', 'Southill',
        'Castletroy', 'Corbally', 'Caherdavin', 'Crossagalla', 'Kennedy Park', "King's Island", 'Dock Road',
        'South Circular', 'Mary Street', 'Parnell', 'New Road', 'Dublin Road', 'Rosbrien', 'Limerick']

def settlement(addr):
    for s in SETTLE:
        if s.lower() in addr.lower():
            return 'Castleconnell' if s == 'Castleconnel' else s
    for c in CITY:
        if c.lower() in addr.lower():
            return 'Limerick City and Suburbs'
    return 'Other County Limerick'

def addr(r):
    parts = [r[f'Project Site Address Line {i}'] for i in range(1, 6)]
    return ', '.join(str(p).strip() for p in parts if pd.notna(p) and str(p).strip())

def dtype(r):
    h = str(r['Project Heading']).lower()
    if 'student' in h or (pd.notna(r['Student Bedspaces']) and r['Student Bedspaces'] > 0):
        return 'Student accommodation'
    ap, ho = r['Total Apartments'], r['Total Houses']
    if pd.notna(ap) and pd.notna(ho) and ap > 0 and ho > 0:
        return 'Mixed houses and apartments'
    if pd.notna(ap) and ap > 0:
        return 'Apartments'
    if pd.notna(ho) and ho > 0:
        return 'Houses / dwellings'
    return 'Other / unclear'

sites = []
lowconf = set(x['Existing Site Review']['Site Group ID'])
for _, s in ex.iterrows():
    sid = s['Site Group ID']
    recs = granted[granted['Project Id'].map(pid2site) == sid]
    best = recs.sort_values('Units', ascending=False).iloc[0]
    exps = recs.exp_final.dropna()
    stat = expiry.loc[sid, 'Group Expiry Screening Status'] if sid in expiry.index else ''
    sites.append(dict(
        sid=sid, origin='Granted/delivery export (grouped)', heading=s['Site / Project Heading'], address=s['Address'],
        settlement=s['Settlement'], lat=s['Latitude'], lon=s['Longitude'], n=s['Application Records'],
        pids=s['Related Project IDs'], stage=s['Current Stage'], tier=s['Delivery Band'], dtype=s['Dwelling Type'],
        units=nz(s['Permitted Units Proxy']), done=nz(s['Units Completed Stated']),
        apts=nz(best['Total Apartments']), houses=nz(best['Total Houses']), beds=nz(best['Student Bedspaces']),
        mixsrc=best['Unit Mix Source'], dec=nz(s['Decision Date']), upd=nz(pd.to_datetime(s['Latest Update Date'])),
        regexp=exps.max() if len(exps) else None, cisexp=stat, overlap='', lowconf='Yes' if sid in lowconf else 'No'))

# overlap check for upstream records against granted records and earlier upstream records
up = up.sort_values('Application Date')
seen = []
for _, r in up.iterrows():
    sid = f"U-{r['Project Id']}"
    pid2site[r['Project Id']] = sid
    notes = []
    if pd.notna(r.Latitude):
        d = dist(granted.Latitude, granted.Longitude, r.Latitude, r.Longitude)
        for j in d[d < 150].sort_values().index[:2]:
            g = granted.loc[j]
            notes.append(f"{pid2site[g['Project Id']]} ({int(d[j])}m): {g['Project Heading'][:45]}, {g['Pipeline Stage']}, {int(g.Units) if pd.notna(g.Units) else '?'} units")
        for o in seen:
            dd = dist(o[1], o[2], r.Latitude, r.Longitude)
            if dd < 150:
                notes.append(f"{o[0]} ({int(dd)}m): {o[3][:45]}, {o[4]}, {o[5]} units")
        seen.append((sid, r.Latitude, r.Longitude, r['Project Heading'], r['Pipeline Stage'],
                     int(r.Units) if pd.notna(r.Units) else '?'))
    a = addr(r)
    sites.append(dict(
        sid=sid, origin='Latest upstream export', heading=r['Project Heading'], address=a, settlement=settlement(a),
        lat=nz(r.Latitude), lon=nz(r.Longitude), n=1, pids=str(r['Project Id']), stage=r['Pipeline Stage'],
        tier=r['Delivery Tier'], dtype=dtype(r), units=nz(r.Units), done=None, apts=nz(r['Total Apartments']),
        houses=nz(r['Total Houses']), beds=nz(r['Student Bedspaces']), mixsrc=r['Unit Mix Source'],
        dec=nz(r['Decision Date']), upd=nz(r['Last Updated']), regexp=nz(r.exp_final), cisexp='',
        overlap='; '.join(notes), lowconf='No'))
S = pd.DataFrame(sites)
A['site'] = A['Project Id'].map(pid2site).fillna('')

# ---------- workbook ----------
wb = Workbook()
F = 'Arial'
HFILL = PatternFill('solid', fgColor='1F3A5F')
INFILL = PatternFill('solid', fgColor='FFF2CC')
REGFILL = PatternFill('solid', fgColor='E2EFDA')
thin = Side(style='thin', color='BFBFBF')

def header(ws, row, cols, fill=HFILL):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font = Font(name=F, bold=True, color='FFFFFF', size=10)
        cell.fill = fill
        cell.alignment = Alignment(wrap_text=True, vertical='top')

def style_body(ws, r0, r1, c1):
    for row in ws.iter_rows(min_row=r0, max_row=r1, max_col=c1):
        for c in row:
            if c.font.name != F or not c.font.bold:
                c.font = Font(name=F, size=10, color=c.font.color.rgb if c.font and c.font.color and isinstance(c.font.color.rgb, str) else None)

DATE = 'dd/mm/yyyy'
NUM = '#,##0;(#,##0);-'

# ---- Method ----
M = wb.active
M.title = 'Method'
M['A1'] = 'Limerick Residential Pipeline – Method and Assumptions'
M['A1'].font = Font(name=F, bold=True, size=14)
M['A3'] = 'Assumptions (edit the yellow cells)'
M['A3'].font = Font(name=F, bold=True, size=11)
assump = [
    ('Report date', pd.Timestamp('2026-09-29'), 'Date the register was queried. Used for staleness and expiry tests.'),
    ('Stale threshold (months)', 24, 'A Permission Granted / Commencement Expected site with no CIS update for longer than this is reported as Constrained / uncertain until checked.'),
    ('Overlap search radius (m)', 150, 'Used at build time to flag upstream records near another record. Changing it does not re-run the search.'),
    ('Location mismatch threshold (m)', 500, 'Register point more than this far from the CIS point is flagged as a possible reference mismatch.'),
]
for i, (k, v, n) in enumerate(assump, start=4):
    M.cell(row=i, column=1, value=k)
    c = M.cell(row=i, column=2, value=v)
    c.fill = INFILL
    c.font = Font(name=F, color='0000FF')
    if isinstance(v, pd.Timestamp):
        c.number_format = DATE
    M.cell(row=i, column=3, value=n)
RD, STALE, LOCM = "Method!$B$4", "Method!$B$5", "Method!$B$7"

notes = [
    ('Sources', ''),
    ('CIS granted/delivery export', 'Granted/delivery records and their site grouping taken from the Existing Site Pipeline tab of Limerick_Residential_Pipeline_Full_Build.xlsx (226 application records grouped into 153 sites).'),
    ('CIS upstream export', 'Export 20260923095518.xls, as de-duplicated in the source workbook (55 records; 3 non-residential frameworks excluded).'),
    ('Planning register', 'National Planning Applications dataset (Department of Housing, Local Government and Heritage), ArcGIS feature service IrishPlanningApplications, filtered to Limerick County Council. 12,835 records, received 2017 onwards. Queried 29/09/2026.'),
    ('An Coimisiún Pleanála', 'SHD case pages at pleanala.ie/en-ie/case/<number>, read 29/09/2026 for the 6 records with ABP references.'),
    ('', ''),
    ('Rules', ''),
    ('Unit of analysis', 'One row per site on the Sites tab. All headline figures come from Sites, so multiple applications on one site are not summed.'),
    ('Units on grouped sites', 'Maximum unit count across the related applications, not the sum (method carried over from the source workbook). Unit mix is taken from the record with the highest unit count.'),
    ('Delivered stock', 'Complete sites are reported as Delivered and kept out of pipeline totals.'),
    ('Student accommodation', 'Student units and bedspaces are reported separately from general dwellings and never added to them.'),
    ('Register outcome', 'Appeal decision overrides the council decision (CONDITIONAL or MODIFIED on appeal = Granted on appeal). Withdrawn, deemed withdrawn and incomplete applications are treated as not live.'),
    ('Expiry', 'Register expiry date is used where one exists, replaced by the expiry of a granted Extension of Duration where one references the parent file number. CIS decision date + 5 years is used only as a fallback.'),
    ('Reporting Tier', 'Starts from the CIS tier. Analyst Decision overrides everything. Otherwise: Complete = Delivered; a site whose register applications are all refused/withdrawn/invalid (and not on site) = Excluded; a Permission Granted or Commencement Expected site that is past expiry or stale = Constrained / uncertain.'),
    ('Upstream overlaps', 'Upstream records within the search radius of another record are flagged, not merged. Resolve by setting Analyst Decision on the Sites tab.'),
    ('', ''),
    ('Limitations', ''),
    ('Part 8 schemes', 'Council own-development (Part 8) references are not in the national register, so these records are shown as Not in council register and remain unverified.'),
    ('Pre-2017 applications', 'The national dataset starts in 2017. Older references will not match.'),
    ('Register unit counts', 'NumResidentialUnits is blank or zero on many register records, so a unit mismatch is only tested where the register gives a number.'),
    ('Extension of Duration', 'Matched by file number quoted in the EoD description. EoDs that do not quote the parent number are missed.'),
    ('Legal position', 'This is a screening exercise. It does not confirm the legal status of any permission; check the planning file before relying on an individual result.'),
    ('', ''),
    ('How to use', ''),
    ('Yellow cells', 'Inputs. Analyst Decision and Analyst Note on Sites; assumptions above. Everything else is data or formula.'),
    ('Review Queue', 'Sites flagged at build, largest first. Set the decision on the Sites tab; the queue status updates.'),
    ('Register Not in CIS', 'Reverse check: live register applications of 10+ units that have no matching reference in CIS. Some are phases of sites already in CIS (see nearest-site distance); others are gaps in the CIS data.'),
    ('Delivered figure', 'Delivered counts sites whose current stage is Complete. Completed phases on sites that are still active are not included, so it is lower than the sum of completed application records.'),
    ('Contacts', 'Project team names and emails from CIS are not carried into this file. Keep them in the source workbook.'),
]
r0 = 10
for i, (k, v) in enumerate(notes):
    a = M.cell(row=r0 + i, column=1, value=k)
    b = M.cell(row=r0 + i, column=2, value=v)
    if v == '' and k:
        a.font = Font(name=F, bold=True, size=11)
    else:
        a.font = Font(name=F, bold=True, size=10)
        b.font = Font(name=F, size=10)
    M.merge_cells(start_row=r0 + i, start_column=2, end_row=r0 + i, end_column=3)
    b.alignment = Alignment(wrap_text=True, vertical='top')
for r in range(4, 8):
    for c in (1, 3):
        M.cell(row=r, column=c).font = Font(name=F, size=10, bold=(c == 1))
    M.cell(row=r, column=3).alignment = Alignment(wrap_text=True, vertical='top')
M.column_dimensions['A'].width = 30
M.column_dimensions['B'].width = 16
M.column_dimensions['C'].width = 110

# ---- Sites ----
SW = wb.create_sheet('Sites')
scols = ['Site ID', 'Origin', 'Site / Project Heading', 'Address', 'Settlement', 'Latitude', 'Longitude',
         'Application Records', 'Project IDs', 'CIS Stage', 'CIS Tier', 'Dwelling Type', 'Permitted / Stated Units',
         'Units Completed (stated)', 'Units Remaining', 'Apartments (known)', 'Houses (known)', 'Student Bedspaces',
         'Unit Mix Source', 'CIS Decision Date', 'Last CIS Update', 'Months Since Update', 'Stale?',
         'Register Expiry (latest)', 'Expiry Used', 'Past Expiry?', 'Live Register Apps', 'Dead Register Apps',
         'Register Conflict?', 'Possible Overlap', 'Low-Confidence Grouping', 'Review Required',
         'Analyst Decision', 'Analyst Note', 'Reporting Tier', 'Tier Reason', 'General Dwellings Counted',
         'Student Units Counted', 'Student Bedspaces Counted', 'CIS Expiry Screen (source workbook)']
C = {n: L(i) for i, n in enumerate(scols, 1)}
header(SW, 1, scols)
n = len(S)
last = n + 1
APPLAST = len(A) + 1
for i, s in enumerate(S.itertuples(), start=2):
    v = [s.sid, s.origin, s.heading, s.address, s.settlement, s.lat, s.lon, s.n, s.pids, s.stage, s.tier, s.dtype,
         s.units, s.done]
    for j, val in enumerate(v, 1):
        SW.cell(row=i, column=j, value=nz(val))
    c = lambda k: f"{C[k]}{i}"
    SW[c('Units Remaining')] = f'=IF({c("Permitted / Stated Units")}="","",IF({c("CIS Stage")}="Complete",0,MAX({c("Permitted / Stated Units")}-N({c("Units Completed (stated)")}),0)))'
    SW[c('Apartments (known)')] = nz(s.apts)
    SW[c('Houses (known)')] = nz(s.houses)
    SW[c('Student Bedspaces')] = nz(s.beds)
    SW[c('Unit Mix Source')] = s.mixsrc
    SW[c('CIS Decision Date')] = nz(s.dec)
    SW[c('Last CIS Update')] = nz(s.upd)
    SW[c('Months Since Update')] = f'=IF({c("Last CIS Update")}="","",ROUND(({RD}-{c("Last CIS Update")})/30.44,0))'
    SW[c('Stale?')] = f'=IF({c("Months Since Update")}="","No",IF({c("Months Since Update")}>{STALE},"Yes","No"))'
    SW[c('Register Expiry (latest)')] = nz(s.regexp)
    SW[c('Expiry Used')] = f'=IF({c("Register Expiry (latest)")}<>"",{c("Register Expiry (latest)")},IF({c("CIS Decision Date")}<>"",EDATE({c("CIS Decision Date")},60),""))'
    st = c('CIS Stage')
    SW[c('Past Expiry?')] = f'=IF(AND({c("Expiry Used")}<>"",OR({st}="Permission Granted",{st}="Commencement Expected",{st}="Stalled or Suspended")),IF({c("Expiry Used")}<{RD},"Yes","No"),"No")'
    rngS, rngO = f"Applications!$B$2:$B${APPLAST}", f"Applications!$AA$2:$AA${APPLAST}"
    live = '+'.join(f'COUNTIFS({rngS},{c("Site ID")},{rngO},"{o}")' for o in ['Granted', 'Granted on appeal', 'Pending', 'Under appeal', 'Not in council register', 'No reference'])
    dead = '+'.join(f'COUNTIFS({rngS},{c("Site ID")},{rngO},"{o}")' for o in ['Refused', 'Refused on appeal', 'Withdrawn', 'Invalid'])
    SW[c('Live Register Apps')] = '=' + live
    SW[c('Dead Register Apps')] = '=' + dead
    SW[c('Register Conflict?')] = f'=IF(AND({c("Dead Register Apps")}>0,{c("Live Register Apps")}=0),"Yes","No")'
    SW[c('Possible Overlap')] = s.overlap or None
    SW[c('Low-Confidence Grouping')] = s.lowconf
    SW[c('Review Required')] = (f'=IF(OR({c("Stale?")}="Yes",{c("Past Expiry?")}="Yes",{c("Register Conflict?")}="Yes",'
                                f'{c("Possible Overlap")}<>"",{c("Low-Confidence Grouping")}="Yes"),IF({c("Analyst Decision")}="","Yes","Resolved"),"No")')
    for k in ('Analyst Decision', 'Analyst Note'):
        SW[c(k)].fill = INFILL
        SW[c(k)].font = Font(name=F, size=10, color='0000FF')
    dec, tier = c('Analyst Decision'), c('CIS Tier')
    onsite = f'OR({st}="On Site",{st}="Part Complete",{st}="Complete")'
    pg = f'OR({st}="Permission Granted",{st}="Commencement Expected")'
    SW[c('Reporting Tier')] = (
        f'=IF(OR({dec}="Duplicate – exclude",{dec}="Lapsed or dead"),"Excluded",IF({dec}="Constrained","Constrained / uncertain",'
        f'IF({dec}="Confirmed live",{tier},IF({st}="Complete","Delivered",IF(AND({c("Register Conflict?")}="Yes",NOT({onsite})),"Excluded",'
        f'IF(AND({pg},OR({c("Stale?")}="Yes",{c("Past Expiry?")}="Yes")),"Constrained / uncertain",{tier}))))))')
    SW[c('Tier Reason')] = (
        f'=IF({dec}<>"","Analyst: "&{dec},IF({st}="Complete","Complete",IF(AND({c("Register Conflict?")}="Yes",NOT({onsite})),"Register: refused / withdrawn",'
        f'IF(AND({pg},{c("Past Expiry?")}="Yes"),"Past expiry",IF(AND({pg},{c("Stale?")}="Yes"),"No CIS update in "&{c("Months Since Update")}&" months","As CIS")))))')
    rt, dt = c('Reporting Tier'), c('Dwelling Type')
    excl = f'OR({rt}="Excluded",{rt}="Delivered")'
    SW[c('General Dwellings Counted')] = f'=IF(OR({excl},{dt}="Student accommodation"),0,N({c("Units Remaining")}))'
    SW[c('Student Units Counted')] = f'=IF(OR({excl},{dt}<>"Student accommodation"),0,N({c("Units Remaining")}))'
    SW[c('Student Bedspaces Counted')] = f'=IF({excl},0,N({c("Student Bedspaces")}))'
    SW[c('CIS Expiry Screen (source workbook)')] = s.cisexp or None
dv = DataValidation(type='list', formula1='"Confirmed live,Constrained,Lapsed or dead,Duplicate – exclude"', allow_blank=True)
SW.add_data_validation(dv)
dv.add(f"{C['Analyst Decision']}2:{C['Analyst Decision']}{last}")
widths = {'Site ID': 11, 'Origin': 16, 'Site / Project Heading': 42, 'Address': 34, 'Settlement': 18,
          'Project IDs': 18, 'Possible Overlap': 60, 'Analyst Note': 30, 'Tier Reason': 24, 'Reporting Tier': 20,
          'CIS Tier': 18, 'CIS Stage': 18, 'Dwelling Type': 18, 'Unit Mix Source': 22, 'Analyst Decision': 18,
          'CIS Expiry Screen (source workbook)': 34}
for k, col in C.items():
    SW.column_dimensions[col].width = widths.get(k, 12)
for k in ('CIS Decision Date', 'Last CIS Update', 'Register Expiry (latest)', 'Expiry Used'):
    for r in range(2, last + 1):
        SW[f"{C[k]}{r}"].number_format = DATE
for k in ('Permitted / Stated Units', 'Units Completed (stated)', 'Units Remaining', 'Apartments (known)', 'Houses (known)',
          'Student Bedspaces', 'General Dwellings Counted', 'Student Units Counted', 'Student Bedspaces Counted'):
    for r in range(2, last + 1):
        SW[f"{C[k]}{r}"].number_format = NUM
SW.freeze_panes = 'D2'
SW.auto_filter.ref = f"A1:{L(len(scols))}{last}"
SW.row_dimensions[1].height = 42
red = PatternFill('solid', fgColor='F8CBAD')
SW.conditional_formatting.add(f"{C['Review Required']}2:{C['Review Required']}{last}",
                              FormulaRule(formula=[f'{C["Review Required"]}2="Yes"'], fill=red))

# ---- Applications ----
AW = wb.create_sheet('Applications')
acols = ['Project Id', 'Site ID', 'CIS Reference', 'Project Heading', 'Address', 'CIS Stage', 'Planning Stage',
         'Contract Stage', 'Application Date', 'CIS Decision Date', 'Start Date', 'Finish Date', 'Units',
         'Apartments', 'Houses', 'Student Bedspaces', 'Unit Mix Source', 'Last Updated', 'Source Dataset',
         'Included in Pipeline', 'Exclusion Reason',
         # register block (V onward)
         'Register Source', 'Register Ref', 'Register Status', 'Register Decision', 'Appeal Decision',
         'Register Outcome', 'Register Decision Date', 'Grant Date', 'Register Expiry',
         'Extension of Duration', 'Expiry incl. EoD', 'Register Units', 'Location Diff (m)',
         'Later Application Nearby', 'Register Description', 'Register Link',
         'Decision Date Diff (days)', 'Units Check', 'Check Result']
CA = {n: L(i) for i, n in enumerate(acols, 1)}
assert CA['Register Outcome'] == 'AA'
header(AW, 1, acols)
for k in acols[acols.index('Register Source'):]:
    AW[f"{CA[k]}1"].fill = PatternFill('solid', fgColor='375623')
for i, a in enumerate(A.itertuples(index=False), start=2):
    d = a._asdict() if hasattr(a, '_asdict') else None
    row = A.iloc[i - 2]
    vals = [row['Project Id'], row.site or None, row.Reference if pd.notna(row.Reference) else None, row['Project Heading'],
            addr(row), row['Pipeline Stage'], row['Planning Stage'], row['Contract Stage'], row['Application Date'],
            row['Decision Date'], row['Start Date'], row['Finish Date'], row.Units, row['Total Apartments'],
            row['Total Houses'], row['Student Bedspaces'], row['Unit Mix Source'], row['Last Updated'],
            row['Source Dataset'], row['Residential Pipeline Included'], row['Exclusion Reason'],
            row.found, row.reg_ref, row.status, row.decision, row.appeal, row.outcome, row.reg_dec, row.grant,
            row.reg_exp, row.eod, row.exp_final, row.reg_units, row.locdiff, row.later, row.reg_desc, row.link]
    for j, v in enumerate(vals, 1):
        v = nz(v)
        if isinstance(v, pd.Timestamp):
            v = v.to_pydatetime()
        AW.cell(row=i, column=j, value=v if v != '' else None)
    c = lambda k: f"{CA[k]}{i}"
    AW[c('Decision Date Diff (days)')] = f'=IF(OR({c("CIS Decision Date")}="",{c("Register Decision Date")}=""),"",ROUND({c("Register Decision Date")}-{c("CIS Decision Date")},0))'
    AW[c('Units Check')] = f'=IF(OR(N({c("Register Units")})=0,{c("Units")}=""),"Not recorded",IF({c("Register Units")}={c("Units")},"Match","Differs"))'
    o, st = c('Register Outcome'), c('CIS Stage')
    built = f'OR({st}="Complete",{st}="On Site",{st}="Part Complete")'
    dead = f'OR({o}="Refused",{o}="Refused on appeal",{o}="Withdrawn",{o}="Invalid")'
    grantedo = f'OR({o}="Granted",{o}="Granted on appeal")'
    AW[c('Check Result')] = (
        f'=IF({c("Included in Pipeline")}="No","Excluded (non-residential)",IF({o}="No reference","Unverified – no reference",'
        f'IF({o}="Not in council register","Unverified – not in register (Part 8 / other)",'
        f'IF({dead},IF({built},"Conflict – register not live but CIS says built","Conflict – not live in register"),'
        f'IF(AND({st}="Plans Submitted",{grantedo}),"Stage out of date – now granted",'
        f'IF(AND({st}<>"Plans Submitted",OR({o}="Pending",{o}="Under appeal")),"Check – register still pending",'
        f'IF(N({c("Location Diff (m)")})>{LOCM},"Check – location differs",'
        f'IF(AND({c("Decision Date Diff (days)")}<>"",ABS(N({c("Decision Date Diff (days)")}))>60),"Consistent – decision date differs","Consistent"))))))))')
    if row.link:
        AW[c('Register Link')].hyperlink = row.link
        AW[c('Register Link')].font = Font(name=F, size=10, color='0563C1', underline='single')
for k in ('Application Date', 'CIS Decision Date', 'Start Date', 'Finish Date', 'Last Updated', 'Register Decision Date',
          'Grant Date', 'Register Expiry', 'Expiry incl. EoD'):
    for r in range(2, APPLAST + 1):
        AW[f"{CA[k]}{r}"].number_format = DATE
aw = {'Project Heading': 40, 'Address': 34, 'Register Description': 50, 'Later Application Nearby': 36,
      'Check Result': 36, 'Extension of Duration': 30, 'Register Link': 30, 'Exclusion Reason': 24, 'Source Dataset': 20,
      'Unit Mix Source': 22, 'Register Status': 20, 'Register Outcome': 18, 'Register Source': 18}
for k, col in CA.items():
    AW.column_dimensions[col].width = aw.get(k, 12)
AW.freeze_panes = 'E2'
AW.auto_filter.ref = f"A1:{L(len(acols))}{APPLAST}"
AW.row_dimensions[1].height = 42
AW.conditional_formatting.add(f"{CA['Check Result']}2:{CA['Check Result']}{APPLAST}",
                              FormulaRule(formula=[f'LEFT({CA["Check Result"]}2,8)="Conflict"'], fill=red))
AW.conditional_formatting.add(f"{CA['Check Result']}2:{CA['Check Result']}{APPLAST}",
                              FormulaRule(formula=[f'OR(LEFT({CA["Check Result"]}2,5)="Check",LEFT({CA["Check Result"]}2,5)="Stage")'],
                                          fill=PatternFill('solid', fgColor='FFE699')))

# ---- Review Queue (static list, live status) ----
def issues(s, arows):
    out = []
    outs = arows.outcome.tolist()
    if s.stage not in ('On Site', 'Part Complete', 'Complete') and outs and all(o in ('Refused', 'Refused on appeal', 'Withdrawn', 'Invalid') for o in outs):
        out.append('Register: ' + ', '.join(sorted(set(outs))).lower())
    rexp = s.regexp if s.regexp is not None and pd.notna(s.regexp) else (s.dec + pd.DateOffset(years=5) if s.dec is not None and pd.notna(s.dec) else None)
    if s.stage in ('Permission Granted', 'Commencement Expected', 'Stalled or Suspended') and rexp is not None and rexp < pd.Timestamp('2026-09-29'):
        out.append(f'Past expiry ({rexp:%d/%m/%Y})')
    if s.upd is not None and pd.notna(s.upd) and (pd.Timestamp('2026-09-29') - s.upd).days / 30.44 > 24:
        out.append(f'No CIS update since {s.upd:%m/%Y}')
    if s.overlap:
        out.append('Possible overlap')
    if s.lowconf == 'Yes':
        out.append('Low-confidence grouping / unit count')
    later = [l for l in arows.later if l]
    if later:
        out.append('Later application nearby: ' + later[0])
    return out

rq = []
for s in S.itertuples():
    ar = A[A.site == s.sid]
    iss = issues(s, ar)
    if iss:
        u = s.units if pd.notna(s.units) else 0
        dn = s.done if pd.notna(s.done) else 0
        rem = 0 if s.stage == 'Complete' else max(u - dn, 0)
        rq.append((s.sid, s.heading, s.settlement, s.stage, rem, '; '.join(iss), s.overlap))
rq.sort(key=lambda t: -t[4])
RQ = wb.create_sheet('Review Queue')
rcols = ['#', 'Site ID', 'Site / Project Heading', 'Settlement', 'CIS Stage', 'Units Remaining (live)', 'Issues (at build)',
         'Overlap Detail', 'Review Status (live)', 'Analyst Decision (live)', 'Reporting Tier (live)']
header(RQ, 1, rcols)
for i, t in enumerate(rq, start=2):
    RQ.cell(row=i, column=1, value=i - 1)
    for j, v in enumerate(t, start=2):
        RQ.cell(row=i, column=j, value=v if v != '' else None)
    RQ.cell(row=i, column=6, value=f'=IFERROR(INDEX(Sites!${C["Units Remaining"]}$2:${C["Units Remaining"]}${last},MATCH($B{i},Sites!$A$2:$A${last},0)),"")').number_format = NUM
    look = lambda k: f'=IFERROR(INDEX(Sites!${C[k]}$2:${C[k]}${last},MATCH($B{i},Sites!$A$2:$A${last},0))&"","")'
    RQ.cell(row=i, column=9, value=look('Review Required'))
    RQ.cell(row=i, column=10, value=look('Analyst Decision'))
    RQ.cell(row=i, column=11, value=look('Reporting Tier'))
for col, w in zip('ABCDEFGHIJK', [5, 11, 42, 20, 18, 10, 60, 60, 12, 18, 20]):
    RQ.column_dimensions[col].width = w
RQ.freeze_panes = 'C2'
RQ.auto_filter.ref = f"A1:K{len(rq) + 1}"
RQ.row_dimensions[1].height = 30
for r in range(2, len(rq) + 2):
    for col in 'GH':
        RQ[f'{col}{r}'].alignment = Alignment(wrap_text=True, vertical='top')

# ---- Summary ----
SU = wb.create_sheet('Summary', 1)
SU['A1'] = 'Limerick Residential Pipeline – Summary'
SU['A1'].font = Font(name=F, bold=True, size=14)
SU['A2'] = '="Report date "&TEXT(Method!$B$4,"dd/mm/yyyy")&". All figures from the Sites tab (one row per site). Delivered and Excluded sites are kept out of pipeline totals."'
rng = lambda k: f"Sites!${C[k]}$2:${C[k]}${last}"
R = 4
def sec(title):
    global R
    SU.cell(row=R, column=1, value=title).font = Font(name=F, bold=True, size=12)
    R += 1

sec('Headline pipeline')
pipe_cond = f'{rng("Reporting Tier")},"<>Delivered",{rng("Reporting Tier")},"<>Excluded"'
head = [
    ('Pipeline sites', f'=COUNTIFS({pipe_cond})'),
    ('General dwellings (units remaining)', f'=SUM({rng("General Dwellings Counted")})'),
    ('Student units', f'=SUM({rng("Student Units Counted")})'),
    ('Student bedspaces', f'=SUM({rng("Student Bedspaces Counted")})'),
    ('Of which firm (Committed + Committed Pre-Construction + Advanced Pre-Construction)',
     '=' + '+'.join(f'SUMIFS({rng("General Dwellings Counted")},{rng("Reporting Tier")},"{t}")' for t in ['Committed', 'Committed Pre-Construction', 'Advanced Pre-Construction'])),
    ('Delivered sites (Complete)', f'=COUNTIFS({rng("Reporting Tier")},"Delivered")'),
    ('Delivered units (permitted, excl. student)', f'=SUMIFS({rng("Permitted / Stated Units")},{rng("Reporting Tier")},"Delivered",{rng("Dwelling Type")},"<>Student accommodation")'),
    ('Excluded sites', f'=COUNTIFS({rng("Reporting Tier")},"Excluded")'),
    ('Excluded units', f'=SUMIFS({rng("Units Remaining")},{rng("Reporting Tier")},"Excluded")'),
]
for k, f in head:
    SU.cell(row=R, column=1, value=k)
    c = SU.cell(row=R, column=2, value=f)
    c.number_format = NUM
    R += 1
R += 1
sec('Reconciliation to the previous workbook')
SU.cell(row=R, column=1, value='Previous headline units (Pipeline Summary tab, all stages, application-level)')
c = SU.cell(row=R, column=2, value=11402); c.font = Font(name=F, color='0000FF'); c.number_format = NUM
SU.cell(row=R, column=3, value='Source: Pipeline Summary tab of Limerick_Residential_Pipeline_Full_Build.xlsx (sum of Units column).')
prevrow = R; R += 1
SU.cell(row=R, column=1, value='New: pipeline general dwellings + student units + delivered units')
SU.cell(row=R, column=2, value=f'=B6+B7+B11').number_format = NUM
R += 1
SU.cell(row=R, column=1, value='Difference')
SU.cell(row=R, column=2, value=f'=B{R-1}-B{prevrow}').number_format = NUM
SU.cell(row=R, column=3, value='Mainly from counting each site once (the old total summed every application on a site) and dropping applications the register shows as withdrawn or refused.')
R += 2

sec('By reporting tier')
tiers = ['Committed', 'Committed Pre-Construction', 'Advanced Pre-Construction', 'Likely', 'Potential',
         'Application Pipeline', 'Constrained / uncertain', 'Delivered', 'Excluded']
th = ['Reporting Tier', 'Sites', 'General Dwellings', 'Student Units', 'Student Bedspaces', 'Known Mix Units', 'Mix Coverage']
for j, h in enumerate(th, 1):
    SU.cell(row=R, column=j, value=h)
header(SU, R, th); R += 1
t0 = R
for t in tiers:
    SU.cell(row=R, column=1, value=t)
    SU.cell(row=R, column=2, value=f'=COUNTIFS({rng("Reporting Tier")},A{R})')
    if t == 'Delivered':
        SU.cell(row=R, column=3, value=f'=SUMIFS({rng("Permitted / Stated Units")},{rng("Reporting Tier")},A{R},{rng("Dwelling Type")},"<>Student accommodation")')
    elif t == 'Excluded':
        SU.cell(row=R, column=3, value=f'=SUMIFS({rng("Units Remaining")},{rng("Reporting Tier")},A{R},{rng("Dwelling Type")},"<>Student accommodation")')
    else:
        SU.cell(row=R, column=3, value=f'=SUMIFS({rng("General Dwellings Counted")},{rng("Reporting Tier")},A{R})')
    SU.cell(row=R, column=4, value=f'=SUMIFS({rng("Student Units Counted")},{rng("Reporting Tier")},A{R})')
    SU.cell(row=R, column=5, value=f'=SUMIFS({rng("Student Bedspaces Counted")},{rng("Reporting Tier")},A{R})')
    SU.cell(row=R, column=6, value=f'=SUMIFS({rng("Apartments (known)")},{rng("Reporting Tier")},A{R},{rng("Dwelling Type")},"<>Student accommodation")+SUMIFS({rng("Houses (known)")},{rng("Reporting Tier")},A{R},{rng("Dwelling Type")},"<>Student accommodation")')
    SU.cell(row=R, column=7, value=f'=IF(SUMIFS({rng("Permitted / Stated Units")},{rng("Reporting Tier")},A{R},{rng("Dwelling Type")},"<>Student accommodation")=0,"",MIN(1,F{R}/SUMIFS({rng("Permitted / Stated Units")},{rng("Reporting Tier")},A{R},{rng("Dwelling Type")},"<>Student accommodation")))')
    R += 1
SU.cell(row=R, column=1, value='Pipeline total (excl. Delivered, Excluded)').font = Font(name=F, bold=True)
for col in 'BCDEF':
    SU[f'{col}{R}'] = f'=SUM({col}{t0}:{col}{t0 + 6})'
    SU[f'{col}{R}'].font = Font(name=F, bold=True)
SU[f'G{R}'] = f'=IF(C{R}=0,"",MIN(1,F{R}/SUMPRODUCT(({rng("Reporting Tier")}<>"Delivered")*({rng("Reporting Tier")}<>"Excluded")*({rng("Dwelling Type")}<>"Student accommodation")*N(+{rng("Permitted / Stated Units")}))))'
for r in range(t0, R + 1):
    for col in 'BCDEF':
        SU[f'{col}{r}'].number_format = NUM
    SU[f'G{r}'].number_format = '0%'
SU.cell(row=R + 1, column=1, value='Mix Coverage = apartments + houses with a known split, as a share of permitted units. Low coverage means the mix split is not representative.').font = Font(name=F, italic=True, size=9)
R += 3

sec('Pipeline by settlement (general dwellings)')
setts = sorted(S.settlement.unique(), key=lambda s: (s == 'Other County Limerick', s))
sh = ['Settlement', 'Sites', 'Firm', 'Likely + Potential', 'Application Pipeline', 'Constrained / uncertain', 'Total']
header(SU, R, sh); R += 1
s0 = R
for st in setts:
    SU.cell(row=R, column=1, value=st)
    SU.cell(row=R, column=2, value=f'=COUNTIFS({rng("Settlement")},A{R},{pipe_cond})')
    g = lambda tl: '+'.join(f'SUMIFS({rng("General Dwellings Counted")},{rng("Settlement")},$A{R},{rng("Reporting Tier")},"{t}")' for t in tl)
    SU.cell(row=R, column=3, value='=' + g(['Committed', 'Committed Pre-Construction', 'Advanced Pre-Construction']))
    SU.cell(row=R, column=4, value='=' + g(['Likely', 'Potential']))
    SU.cell(row=R, column=5, value='=' + g(['Application Pipeline']))
    SU.cell(row=R, column=6, value='=' + g(['Constrained / uncertain']))
    SU.cell(row=R, column=7, value=f'=SUM(C{R}:F{R})')
    R += 1
SU.cell(row=R, column=1, value='Total').font = Font(name=F, bold=True)
for col in 'BCDEFG':
    SU[f'{col}{R}'] = f'=SUM({col}{s0}:{col}{R - 1})'
    SU[f'{col}{R}'].font = Font(name=F, bold=True)
for r in range(s0, R + 1):
    for col in 'BCDEFG':
        SU[f'{col}{r}'].number_format = NUM
SU.cell(row=R + 1, column=1, value='Settlement for upstream records is assigned from address text; check before using at settlement level.').font = Font(name=F, italic=True, size=9)
R += 3

sec('Register validation (applications)')
cr = f"Applications!${CA['Check Result']}$2:${CA['Check Result']}${APPLAST}"
vh = ['Check Result', 'Applications']
header(SU, R, vh); R += 1
v0 = R
for res in ['Consistent', 'Consistent – decision date differs', 'Stage out of date – now granted',
            'Check – register still pending', 'Check – location differs', 'Conflict – not live in register',
            'Conflict – register not live but CIS says built', 'Unverified – not in register (Part 8 / other)',
            'Unverified – no reference', 'Excluded (non-residential)']:
    SU.cell(row=R, column=1, value=res)
    SU.cell(row=R, column=2, value=f'=COUNTIF({cr},A{R})')
    R += 1
SU.cell(row=R, column=1, value='Total').font = Font(name=F, bold=True)
SU[f'B{R}'] = f'=SUM(B{v0}:B{R - 1})'; SU[f'B{R}'].font = Font(name=F, bold=True)
R += 2
sec('Review status (sites)')
for k, f in [('Sites needing review', f'=COUNTIF({rng("Review Required")},"Yes")'),
             ('Sites resolved by analyst', f'=COUNTIF({rng("Review Required")},"Resolved")'),
             ('Units remaining on sites needing review', f'=SUMIFS({rng("Units Remaining")},{rng("Review Required")},"Yes")')]:
    SU.cell(row=R, column=1, value=k)
    SU.cell(row=R, column=2, value=f).number_format = NUM
    R += 1
SU.column_dimensions['A'].width = 62
for col in 'BCDEFG':
    SU.column_dimensions[col].width = 16
SU.column_dimensions['C'].width = 18

# ---- Register Not in CIS ----
abpnums = {r[6:] for r in CISREFS if r.startswith('ABPREF')}
cand = reg[reg.ApplicationType.isin(['PERMISSION', 'OUTLINE PERMISSION', 'PERMISSION CONSEQUENT'])
           & (reg.NumResidentialUnits.fillna(0) >= 10) & (~reg.ref.isin(CISREFS))
           & (~reg.ref.str[2:].isin(abpnums))].copy()
cand['out'] = cand.apply(outcome, axis=1)
cand = cand[cand.out.isin(['Pending', 'Under appeal']) |
            (cand.out.isin(['Granted', 'Granted on appeal']) & (cand.ExpiryDate >= pd.Timestamp('2026-09-29')))]
siteref = A[A.site != ''][['site', 'Latitude', 'Longitude']].dropna()
rows = []
for _, r in cand.sort_values('NumResidentialUnits', ascending=False).iterrows():
    dd = dist(siteref.Latitude, siteref.Longitude, r.lat, r.lon)
    j = dd.idxmin()
    rows.append([r.ref, r.ReceivedDate, r.out, int(r.NumResidentialUnits), nz(r.ExpiryDate), r.DevelopmentAddress,
                 str(r.DevelopmentDescription)[:300], siteref.loc[j, 'site'], int(dd[j]), r.LinkAppDetails])
NW = wb.create_sheet('Register Not in CIS')
ncols = ['Register Ref', 'Received', 'Outcome', 'Residential Units', 'Expiry', 'Address', 'Description',
         'Nearest CIS Site', 'Distance (m)', 'Register Link', 'Analyst Note']
header(NW, 1, ncols, fill=PatternFill('solid', fgColor='375623'))
for i, rw in enumerate(rows, start=2):
    for j, v in enumerate(rw, 1):
        v = nz(v)
        if isinstance(v, pd.Timestamp):
            v = v.to_pydatetime()
        NW.cell(row=i, column=j, value=v)
    NW.cell(row=i, column=2).number_format = DATE
    NW.cell(row=i, column=5).number_format = DATE
    if rw[9]:
        NW.cell(row=i, column=10).hyperlink = rw[9]
        NW.cell(row=i, column=10).font = Font(name=F, size=10, color='0563C1', underline='single')
    NW.cell(row=i, column=11).fill = INFILL
for col, w in zip('ABCDEFGHIJK', [12, 11, 16, 10, 11, 40, 60, 12, 10, 30, 30]):
    NW.column_dimensions[col].width = w
NW.freeze_panes = 'B2'
NW.auto_filter.ref = f"A1:K{len(rows) + 1}"
NW.row_dimensions[1].height = 30
print('register not in CIS', len(rows), sum(r[3] for r in rows))

# fonts everywhere
for ws in wb:
    for row in ws.iter_rows():
        for c in row:
            f = c.font
            if f.name != F:
                c.font = Font(name=F, size=f.size if f.size and f.size != 11 else 10, bold=f.b, italic=f.i,
                              color=f.color, underline=f.u)
wb.move_sheet('Review Queue', offset=0)
wb._sheets = [wb['Method'], wb['Summary'], wb['Sites'], wb['Review Queue'], wb['Applications'], wb['Register Not in CIS']]
wb.save('Limerick_Residential_Pipeline_Simplified.xlsx')
print('sites', len(S), 'apps', len(A), 'queue', len(rq))
print(A.outcome.value_counts())
