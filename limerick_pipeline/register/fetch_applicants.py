"""Applicant name for each permission from Limerick's ePlanning file details page. Writes in_review/eplan_applicants.csv."""
import re, html, sqlite3, time, os
import pandas as pd, requests
from concurrent.futures import ThreadPoolExecutor
p = pd.read_sql('select distinct perm_id, planning_ref, register_ref from parcel_permissions', sqlite3.connect('Limerick_Housing_Land_Register.gpkg'))
refs = sorted({str(x) for x in pd.concat([p.planning_ref, p.register_ref]).dropna() if not str(x).startswith('ABPREF')})
def get(ref):
    f = f'ep_app/{ref}.html'
    if not os.path.exists(f):
        for k in range(3):
            try:
                r = requests.get(f'https://eplanning.ie/LimerickCCC/AppFileRefDetails/{ref}/0', headers={'User-Agent': 'Mozilla/5.0'}, timeout=60)
                open(f, 'w').write(r.text); break
            except Exception:
                time.sleep(3)
    t = open(f).read() if os.path.exists(f) else ''
    m = re.search(r'Applicant name:\s*</[^>]+>\s*(?:<[^>]+>\s*)*([^<]+)<', t)
    return ref, html.unescape(m.group(1)).strip() if m else ''
with ThreadPoolExecutor(4) as ex:
    res = list(ex.map(get, refs))
A = pd.DataFrame(res, columns=['ref', 'applicant'])
A.to_csv('in_review/eplan_applicants.csv', index=False)
print(len(A), 'refs;', A.applicant.ne('').sum(), 'with applicant')
