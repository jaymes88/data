"""Assemble the scheme-level dataset for the Limerick delivery study.

Scheme = a counted application in Limerick_Residential_Pipeline_Simplified.xlsx (Counts? = Yes).
Joins: planning register (reg.pkl), building control commencement/completion (bcms_lim.pkl),
CIS narrative (lp.xlsx), LEA boundaries (lea.geojson).
"""
import re, json
import numpy as np, pandas as pd
from shapely.geometry import shape, Point

REPORT_DATE = pd.Timestamp('2026-09-29')
WB = 'Limerick_Residential_Pipeline_Simplified.xlsx'

app = pd.read_excel(WB, sheet_name='Applications', dtype={'CIS Reference': str, 'Register Ref': str, 'Related Ref': str})
full = pd.read_excel('lp.xlsx', sheet_name='Full Project Pipeline')
reg = pd.read_pickle('reg.pkl')
reg['ref'] = reg.ApplicationNumber.astype(str).str.strip()
REG = reg.drop_duplicates('ref').set_index('ref')
bc = pd.read_pickle('bcms_lim.pkl')
for c in ['CN_Commencement_Date', 'CCC_Date_Validated', 'CN_Date_Granted']:
    bc[c] = pd.to_datetime(bc[c], errors='coerce')
abp = json.load(open('abp.json'))

# ---------- BCMS reference index ----------
def bc_refs(s):
    s = str(s)
    out = set()
    for yy, n in re.findall(r'(?<!\d)(\d{2})\s*[/\-. ]\s*(\d{1,5})(?!\d)', s):
        out.add(yy + n)
    for t in re.findall(r'(?<![\d/\-.])(\d{4,7})(?![\d/\-.])', s):
        out.add(t)
    for n in re.findall(r'ABP[-\s]?(\d{6})', s, re.I):
        out.add('ABPREF' + n)
    for n in re.findall(r'PL\s*\d{2}\s*\.?\s*(\d{6})', s, re.I):
        out.add('ABPREF' + n)
    return out

bc['refs'] = bc.CN_Planning_Permission_Number.map(bc_refs)
BIDX = {}
for i, rs in bc.refs.items():
    for r in rs:
        BIDX.setdefault(r, set()).add(i)

# ---------- CIS narrative: dated entries ----------
DATE = r'(\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+\s+\d{4}|\d{2}/\d{2}/\d{4})'

