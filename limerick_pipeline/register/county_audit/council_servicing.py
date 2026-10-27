"""Servicing and infrastructure attributes from the council capacity audit Excel (May 2026), city and county.

City sheet ('City&Subs Material Alterations') is keyed by 'SCA Site No.', which is the rsca number of the city audit
polygons (checked: 106 of 109 numeric matches agree on area within 10%). County sheets are keyed by settlement + site.
Writes in_county/council_servicing.csv with one row per council site.
"""
import re
import pandas as pd

XL = 'in_sca2/xl/sca.xlsx'
FIELDS = {  # register field: possible Excel column names
    'svc_lighting': ['Lighting'], 'svc_footpaths': ['Footpaths'], 'svc_road_access': ['Road Access'], 'svc_water': ['Water'],
    'svc_foul': ['Foul'], 'svc_surface_water': ['Surface Water'], 'svc_tier': ['Updated Tier'],
    'ue_water': ['Uisce Eireann Water Capacity', 'Uisce Eireann 10 Year Supply Capacity Register - Water', 'Uisce Eireann Capacity Register 2025 - Water'],
    'ue_wastewater': ['Uisce Eireann Wastewater Capacity', 'Uisce Eireann Capacity Register 2025 - Wastewater'],
    'flood_risk': ['Flood Risk'], 'energy': ['Energy Infrastructure'], 'near_public_transport': ['Proximity to Public Transport'],
    'near_primary_school': ['Proximity to Primary Schools'], 'near_secondary_school': ['Proximity to Secondary Schools'],
    'school_requirements': ['School Requirements'], 'council_site_status': ['Site Status (July 26)', 'Site Status (Jun. 26)'],
}
def tidy(v):
    if pd.isna(v): return ''
    s = str(v).strip()
    return re.sub(r'\.0$', '', s)

out = []
c = pd.read_excel(XL, sheet_name='City&Subs Material Alterations', header=1)
c.columns = [str(x).strip() for x in c.columns]
c = c[c['SCA Site No.'].notna() & c['Variation RSCA Site No.'].notna()]
for _, r in c.iterrows():
    row = dict(scope='City', settlement='Limerick City and Suburbs', site=tidy(r['SCA Site No.']), excel_area=r.get('2022 Area'))
    for f, cols in FIELDS.items():
        row[f] = next((tidy(r[x]) for x in cols if x in c.columns and tidy(r[x])), '')
    out.append(row)
for sh in ['Key Town', 'Towns', 'Large Villages']:
    d = pd.read_excel(XL, sheet_name=sh, header=1)
    d.columns = [str(x).strip() for x in d.columns]
    d = d[d.Settlement.notna() & d['SCA Site No.'].notna()]
    for _, r in d.iterrows():
        row = dict(scope='County', settlement=str(r.Settlement).strip(), site=tidy(r['SCA Site No.']), excel_area=r.get('Site Area (ha.)'))
        for f, cols in FIELDS.items():
            row[f] = next((tidy(r[x]) for x in cols if x in d.columns and tidy(r[x])), '')
        out.append(row)
S = pd.DataFrame(out)
yn = ['svc_lighting', 'svc_footpaths', 'svc_road_access', 'svc_water', 'svc_foul', 'svc_surface_water']
lab = {'svc_lighting': 'lighting', 'svc_footpaths': 'footpaths', 'svc_road_access': 'road access', 'svc_water': 'water',
       'svc_foul': 'foul', 'svc_surface_water': 'surface water'}
def summary(r):
    v = {k: r[k].upper()[:1] for k in yn if r[k]}
    if not v: return 'Not assessed'
    s = [lab[k] for k, x in v.items() if x == 'S']; n = [lab[k] for k, x in v.items() if x == 'N']
    if not s and not n and len(v) == len(yn): return 'Serviced'
    return ('Serviceable: ' + ', '.join(s) if s else '') + ('; not serviced: ' + ', '.join(n) if n else '') or 'Partly assessed'
S['servicing'] = S.apply(summary, axis=1)
S.to_csv('in_county/council_servicing.csv', index=False)
print(S.groupby('scope').servicing.apply(lambda s: s.str.split(':').str[0].value_counts().to_dict()))
