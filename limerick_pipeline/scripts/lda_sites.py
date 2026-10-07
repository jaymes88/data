import sys, json, shapefile, pandas as pd, numpy as np
from pyproj import Transformer
from shapely.geometry import shape, Point, mapping
from shapely.ops import transform, unary_union
src = sys.argv[1]
r = shapefile.Reader(src)
tr = Transformer.from_crs(2157, 4326, always_xy=True)
rows = []
for sr in r.shapeRecords():
    d = sr.record.as_dict()
    g_itm = shape(sr.shape.__geo_interface__).buffer(0)
    rows.append(dict(site=d['Framework_'], programme=d['Programme'], owner=d['Owner'], schedule=d['Schedule'], cls=d['Class'],
                     yield_=d['Yield'], area_ha=g_itm.area / 1e4, g_itm=g_itm, g=transform(tr.transform, g_itm)))
P = pd.DataFrame(rows)
S = P.groupby('site').agg(parcels=('g', 'size'), area_ha=('area_ha', 'sum'), owner=('owner', 'first'), cls=('cls', 'first'),
                          yield_=('yield_', 'first'), programme=('programme', lambda x: ', '.join(sorted(set(x))))).reset_index()
S['g'] = [unary_union(list(P[P.site == s].g)) for s in S.site]
S['g_itm'] = [unary_union(list(P[P.site == s].g_itm)) for s in S.site]
nb = [(f['properties']['nbhd'], shape(f['geometry'])) for f in json.load(open('nbh.geojson'))['features']]
S['nbhd'] = [', '.join(n for n, g in nb if g.intersects(x)) or 'Outside' for x in S.g]
D = pd.read_pickle('delivery.pkl')
toitm = Transformer.from_crs(4326, 2157, always_xy=True)
D['pt'] = [Point(*toitm.transform(lo, la)) if pd.notna(la) else None for la, lo in zip(D.lat, D.lon)]
out = []
for _, s in S.iterrows():
    hits = D[[p is not None and s.g_itm.buffer(50).contains(p) for p in D.pt]]
    out.append('; '.join(f"{h.ref or h.pid} {h.heading[:45]} ({int(h.units) if pd.notna(h.units) else '?'} units, {h.status}, {h.owner})" for _, h in hits.iterrows()))
S['tracker_schemes'] = out
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 140)
print(S[['site', 'parcels', 'area_ha', 'owner', 'cls', 'yield_', 'programme', 'nbhd']].to_string())
for _, s in S.iterrows(): print('-', s.site, '=>', s.tracker_schemes or 'none')
S.drop(columns=['g', 'g_itm']).to_pickle('lda_sites.pkl')
json.dump(dict(type='FeatureCollection', features=[dict(type='Feature', properties=dict(site=s.site, yield_=s.yield_, owner=s.owner), geometry=mapping(s.g)) for _, s in S.iterrows()]), open('lda_sites.geojson', 'w'))
