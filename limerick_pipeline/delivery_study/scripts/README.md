# Limerick delivery study – rebuild steps

Run from a folder containing lp.xlsx, reg.pkl, abp.json and Limerick_Residential_Pipeline_Simplified.xlsx
(see ../../scripts for those), plus:

- `bcms_lim.pkl`: Limerick rows of the NBCO "Building Commencement and Completion Data 2014 – Present"
  CSV (data.nbco.gov.ie), filtered on LocalAuthority containing "Limerick".
- `lea.geojson`: Local Electoral Areas 2019, generalised 20m (Tailte Éireann ArcGIS service), COUNTY like '%LIMERICK%'.

- `nbh.geojson`: the nine city neighbourhoods (Council's 42-ED grouping, reprojected to WGS84; copy in this folder's parent).

Then: `python delivery_data.py && python delivery_analysis.py && python facts.py && python export_tables.py && python delivery_excel.py && node report.js`
