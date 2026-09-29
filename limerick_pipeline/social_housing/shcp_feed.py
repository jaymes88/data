"""Vetted social housing matches -> feed for the pipeline workbook and delivery study."""
import pandas as pd, numpy as np
X = pd.read_pickle('shcp_xwalk.pkl'); D = pd.read_pickle('delivery.pkl')
m = X[X.category == 'Matched'].copy()
# drop ambiguous: several report rows on one tracker scheme
key = m.tracker_site.fillna('') + '|' + m.tracker_ref.fillna('') + '|' + m.tracker_scheme
m = m[key.map(key.value_counts()) == 1]
m = m[m.no != 1830]  # Ballycummin Road: LA scheme at capital appraisal vs 2025 private application – not the same scheme
# attach tracker scheme (pid) and drop date conflicts (report says delivered before the tracker application was lodged)
Dk = D.assign(k=D.ref.fillna('') + '|' + D.heading)
m['pid'] = (m.tracker_ref.fillna('') + '|' + m.tracker_scheme).map(dict(zip(Dk.k, Dk.pid)))
m = m[m.pid.notna()]
qend = lambda q: pd.Period(q.replace('Q', '').split('-')[1] + 'Q' + q[1], freq='Q').end_time.normalize() if isinstance(q, str) and q[1].isdigit() else pd.NaT
qmid = lambda q: (pd.Period(q.replace('Q', '').split('-')[1] + 'Q' + q[1], freq='Q').start_time + pd.Timedelta(days=45)) if isinstance(q, str) else pd.NaT
m['q_end'] = m.stage_quarter.map(qend); m['q_mid'] = m.stage_quarter.map(qmid)
Di = D.set_index('pid')
rec, grant = m.pid.map(Di.received), m.pid.map(Di.final_grant)
conflict = (m.stage.eq('On Site') & rec.notna() & (m.q_end < rec)) | (m.stage.eq('Completed') & grant.notna() & (m.q_end < grant + pd.Timedelta(days=180)))
print('dropped for date conflict:', m[conflict].name.tolist())
m = m[~conflict]
m['sh_owner'] = np.where(m.programme.str.contains('CALF|CAS'), 'Public – approved housing body', 'Public – local authority')
m['sh_mode'] = np.where(m.programme.str.contains('Turnkey'), 'Turnkey', 'Construction')
feed = m[['pid', 'no', 'name', 'units', 'programme', 'ahb', 'stage', 'stage_quarter', 'q_mid', 'sh_owner', 'sh_mode', 'tracker_ref', 'tracker_scheme', 'tracker_status']]
feed.to_pickle('shcp_feed.pkl'); feed.to_csv('shcp_feed.csv', index=False)
print(len(feed), feed.units.sum()); print(feed.groupby(['sh_owner', 'sh_mode']).size())
print(pd.crosstab(feed.stage, feed.tracker_status))
