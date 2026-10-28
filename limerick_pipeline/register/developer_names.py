"""Developer / applicant name for each permission in the land register.

Order of sources: the applicant named on the council's ePlanning file (fetch_applicants.py; Part 8 files are the
council's own); the applicant on the An Bord Pleanála case page for SHDs; the CIS project team (role Promoter or Client);
the grantee named in the CIS project description ("granted to X for ..."); then the public delivery body where it is the
council or the LDA. Names are as recorded in the source. Writes in_review/developer_names.csv.
"""
import re, sqlite3
import pandas as pd

FB = '/root/.claude/uploads/5b5cc1fb-d010-598c-b6b3-355e877f30b9/db39aa29-Limerick_Residential_Pipeline_Full_Build.xlsx'
teams = pd.concat([pd.read_excel(f, sheet_name='Project Teams', dtype={'Project Id': str}) for f in ['lp.xlsx', FB]]).drop_duplicates()
prom = (teams[teams.Role.isin(['Promoter', 'Client'])].dropna(subset=['Company Name'])
        .groupby('Project Id')['Company Name'].apply(lambda x: '; '.join(dict.fromkeys(x.astype(str).str.strip()))))
desc = pd.concat([pd.read_excel(f, sheet_name=s, dtype={'Project Id': str})[['Project Id', 'Description']]
                  for f in ['lp.xlsx', FB] for s in ['Full Project Pipeline', 'Latest Export Deduplicated']]).dropna().drop_duplicates('Project Id').set_index('Project Id').Description
GRANTEE = re.compile(r"(?:grant(?:ed)?|approv\w*|uph\w+)[^.]{0,120}?\bto ([A-Z][A-Za-z0-9&'’.\- ]{2,80}?)(?: for | to | the |,|\.| \()", re.S)
BAD = re.compile(r'^(?:the |a |an |planning|permission|limerick$|construct|develop|demolish|provide|erect|retain|amend|extend|be |proceed)', re.I)

EP = pd.read_csv('in_review/eplan_applicants.csv', dtype=str).fillna('').set_index('ref').applicant
ABP = {}
for n in ['307631', '309999', '311588', '312683', '313124', '315273']:
    m = re.search(r'<p>\s*([^<]+?)\s*\(Applicant\)', open(f'p_{n}.html').read())
    if m:
        ABP['ABPREF' + n] = re.sub(r'\s+', ' ', m.group(1)).strip()
p = pd.read_sql('select perm_id, planning_ref, register_ref, delivery_body, route from parcel_permissions', sqlite3.connect('Limerick_Housing_Land_Register.gpkg')).drop_duplicates('perm_id')
out = []
for _, r in p.iterrows():
    pid = str(r.perm_id)
    name, src = '', ''
    refs = [str(x) for x in (r.planning_ref, r.register_ref) if pd.notna(x)]
    ep = next((EP[x] for x in refs if EP.get(x, '')), '')
    ab = next((ABP[x] for x in refs if x in ABP), '')
    if ep:
        name, src = (('Limerick City and County Council', 'Planning register (Part 8, council scheme)') if ep.lower().startswith('part 8')
                     else (ep, 'Planning register (applicant)'))
    elif ab:
        name, src = ab, 'An Bord Pleanála case (applicant)'
    elif pid in prom.index:
        name, src = prom[pid], 'CIS project team (promoter)'
    else:
        g = [x.strip() for x in GRANTEE.findall(str(desc.get(pid, ''))) if not BAD.match(x.strip())]
        if g:
            name, src = g[0], 'CIS project description (grantee)'
    if not name and r.delivery_body == 'Local authority':
        name, src = 'Limerick City and County Council', 'Delivery body (local authority scheme)'
    if not name and r.delivery_body == 'Land Development Agency':
        name, src = 'Land Development Agency', 'Delivery body'
    name = re.sub(r'^Limerick Council$', 'Limerick City and County Council', name)
    out.append(dict(perm_id=pid, developer=name, developer_source=src))
D = pd.DataFrame(out)
D.to_csv('in_review/developer_names.csv', index=False)
print(D.developer_source.replace('', 'None found').value_counts().to_string())
