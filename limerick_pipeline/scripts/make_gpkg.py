"""Write the Limerick residential pipeline to a GeoPackage (EPSG:2157, Irish Transverse Mercator)."""
import json, os, numpy as np, pandas as pd, geopandas as gpd
from shapely.geometry import shape
OUT = 'Limerick_Residential_Pipeline.gpkg'
if os.path.exists(OUT):
    os.remove(OUT)
ITM = 2157

def clean(df):
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda v: None if (v is None or (isinstance(v, float) and np.isnan(v))) else (str(v) if not isinstance(v, (str, int, float, bool)) else v))
        elif str(df[c].dtype).startswith('datetime'):
            df[c] = pd.to_datetime(df[c]).dt.date.astype('string')
    return df

def points(df, lat='lat', lon='lon'):
    df = df[df[lat].notna() & df[lon].notna()]
    g = gpd.GeoDataFrame(clean(df.drop(columns=[lat, lon])), geometry=gpd.points_from_xy(df[lon], df[lat]), crs=4326)
    return g.to_crs(ITM)

# 1. delivery study schemes (one row per counted scheme)
D = pd.read_pickle('delivery.pkl').drop(columns=['cis_partial', 'pt'], errors='ignore')
D['sector'] = np.where(D.owner.str.startswith('Public'), 'Public', 'Private')
keep = ['pid', 'ref', 'register_ref', 'source', 'site', 'heading', 'settlement', 'lea', 'nbhd', 'units', 'band', 'dwelling_type',
        'route', 'owner', 'sector', 'stage', 'status', 'relationship', 'rel_conf', 'received', 'final_grant', 'fi', 'appealed',
        'expiry', 'start', 'start_source', 'completion', 'completion_source', 'approval_yrs', 'grant_to_start_yrs',
        'start_to_complete_yrs', 'build_rate_dpa', 'bc_notices', 'ccc_count', 'ccc_units', 'sh_no', 'sh_programme', 'sh_stage',
        'sh_quarter', 'sh_mode', 'barriers_noted', 'lat', 'lon']
_apps = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Applications')
D['student_bedspaces'] = D.pid.map(dict(zip(_apps['Project Id'].astype(str), _apps['Student Bedspaces']))) if False else D.pid.astype(str).map(dict(zip(_apps['Project Id'].astype(str), _apps['Student Bedspaces'])))
keep.insert(keep.index('dwelling_type') + 1, 'student_bedspaces')
g1 = points(D[[c for c in keep if c in D.columns]])
g1.to_file(OUT, layer='schemes', driver='GPKG')

# 2. all applications from the pipeline workbook, located from CIS / register
A = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Applications')
from sources import load_full, _read_shp, KPMG_SHP
full = load_full('lp.xlsx')[['Project Id', 'Latitude', 'Longitude']]
A = A.merge(full, on='Project Id', how='left').rename(columns={'Latitude': 'lat', 'Longitude': 'lon'})
acols = ['Project Id', 'Site ID', 'CIS Reference', 'Project Heading', 'Address', 'Settlement', 'CIS Stage', 'Application Date',
         'CIS Decision Date', 'Units', 'Dwelling Type', 'Final Relationship', 'Related Ref', 'Confidence', 'Counts?', 'Reporting Tier',
         'Remaining Units', 'Mix Source', 'Studio', '1 Bed', '2 Bed', '3 Bed', '4 Bed', '5+ Bed', 'Register Outcome', 'Expiry incl. EoD',
         'Check Result', 'Register Link', 'Social Housing Project No.', 'Public Delivery', 'lat', 'lon']
A = A[[c for c in acols if c in A.columns]]
A.columns = [c.lower().replace(' ', '_').replace('?', '').replace('.', '').replace('+', 'plus') for c in A.columns]
points(A).to_file(OUT, layer='applications', driver='GPKG')

# 3. sites roll-up
S = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Sites').rename(columns={'Latitude': 'lat', 'Longitude': 'lon'})
S.columns = [c if c in ('lat', 'lon') else c.lower().replace(' ', '_').replace('/', '').replace('(', '').replace(')', '').replace('-', '_') for c in S.columns]
points(S).to_file(OUT, layer='sites', driver='GPKG')

# 4. live register schemes (10+ units) not in CIS
reg = pd.read_pickle('reg.pkl'); reg['ref'] = reg.ApplicationNumber.astype(str)
N = pd.read_excel('Limerick_Residential_Pipeline_Simplified.xlsx', sheet_name='Register Not in CIS', dtype={'Register Ref': str})
N = N.merge(reg.drop_duplicates('ref')[['ref', 'lat', 'lon']], left_on='Register Ref', right_on='ref', how='left').drop(columns='ref')
N.columns = [c if c in ('lat', 'lon') else c.lower().replace(' ', '_').replace('(', '').replace(')', '') for c in N.columns]
points(N).to_file(OUT, layer='register_not_in_cis', driver='GPKG')

# 5-7. boundaries and public land
def polys(path, layer, props_map=None):
    fc = json.load(open(path))
    g = gpd.GeoDataFrame([f['properties'] for f in fc['features']], geometry=[shape(f['geometry']) for f in fc['features']], crs=4326).to_crs(ITM)
    g.to_file(OUT, layer=layer, driver='GPKG')
    return g
polys('nbh.geojson', 'city_neighbourhoods')
polys('nbh_eds.geojson', 'city_neighbourhood_eds')
lea = polys('lea.geojson', 'local_electoral_areas')
L = pd.read_pickle('lda_sites.pkl')
ld = polys('lda_sites.geojson', 'lda_public_land')

# Clare schemes in the KPMG audit (Limerick metropolitan area, outside Limerick's planning authority – not in study totals)
K = _read_shp(KPMG_SHP)
K = K[K['Planning A'].astype(str).str.contains('Clare')]
kc = gpd.GeoDataFrame(pd.DataFrame({'project_id': K['Project Id'].astype('int64'), 'reference': K['Reference'], 'scheme': K['Project He'],
                                    'address': K['Project Si'], 'stage': K['Detailed s'], 'units': K['Units'], 'planning_authority': K['Planning A'],
                                    'note': 'Clare County Council area – outside the Limerick study totals'}),
                      geometry=list(K['_geom_itm']), crs=2157)
kc.to_file(OUT, layer='clare_metro_schemes', driver='GPKG')

import pyogrio
for l in pyogrio.list_layers(OUT):
    info = pyogrio.read_info(OUT, layer=l[0])
    print(l[0], l[1], info['features'], info['crs'])
