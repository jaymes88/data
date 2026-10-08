"""Extra source records shared by build2.py, delivery_data.py and make_gpkg.py.

- KPMG audit: CIS records for live Limerick schemes that were not in our CIS exports (checked against the register).
- PBSA file: bedspace counts for student schemes already in the tracker.
"""
import os, re
import numpy as np, pandas as pd

KPMG_SHP = 'kpmg_in/kpmg.shp'
PBSA_SHP = 'in_7661c9a2-Archive/pbsa.shp'
# live in the register, missing from both CIS exports (see kpmg_cmp.py)
KPMG_ADD = ['2360842', '2560540', '2560151', '2560169', '221107', '221003', '2360150', '22471', '2460864', '2460633', '21364']
STAGE = {'Plans Granted': ('Permission Granted', 'Potential', 'Plans Granted', None),
         'Plans Granted - On Site': ('On Site', 'Committed', 'Plans Granted', 'On Site'),
         'Plans Granted - Contract Awarded': ('Contract Awarded', 'Committed Pre-Construction', 'Plans Granted', 'Contract Awarded'),
         'Plans Granted - Tender': ('Tender', 'Advanced Pre-Construction', 'Plans Granted', 'Tender')}
MIX = {'oneBedApar': '1 Bed Apartments', 'twoBedApar': '2 Bed Apartments', 'threeBedAp': '3 Bed Apartments', 'fourBedApa': '4 Bed Apartments',
       'fiveAndGre': '5+ Bed Apartments', 'totalApart': 'Total Apartments', 'oneBedHous': '1 Bed Houses', 'twoBedHous': '2 Bed Houses',
       'threeBedHo': '3 Bed Houses', 'fourBedHou': '4 Bed Houses', 'fiveAndG_1': '5+ Bed Houses', 'TotalHouse': 'Total Houses',
       'StudentBed': 'Student Bedspaces'}
SOURCE = 'KPMG audit (CIS record missing from our exports)'


def _read_shp(path):
    import shapefile
    from pyproj import Transformer
    from shapely.geometry import shape
    tr = Transformer.from_crs(2157, 4326, always_xy=True)
    out = []
    for sr in shapefile.Reader(path).shapeRecords():
        g = shape(sr.shape.__geo_interface__)
        lon, lat = tr.transform(*g.representative_point().coords[0])
        out.append({**sr.record.as_dict(), '_lat': lat, '_lon': lon, '_geom_itm': g})
    return pd.DataFrame(out)


def kpmg_records(columns):
    """Rows shaped like lp.xlsx 'Full Project Pipeline' for the KPMG schemes we add."""
    if not os.path.exists(KPMG_SHP):
        return pd.DataFrame(columns=columns)
    K = _read_shp(KPMG_SHP)
    K = K[K['Reference'].astype(str).str.strip().isin(KPMG_ADD)]
    rows = []
    d = lambda s: pd.to_datetime(s, dayfirst=True, errors='coerce') if s else pd.NaT
    for _, k in K.iterrows():
        stage, tier, pstage, cstage = STAGE[k['Detailed s']]
        row = {c: np.nan for c in columns}
        row.update({'Project Id': int(k['Project Id']), 'Reference': str(k['Reference']).strip(), 'Project Heading': k['Project He'],
                    'Description': k['Descriptio'], 'Project Site Address Line 1': k['Project Si'], 'Project Site County': 'Co. Limerick',
                    'Latitude': k['_lat'], 'Longitude': k['_lon'], 'Contract Stage': cstage, 'Planning Stage': pstage,
                    'Application Date': d(k['Applicatio']), 'Decision Date': d(k['Decision D']), 'Start Date': d(k['Start Date']),
                    'Units': k['Units'], 'Last Updated': d(k['Last Updat']), 'Planning Authority': 'Limerick Council',
                    'Pipeline Stage': stage, 'Delivery Tier': tier, 'Residential Pipeline Included': 'Yes',
                    'Already in Granted/Delivery Dataset': 'No', 'Unit Mix Source': 'KPMG audit', 'Unit Mix Reconciles': 'Unknown',
                    'Source Dataset': SOURCE})
        for a, b in MIX.items():
            if b in row:
                row[b] = k[a]
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def load_full(path='lp.xlsx', **kw):
    full = pd.read_excel(path, sheet_name='Full Project Pipeline', **kw)
    extra = kpmg_records(full.columns)
    full = pd.concat([full, extra], ignore_index=True)
    full['Reference'] = full['Reference'].map(lambda v: None if pd.isna(v) else str(v).replace('.0', '') if isinstance(v, float) else str(v))
    return fix_coords(full)


def pbsa():
    """PBSA file as a DataFrame: scheme, beds, rooms, existing, status, refs, lat, lon."""
    if not os.path.exists(PBSA_SHP):
        return pd.DataFrame()
    P = _read_shp(PBSA_SHP)
    P['refs'] = P['status'].fillna('').map(lambda s: [x.replace('/', '') for x in re.findall(r'\d{2}/?\d{3,5}', s)])
    return P.rename(columns={'_lat': 'lat', '_lon': 'lon'})


# bedspaces from the PBSA file for student schemes in the tracker (planning ref -> beds)
def pbsa_beds():
    P = pbsa()
    if P.empty:
        return {}
    return {r: int(b) for refs, b, ex in zip(P.refs, P.beds, P.existing) if ex == 'no' for r in refs[:1]}


def fix_coords(full):
    """Best location per record: planning register point (council's own; SHDs via their council copy yy+case no.),
    then the KPMG audit site boundary, then the CIS coordinate. Adds a 'Location Source' column."""
    full = full.copy()
    reg = pd.read_pickle('reg.pkl')
    reg['ref'] = reg.ApplicationNumber.astype(str).str.strip()
    reg = reg.dropna(subset=['lat', 'lon']).drop_duplicates('ref')
    pts = dict(zip(reg.ref, zip(reg.lat, reg.lon)))
    shd = {r[-6:]: pts[r] for r in pts if len(r) == 8 and r[-6:].startswith('3')}
    kp = {}
    if os.path.exists(KPMG_SHP):
        K = _read_shp(KPMG_SHP)
        kp = dict(zip(K['Project Id'].astype('int64'), zip(K['_lat'], K['_lon'])))
    src = []
    for i, r in full.iterrows():
        ref = str(r.get('Reference') or '').strip()
        p = pts.get(ref) or (shd.get(ref[6:]) if ref.startswith('ABPREF') else None)
        s_ = 'Planning register'
        if p is None and pd.notna(r['Project Id']) and int(r['Project Id']) in kp:
            p, s_ = kp[int(r['Project Id'])], 'KPMG audit site boundary'
        if p is None:
            s_ = 'CIS' if pd.notna(r['Latitude']) else 'None'
        else:
            full.at[i, 'Latitude'], full.at[i, 'Longitude'] = p
        src.append(s_)
    full['Location Source'] = src
    return full
