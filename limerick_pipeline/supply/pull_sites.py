"""Pull Limerick planning application site polygons (national Planning Application Sites layer) to in_pp_full/sites.gpkg."""
import json, time, requests, geopandas as gpd, pandas as pd
B = 'https://services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/IrishPlanningApplications/FeatureServer/1/query'
parts, off = [], 0
while True:
    for t in range(4):
        try:
            r = requests.get(B, params={'where': "PlanningAuthority LIKE '%Limerick%'", 'outFields': '*', 'outSR': 2157, 'f': 'geojson',
                                        'resultOffset': off, 'resultRecordCount': 2000, 'orderByFields': 'OBJECTID'}, timeout=120)
            fc = r.json(); break
        except Exception as e:
            time.sleep(2 ** (t + 1))
    feats = fc.get('features', [])
    if not feats:
        break
    parts.append(gpd.GeoDataFrame.from_features(feats, crs=2157))
    off += len(feats)
    print(off)
g = pd.concat(parts, ignore_index=True)
for c in [c for c in g.columns if c.endswith('Date') or c == 'ETL_DATE']:
    g[c] = pd.to_datetime(g[c], unit='ms', errors='coerce')
g.to_file('in_pp_full/sites.gpkg', layer='sites', driver='GPKG')
print(len(g), g.ApplicationNumber.nunique(), (g.area / 1e4).max())
