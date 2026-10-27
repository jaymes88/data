"""One polygon file holding every parcel of the land register.

Writes Limerick_Developable_Land_Review.gpkg with a single layer, developable_land: every parcel in the register with
its land facts, capacity, consented and future supply, and its permissions written out as text, followed by blank review
columns. Built from Limerick_Housing_Land_Register.gpkg; rerunning it overwrites the file, so reviewed copies should be
saved under another name and returned for merging (matched on parcel_id).
"""
import sqlite3
import pandas as pd, geopandas as gpd

REG = 'Limerick_Housing_Land_Register.gpkg'
OUT = 'Limerick_Developable_Land.gpkg'

ps = gpd.read_file(REG, layer='parcel_summary')
pp = pd.read_sql("select * from parcel_permissions where counts_toward_totals = 'Yes'", sqlite3.connect(REG))
pp['txt'] = (pp.planning_ref.fillna(pp.register_ref).fillna('CIS ' + pp.perm_id.astype(str)) + ': ' + pp.units.fillna(0).astype(int).astype(str)
             + ' homes, ' + pp.status + pp.units_built.fillna(0).gt(0).map({True: '', False: ''})
             + pp.apply(lambda r: f' ({int(r.units_built)} built)' if pd.notna(r.units_built) and 0 < r.units_built < r.units else '', axis=1))
perm_txt = pp.sort_values('units', ascending=False).groupby('parcel_id').txt.apply(' | '.join)

order = {'Council audit': 1, 'Council audit – county': 2, 'Zoned land – no consent (estimate)': 3, 'Planning consent – not in council audit': 4}
ps['src_order'] = ps.parcel_source.map(order)
ps = ps.sort_values(['src_order', 'catchment_type', 'catchment', 'parcel_id'])
ps['permission_list'] = ps.parcel_id.map(perm_txt).fillna('')
ps['settlement_or_area'] = ps.catchment

cols = ['parcel_id', 'parcel_source', 'local_name', 'settlement_or_area', 'catchment_type', 'lea', 'zoning', 'site_type',
        'register_status', 'mapped_area_ha', 'developable_area_ha', 'capacity_used', 'capacity_basis', 'capacity_manual', 'density_estimate_units',
        'consented_units', 'unconsented_capacity', 'total_supply_units', 'built_units', 'future_supply_units', 'parcel_status',
        'permissions', 'permission_list', 'est_q4_2026', 'est_2027', 'est_2028', 'est_2029', 'est_2030', 'est_2031_plus',
        'energy', 'ue_water', 'ue_wastewater',
        'phase', 'rzlt_2027_share', 'geod_addresses_now', 'geod_new_since_2019', 'flag', 'notes', 'source_name']
R = ps[cols + ['geometry']].copy()
R = gpd.GeoDataFrame(R, geometry='geometry', crs=ps.crs)
R.to_file(OUT, layer='developable_land', driver='GPKG')
print(len(R), 'parcels ->', OUT); print(R.parcel_source.value_counts().to_string()); print(R.parcel_status.value_counts().to_string())