def entries(desc):
    out = []
    for p in re.split(r'(?:^|\s)(?=' + DATE + r'\s*[:\-])', str(desc)):
        m = re.match(DATE + r'\s*[:\-]\s*(.*)', p.strip(), re.S)
        if m:
            d = pd.to_datetime(re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', m.group(1)), dayfirst=True, errors='coerce')
            out.append((d, m.group(2).strip()))
    return out

COMPLETE = re.compile(r'(works (?:are|have been|are now|have now been) (?:now )?complete|now complete|development is (?:now )?complete|project is (?:now )?complete|is complete\b|works are completed|completed on site)', re.I)
PARTIAL = re.compile(r'complete(?:d)? on (?:the )?(\d+) (?:units|houses|dwellings)|(\d+) units? (?:are|have been) (?:now )?complete', re.I)
BARRIER = {
    'On hold / no movement': r'on hold|no movement|not progress|no construction or tender schedules|yet to be advanced',
    'Legal challenge / quashed': r'quash|judicial review|legal challenge',
    'Permission expiring': r'expire',
    'Stalled': r'\bstall|suspend',
    'Site for sale / sold': r'for sale|been sold|on the market|new owner',
    'Awaiting funding / approval': r'funding|awaiting (?:approval|department)|stage \d approval',
}

narr = {}
for _, r in full.iterrows():
    ents = entries(r.Description)
    comp = [d for d, t in ents if COMPLETE.search(t) and not re.search(r'expected|anticipated|not expected|until', t, re.I) and pd.notna(d)]
    part = []
    for d, t in ents:
        m = PARTIAL.search(t)
        if m and pd.notna(d):
            part.append((d, int(m.group(1) or m.group(2))))
    barriers = [k for k, p in BARRIER.items() if re.search(p, str(r.Description), re.I)]
    last = max([d for d, t in ents if pd.notna(d)], default=pd.NaT)
    narr[r['Project Id']] = dict(cis_complete_date=min(comp) if comp else pd.NaT, cis_partial=part,
                                 barriers='; '.join(barriers), last_entry=last)

# ---------- LEA ----------
lea = json.load(open('lea.geojson'))
LEAS = [(re.sub(r'\s*LEA-\d+$', '', f['properties']['ENGLISH']).title(), shape(f['geometry'])) for f in lea['features']]

def lea_of(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return 'Unknown'
    p = Point(lon, lat)
    for n, g in LEAS:
        if g.contains(p):
            return n
    best = min(LEAS, key=lambda t: t[1].distance(p))
    return best[0] if best[1].distance(p) < 0.02 else 'Outside county'

# ---------- neighbourhoods (Limerick city, 42 EDs grouped by the Council) ----------
NBH = [(f['properties']['nbhd'], f['properties']['code'], shape(f['geometry'])) for f in json.load(open('nbh.geojson'))['features']]
def nbhd_of(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return 'Unknown'
    pt = Point(lon, lat)
    for n, c, g in NBH:
        if g.contains(pt):
            return n
    return 'Outside city neighbourhoods'

# ---------- Part 8 records in the register (Limerick files Part 8s as yy/8nnn) ----------
from rel import desc_units
P8 = reg[reg.ref.str.fullmatch(r'\d{2}8\d{3}')].drop_duplicates('ref').copy()
P8['dunits'] = [desc_units(d) for d in P8.DevelopmentDescription]
P8['units'] = [du if pd.notna(du) and du else (nu if pd.notna(nu) and nu else np.nan) for du, nu in zip(P8.dunits, P8.NumResidentialUnits)]
P8 = P8[P8.DevelopmentDescription.str.contains(r'dwelling|house|residential|apartment|homes|housing unit', case=False, na=False)
        & ~P8.DevelopmentDescription.str.contains(r'greenway|library|station house|market house|innovation hub|appliance bay|roundabout|junction', case=False, na=False)]
IS_P8 = lambda x: bool(re.fullmatch(r'\d{2}8\d{3}', x or ''))

# ---------- owner (public / private) ----------
teams = pd.read_excel('lp.xlsx', sheet_name='Project Teams')
promoters = teams[teams.Role.isin(['Promoter', 'Client'])].groupby('Project Id')['Company Name'].apply(lambda x: '; '.join(x.astype(str))).to_dict()
GRANTEE = re.compile(r"(?:grant(?:ed)?|approv\w*|uph\w+)[^.]{0,120}?\bto ([A-Z][A-Za-z0-9&'’.\- ]{2,80}?)(?: for | to | the |,|\.| \()", re.S)
AHB = r'housing association|cl[uú]id|respond|tuath|oaklee|co-?operative housing|voluntary housing|approved housing|focus housing|circle vha|iveagh|peter mc ?verry|simon communit|sophia|novas|threshold|clann housing|nabco|fold housing|ballyhoura rural|broadford voluntary'
LA = r'limerick city (?:and|&) county council|limerick county council|limerick city council|^limerick council$'
def owner(text, grantee, team, route, bc_la, bc_ahb):
    blob = ' '.join([text, grantee, team])
    if re.search(r'land development agency|\bLDA\b', blob, re.I):
        return 'Public – LDA'
    if route == 'Part 8 / council' or re.search(LA, grantee.strip(), re.I) or re.search(LA, team, re.I) or bc_la \
            or re.search(r'limerick city (?:and|&) county council (?:has|have) (?:issued|lodged|sought)|part (?:8|viii) (?:application|scheme)', text, re.I):
        return 'Public – local authority'
    if re.search(AHB, grantee + ' ' + team, re.I) or bc_ahb or re.search(r'on behalf of [^.]{0,40}(?:' + AHB + ')', text, re.I):
        return 'Public – approved housing body'
    return 'Private'

def bc_for(keys):
    idx = set()
    for k in keys:
        if k:
            idx |= BIDX.get(k, set())
    b = bc.loc[sorted(idx)] if idx else bc.iloc[0:0]
    la = b.CN_Behalf_local_authority.astype(str).str.lower().eq('yes').any() if 'CN_Behalf_local_authority' in b else False
    ahb = b.CN_Approved_housing_body.astype(str).str.lower().eq('yes').any() if 'CN_Approved_housing_body' in b else False
    return b, la, ahb

def dwelling_type(desc, heading, ho=np.nan, apx=np.nan, student=False):
    if student or re.search(r'student', heading, re.I):
        return 'Student'
    if pd.notna(ho) and ho > 0 and pd.notna(apx) and apx > 0:
        return 'Mixed'
    if pd.notna(apx) and apx > 0:
        return 'Apartments'
    if pd.notna(ho) and ho > 0:
        return 'Houses'
    if re.search(r'apartment|duplex|flat', desc + ' ' + heading, re.I):
        return 'Apartments'
    if re.search(r'house|dwelling', desc + ' ' + heading, re.I):
        return 'Houses'
    return 'Unknown'

# ---------- scheme table ----------
fullidx = full.set_index('Project Id')
S = app[app['Counts?'] == 'Yes'].copy()
eod_children = app[app['Final Relationship'] == 'Extension of duration'].groupby('Related Ref')['CIS Reference'].apply(list).to_dict()
cis_refs = set(app['CIS Reference'].dropna().astype(str).str.strip())
p8_used = set(r_ for r_ in cis_refs if IS_P8(r_))

rows = []
for _, a in S.iterrows():
    pid = a['Project Id']
    f = fullidx.loc[pid]
    ref = (a['CIS Reference'] or '').strip() if isinstance(a['CIS Reference'], str) else ''
    r = REG.loc[ref] if ref in REG.index else None
    p8_match = ''
    # CIS Part 8 records carry CIS ids, not register refs: match to register Part 8 by location and date
    if r is None and not ref.startswith('ABPREF') and pd.notna(f.Latitude):
        d = np.sqrt(((P8.lat - f.Latitude) * 111000) ** 2 + ((P8.lon - f.Longitude) * 67000) ** 2)
        appd = pd.to_datetime(f['Application Date'])
        cu = a['Units'] if pd.notna(a['Units']) else np.nan
        ok = (d < 250) & ~P8.ref.isin(p8_used) & ((P8.units - cu).abs() <= 0.5 * np.maximum(P8.units, cu))
        if pd.notna(appd):
            ok &= (P8.ReceivedDate - appd).abs().dt.days < 3 * 365
        if ok.any():
            j = d[ok].idxmin()
            r = REG.loc[P8.loc[j, 'ref']]
            p8_match = P8.loc[j, 'ref']
            p8_used.add(p8_match)
    reg_ref = p8_match or ref
    received = r.ReceivedDate if r is not None else pd.to_datetime(f['Application Date'])
    council_dec = r.DecisionDate if r is not None else pd.NaT
    appeal = r is not None and str(r.AppealDecision or '').strip() not in ('', 'None')
    fi = r is not None and pd.notna(r.FIRequestDate)
    if r is not None and appeal and pd.notna(r.AppealDecisionDate):
        final = r.AppealDecisionDate
    elif r is not None and pd.notna(r.GrantDate):
        final = r.GrantDate
    elif r is not None and pd.notna(r.DecisionDate):
        final = r.DecisionDate
    elif ref.startswith('ABPREF') and ref[6:] in abp:
        final = pd.to_datetime(abp[ref[6:]]['signed'], dayfirst=True)
    else:
        final = pd.to_datetime(f['Decision Date'])
    desc = str(r.DevelopmentDescription) if r is not None else str(a['Register Description'] or '')
    if ref.startswith('ABPREF'):
        route = 'SHD (An Bord Pleanála)'
    elif IS_P8(reg_ref) or re.search(r'part\s*8|PT8', ref + ' ' + str(a['Project Heading']), re.I) or a['Register Source'] == 'Not in council register':
        route = 'Part 8 / council'
    elif re.search(r'large[- ]scale residential|\bLRD\b', desc, re.I):
        route = 'LRD'
    else:
        route = 'Standard planning application'
    keys = {ref, reg_ref} | set(eod_children.get(ref, []))
    if r is not None and r.AppealRefNumber:
        keys |= {'ABPREF' + n for n in re.findall(r'(\d{6})', str(r.AppealRefNumber))}
    b, bc_la, bc_ahb = bc_for(keys)
    g = GRANTEE.findall(str(f.Description))
    own = owner(str(f.Description) + ' ' + str(a['Project Heading']), g[0].strip() if g else '', promoters.get(pid, ''), route, bc_la, bc_ahb)
    cn = b.dropna(subset=['CN_Commencement_Date']).drop_duplicates('CN_Number')
    ccc = b.dropna(subset=['CCC_Date_Validated']).drop_duplicates('CCC_Number')
    bc_start = cn.CN_Commencement_Date.min() if len(cn) else pd.NaT
    bc_start = bc_start if pd.isna(bc_start) or bc_start <= REPORT_DATE else pd.NaT  # future-dated notices not yet started
    stage = a['CIS Stage']
    started_cis = stage in ('On Site', 'Part Complete', 'Complete')
    cis_start = pd.to_datetime(f['Start Date']) if started_cis else pd.NaT
    start = bc_start if pd.notna(bc_start) else cis_start
    start_src = 'Commencement notice' if pd.notna(bc_start) else ('CIS start date' if pd.notna(cis_start) else '')
    nm = narr.get(pid, {})
    comp_date = nm.get('cis_complete_date', pd.NaT) if stage == 'Complete' else pd.NaT
    if stage == 'Complete' and pd.isna(comp_date):
        comp_date = pd.to_datetime(f['Finish Date'])
    units = a['Units'] if pd.notna(a['Units']) else np.nan
    dt = dwelling_type(desc, str(a['Project Heading']), a['Houses'], a['Apartments'], a['Dwelling Type'] == 'Student accommodation')
    expiry = pd.NaT if route == 'Part 8 / council' else a['Expiry Used']  # Part 8 approvals carry no register expiry
    rows.append(dict(
        pid=pid, site=a['Site ID'], ref=ref, register_ref=reg_ref, source='CIS', heading=a['Project Heading'], settlement=a['Settlement'],
        lat=f.Latitude, lon=f.Longitude, lea=lea_of(f.Latitude, f.Longitude), nbhd=nbhd_of(f.Latitude, f.Longitude), units=units,
        units_completed_stated=a['Units Completed (stated)'], stage=stage, tier=a['Reporting Tier'],
        relationship=a['Final Relationship'], rel_conf=a['Confidence'], dwelling_type=dt, route=route, owner=own,
        received=received, council_decision=council_dec, final_grant=final, fi=fi, appealed=appeal,
        register_outcome=a['Register Outcome'], expiry=expiry,
        bc_start=bc_start, cis_start=cis_start, start=start, start_source=start_src,
        bc_notices=len(cn), bc_units_commenced=cn.CN_Units_for_phase.sum() if len(cn) else 0,
        ccc_first=ccc.CCC_Date_Validated.min() if len(ccc) else pd.NaT,
        ccc_last=ccc.CCC_Date_Validated.max() if len(ccc) else pd.NaT,
        ccc_units=ccc.CCC_Units_Completed.sum() if len(ccc) else 0, ccc_count=len(ccc),
        completion=comp_date, cis_partial=nm.get('cis_partial', []), barriers_noted=nm.get('barriers', ''),
        last_cis_entry=nm.get('last_entry', pd.NaT), last_updated=a['Last Updated'],
    ))

# ---------- residential Part 8s in the register that CIS does not hold ----------
SETTLE = ['Mungret', 'Annacotty', 'Patrickswell', 'Newcastle West', 'Kilmallock', 'Adare', 'Bruff', 'Cappamore',
          'Rathkeale', 'Castleconnell', 'Caherconlish', 'Abbeyfeale', 'Croom', 'Askeaton', 'Foynes', 'Kilfinane', 'Hospital', 'Glin']
def settlement_of(addr, nb):
    for x in SETTLE:
        if x.lower() in str(addr).lower():
            return x
    return 'Limerick City and Suburbs' if nb not in ('Outside city neighbourhoods', 'Unknown') else 'Other County Limerick'
extra = P8[~P8.ref.isin(p8_used) & (P8.units >= 2)]
_has_cn = extra.ref.map(lambda x: len(bc_for({x})[0].dropna(subset=['CN_Commencement_Date'])) > 0)
P8_UNDECIDED = extra[extra.DecisionDate.isna() & ~_has_cn]
P8_UNDECIDED.to_pickle('p8_undecided.pkl')
extra = extra[extra.DecisionDate.notna() | _has_cn]
for _, r in extra.iterrows():
    b, bc_la, bc_ahb = bc_for({r.ref})
    cn = b.dropna(subset=['CN_Commencement_Date']).drop_duplicates('CN_Number')
    ccc = b.dropna(subset=['CCC_Date_Validated']).drop_duplicates('CCC_Number')
    bc_start = cn.CN_Commencement_Date.min() if len(cn) else pd.NaT
    bc_start = bc_start if pd.isna(bc_start) or bc_start <= REPORT_DATE else pd.NaT
    o = outcome_reg(r) if 'outcome_reg' in globals() else ''
    decided = (pd.notna(r.DecisionDate) and str(r.Decision).upper() in ('CONDITIONAL', 'UNCONDITIONAL')) or len(cn) > 0
    nb = nbhd_of(r.lat, r.lon)
    desc = str(r.DevelopmentDescription)
    rows.append(dict(
        pid='REG-' + r.ref, site='', ref=r.ref, register_ref=r.ref, source='Register only (Part 8, not in CIS)',
        heading='Part 8: ' + re.sub(r'\s+', ' ', desc)[:70], settlement=settlement_of(r.DevelopmentAddress, nb),
        lat=r.lat, lon=r.lon, lea=lea_of(r.lat, r.lon), nbhd=nb, units=r.units, units_completed_stated=np.nan,
        stage='Commenced (building control)' if pd.notna(bc_start) else ('Permission Granted' if decided else 'Plans Submitted'),
        tier='', relationship='Primary', rel_conf='', dwelling_type=dwelling_type(desc, ''), route='Part 8 / council',
        owner='Public – local authority', received=r.ReceivedDate, council_decision=r.DecisionDate,
        final_grant=r.GrantDate if pd.notna(r.GrantDate) else r.DecisionDate, fi=pd.notna(r.FIRequestDate), appealed=False,
        register_outcome='Granted' if decided else 'Pending', expiry=pd.NaT, bc_start=bc_start, cis_start=pd.NaT,
        start=bc_start, start_source='Commencement notice' if pd.notna(bc_start) else '', bc_notices=len(cn),
        bc_units_commenced=cn.CN_Units_for_phase.sum() if len(cn) else 0,
        ccc_first=ccc.CCC_Date_Validated.min() if len(ccc) else pd.NaT, ccc_last=ccc.CCC_Date_Validated.max() if len(ccc) else pd.NaT,
        ccc_units=ccc.CCC_Units_Completed.sum() if len(ccc) else 0, ccc_count=len(ccc), completion=pd.NaT, cis_partial=[],
        barriers_noted='', last_cis_entry=pd.NaT, last_updated=pd.NaT,
    ))
D = pd.DataFrame(rows)

# ---------- Department social housing construction report (vetted matches only) ----------
import os
if os.path.exists('shcp_feed.pkl'):
    SH = pd.read_pickle('shcp_feed.pkl').set_index('pid')
    for c in ['sh_no', 'sh_programme', 'sh_ahb', 'sh_stage', 'sh_quarter', 'sh_mode', 'completion_source']:
        D[c] = ''
    D['completion_source'] = np.where(D.completion.notna(), 'CIS', '')
    for i, r in D[D.pid.isin(SH.index)].iterrows():
        h = SH.loc[r.pid]
        D.at[i, 'sh_no'] = str(h.no); D.at[i, 'sh_programme'] = h.programme; D.at[i, 'sh_ahb'] = '' if pd.isna(h.ahb) else h.ahb
        D.at[i, 'sh_stage'] = h.stage; D.at[i, 'sh_quarter'] = h.stage_quarter; D.at[i, 'sh_mode'] = h.sh_mode
        D.at[i, 'owner'] = h.sh_owner
        if h.stage == 'Completed' and r.stage != 'Complete':
            D.at[i, 'stage'] = 'Complete'; D.at[i, 'completion'] = h.q_mid; D.at[i, 'completion_source'] = 'Department social housing report'
        elif h.stage == 'On Site' and pd.isna(r.start) and r.stage not in ('On Site', 'Part Complete', 'Complete'):
            D.at[i, 'stage'] = 'On Site'; D.at[i, 'start_source'] = 'Department social housing report (on site by ' + h.stage_quarter + ')'

# size bands
BANDS = [(1, 9, '1–9'), (10, 24, '10–24'), (25, 49, '25–49'), (50, 99, '50–99'), (100, 10 ** 6, '100+')]
def band(u):
    if pd.isna(u) or u <= 0:
        return 'Unknown'
    for lo, hi, n in BANDS:
        if lo <= u <= hi:
            return n
D['band'] = D.units.map(band)
BAND_ORDER = [b[2] for b in BANDS]

yrs = lambda a, b: (b - a).dt.days / 365.25
D['approval_yrs'] = yrs(D.received, D.final_grant)
D['grant_to_start_yrs'] = yrs(D.final_grant, D.start)
D['start_to_complete_yrs'] = yrs(D.start, D.completion)
D['received_to_start_yrs'] = yrs(D.received, D.start)
for c in ['approval_yrs', 'grant_to_start_yrs', 'start_to_complete_yrs', 'received_to_start_yrs']:
    D.loc[D[c] < 0, c] = np.nan  # data errors (e.g. start recorded before grant)
D['build_rate_dpa'] = np.where(D.start_to_complete_yrs > 0, D.units / D.start_to_complete_yrs.clip(lower=0.5), np.nan)

started = D.start.notna() | D.stage.isin(['On Site', 'Part Complete', 'Complete'])
D['status'] = np.select(
    [D.stage == 'Complete', started, D.stage == 'Stalled or Suspended',
     D.expiry.notna() & (pd.to_datetime(D.expiry) < REPORT_DATE), D.stage.isin(['Plans Submitted'])],
    ['Complete', 'Under construction', 'Stalled (CIS)', 'Not started – past expiry', 'In planning'],
    'Not started – permission live')
D['grant_year'] = D.final_grant.dt.year
D['start_year'] = D.start.dt.year
D['complete_year'] = D.completion.dt.year
D.to_pickle('delivery.pkl')

if __name__ == '__main__':
    pd.set_option('display.width', 250)
    print(len(D))
    print(D.band.value_counts().reindex(BAND_ORDER + ['Unknown']))
    print(D.status.value_counts())
    print(D.start_source.value_counts())
    print(D.route.value_counts()); print(D.owner.value_counts()); print(D.source.value_counts()); print(D.nbhd.value_counts()); print(D.dwelling_type.value_counts()); print(D.lea.value_counts())
    print(D[['approval_yrs', 'grant_to_start_yrs', 'start_to_complete_yrs', 'build_rate_dpa']].describe())
    c = D[D.stage == 'Complete']
    print('complete with ccc', (c.ccc_count > 0).sum(), len(c), 'ccc units', c.ccc_units.sum(), 'cis units', c.units.sum())
    print('fi', D.fi.sum(), 'appealed', D.appealed.sum())
    print(D.barriers_noted.replace('', np.nan).dropna().value_counts().head(10))
