import re, difflib
import numpy as np, pandas as pd

MOD = re.compile(r'modif|amend|revis|alteration|change of house type|changes? to (?:the )?(?:permitted|house)|replace|substitut|in lieu|redesign|reconfigur', re.I)
EOD = re.compile(r'extension of (?:permission|duration|the (?:appropriate )?period)|extend the (?:appropriate )?(?:period|duration)', re.I)
OUTL = re.compile(r'outline permission', re.I)
REF = re.compile(r'(?<![\d/])(\d{2})\s*/\s*(\d{1,6})(?![\d/])')
ABP = re.compile(r'ABP[-\s]?(\d{6})', re.I)
DEAD = {'Refused', 'Refused on appeal', 'Withdrawn', 'Invalid'}
BUILT = {'Complete', 'On Site', 'Part Complete'}

def refs_in(desc):
    if not isinstance(desc, str):
        return []
    out = [a + b for a, b in REF.findall(desc)]
    out += ['ABPREF' + n for n in ABP.findall(desc)]
    return out

def sim(a, b):
    a = re.sub(r'\s+', ' ', str(a).lower())[:350]
    b = re.sub(r'\s+', ' ', str(b).lower())[:350]
    return difflib.SequenceMatcher(None, a, b).ratio()

HDR = re.compile(r'(\d{1,4})\s*(?:no\.?|x|nr\.?)?\s*(?:residential|dwelling|housing|new|social)?\s*(?:units|dwellings|dwelling units|houses|homes|apartments)\b', re.I)

def desc_units(desc):
    if not isinstance(desc, str):
        return None
    m = HDR.search(desc)
    return int(m.group(1)) if m else None

def best_units(r):
    return r.dunits if pd.notna(r.get('dunits')) and r.dunits else r.units

def dist(lat1, lon1, lat2, lon2):
    return float(np.sqrt(((lat1 - lat2) * 111000) ** 2 + ((lon1 - lon2) * 67000) ** 2))

def classify(A):
    """A: DataFrame with columns ref, site, date, units, outcome, stage, desc, lat, lon, regtype, included.
    Returns dict idx -> (relationship, related_ref, basis, confidence)."""
    res = {}
    A = A.sort_values('date', na_position='first')
    byref = {r.ref: i for i, r in A.iterrows() if r.ref}
    superseded = {}
    for i, a in A.iterrows():
        if a.included != 'Yes':
            res[i] = ('Excluded', '', 'Non-residential record', 'High'); continue
        # comparison set: same site or within 100m, earlier
        prior = []
        for j, e in A.iterrows():
            if j == i or e.included != 'Yes':
                continue
            if pd.notna(e.date) and pd.notna(a.date) and e.date > a.date:
                continue
            if pd.isna(e.date) and pd.notna(a.date):
                pass
            same = e.site == a.site and a.site != ''
            near = pd.notna(a.lat) and pd.notna(e.lat) and dist(a.lat, a.lon, e.lat, e.lon) < 100
            if (same or near) and not (pd.isna(e.date) and pd.isna(a.date) and j > i):
                prior.append(j)
        desc = a.desc if isinstance(a.desc, str) else ''
        rrefs = [r for r in refs_in(desc) if r in byref and r != a.ref
                 and not (pd.notna(A.loc[byref[r]].date) and pd.notna(a.date) and A.loc[byref[r]].date > a.date)]
        if a.regtype == 'EXTENSION OF DURATION' or EOD.search(desc[:200]):
            if rrefs:
                res[i] = ('Extension of duration', rrefs[0], f'Extends {rrefs[0]}; units counted on parent', 'High')
            else:
                q = refs_in(desc)
                cands = [(sim(desc, A.loc[j].desc), j) for j in prior if A.loc[j].site == a.site]
                cands = [c for c in cands if c[0] >= 0.8]
                if not q and cands:
                    j = max(cands)[1]
                    res[i] = ('Extension of duration', A.loc[j].ref, f'Register EoD; description matches {A.loc[j].ref} ({max(cands)[0]:.0%})', 'Medium')
                else:
                    res[i] = ('Extension of duration (parent not in CIS)', q[0] if q else '', 'Parent permission not in CIS; CIS units counted here', 'Low')
            continue
        if a.outcome in DEAD:
            res[i] = ('Not live', '', f'Register: {a.outcome.lower()}', 'High'); continue
        if rrefs:
            r = rrefs[0]; e = A.loc[byref[r]]
            if OUTL.search(desc) and e.regtype == 'OUTLINE PERMISSION' or re.search(r'outline permission[^.]{0,80}' + r[:2] + r'\s*/\s*' + r[2:], desc, re.I):
                res[i] = ('Replaces earlier', r, f'Permission consequent on outline {r}', 'High'); superseded[byref[r]] = a.ref; continue
            if MOD.search(desc):
                au, eu = best_units(a), best_units(e)
                if e.stage == 'Complete':
                    res[i] = ('Additional phase', r, f'Modifies completed {r}; its own units counted', 'Medium')
                elif pd.isna(e.units) or e.units == 0:
                    res[i] = ('Additional phase', r, f'Modifies {r}, which has no unit count in CIS; units counted here', 'Low')
                elif pd.notna(au) and au >= 0.5 * eu:
                    res[i] = ('Replaces earlier', r, f'Modifies {r} and restates the scheme', 'Medium'); superseded[byref[r]] = a.ref
                else:
                    res[i] = ('Amendment within parent', r, f'Partial modification of {r}; units already counted there', 'Medium')
                continue
            res[i] = ('Additional phase', r, f'References {r} without modification wording (e.g. phase / connection)', 'Medium'); continue
        # repeat detection against earlier live applications nearby
        best = None
        for j in prior:
            e = A.loc[j]
            if e.outcome in DEAD or j in superseded:
                continue
            s = sim(desc, e.desc)
            au, eu = best_units(a), best_units(e)
            ok = pd.notna(au) and pd.notna(eu) and max(au, eu) > 0
            ueq = ok and max(au, eu) >= 5 and abs(au - eu) <= 0.1 * max(au, eu)
            ucompat = ok and abs(au - eu) <= 0.25 * max(au, eu)
            if (s >= 0.85 and ucompat) or (ueq and s >= 0.5):
                if best is None or s > best[1]:
                    best = (j, s, ueq)
        if best:
            j, s, ueq = best; e = A.loc[j]
            if e.stage == 'Complete' and s < 0.95:
                res[i] = ('Additional application on site', e.ref, f'Similar to completed {e.ref} ({s:.0%} text match); treated as separate', 'Low'); continue
            conf = 'High' if s >= 0.85 and ueq else 'Medium'
            res[i] = ('Replaces earlier', e.ref, f'Repeat of {e.ref} ({s:.0%} text match, units {int(eu)}→{int(au)})', conf)
            superseded[j] = a.ref; continue
        others = [j for j in prior if A.loc[j].outcome not in DEAD]
        if others:
            res[i] = ('Additional application on site', '', 'Other live applications on site/nearby; no link found in descriptions', 'Low')
        else:
            res[i] = ('Primary', '', 'Only live application on site', 'High')
    # apply supersession
    for j, newref in superseded.items():
        rel = res.get(j, ('', '', '', ''))
        if rel[0] in ('Extension of duration', 'Not live', 'Excluded'):
            continue
        res[j] = ('Superseded', newref, f'Replaced by {newref}', res[j][3] if j in res else 'Medium')
    return res
