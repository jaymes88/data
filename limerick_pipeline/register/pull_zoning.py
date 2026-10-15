"""Pull Limerick zoning (GZT current plans) and the residential zoned land tax maps to in_zoning/."""
import time, requests, pandas as pd, geopandas as gpd
B = 'https://services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/{}/FeatureServer/0/query'
def pull(svc, where, out):
    parts, off = [], 0
    while True:
        for t in range(4):
            try:
                fc = requests.get(B.format(svc), params={'where': where, 'outFields': '*', 'outSR': 2157, 'f': 'geojson',
                                                         'resultOffset': off, 'resultRecordCount': 2000, 'orderByFields': 'OBJECTID'}, timeout=180).json()
                break
            except Exception:
                time.sleep(2 ** (t + 1))
        f = fc.get('features', [])
        if not f:
            break
        parts.append(gpd.GeoDataFrame.from_features(f, crs=2157)); off += len(f)
    g = pd.concat(parts, ignore_index=True)
    g.to_file(f'in_zoning/{out}.gpkg', driver='GPKG')
    print(out, len(g))
pull('GZT_Current_Plan', "LA_NAME LIKE '%Limerick%'", 'gzt')
pull('Residential_Zoned_Land_Tax_Annual_Draft_Map2027_view', "LOCAL_AUTHORITY_NAME LIKE '%Limerick%'", 'rzlt2027')
