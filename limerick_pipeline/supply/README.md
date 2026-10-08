# Limerick housing supply GeoPackage

`Limerick_Housing_Supply.gpkg` (EPSG:2157) keeps three things apart and links them by keys:

| Layer | Type | What it is | Key |
|---|---|---|---|
| `sites` | Polygons | Council land register (city; county sites to be added with `scope = County`) | `site_id` |
| `permissions` | Points | One row per counted scheme. Tenure, delivery body, supply type are fields – filter/style, don't split layers | `perm_id`, `planning_ref` |
| `applications` | Points | Every application incl. superseded/refused/duplicate (audit trail) | `planning_ref` |
| `programmes` | Table | DHLGH social housing report, LDA, PBSA rows; `perm_id` links to permissions where matched | `programme_id` |
| `non_new_supply` | Table | Buy & Renew, remedial works – existing homes, not pipeline | `programme_id` |
| `site_reconciliation` | Table | Per site: capacity, complete, under construction, permitted not started, expired, in planning, residual, flags | `site_id` |
| `off_register_permissions` | View | City permissions not on a council site | `perm_id` |
| `edge_match_permissions` | View | Within 50 m of a site but not inside – point precision | `perm_id` |
| `ref_*` | Layers | Neighbourhoods, EDs, LEAs, LDA public land, KPMG audit polygons, register leads | |

`site_match`: Within site / Edge (≤50 m) – check / Off register / Not assessed (county sites pending).

Council sites drawn as two polygons under one reference (rsca 14, 49, 56, 133) are merged into one multipart site so capacity is counted once.

Sites the council removed in its 04/12/25 review with no reason recorded are added back from the initial audit (`in_audit0/original.shp`) when checked and found still developable. They are listed in `REINSTATE` in the build script and say so in `reconcile_action`. Currently: rsca 2 (Clonmacken Road, 2.193 ha, 77 units) – the adjoining land was built under 17/470; this remainder is undeveloped. rsca 112 (City Centre, council-owned, 1.346 ha, 61 units) – undeveloped, no permission; narrow irregular shape, so treat the capacity as an upper figure. rsca 35 (King's Island, council-owned, 0.454 ha, 27 units) – removed because it already had Part 8 approval 19/8004 (27 older persons homes, not started), although the council kept 28 other permitted sites; reinstated for consistency.

Rebuild: run `build_supply_gpkg.py` from the folder holding the study inputs (delivery.pkl, the pipeline workbook, shcp feed/crosswalk, nbh/lea/lda geojson, KPMG and PBSA shapefiles, the council sites GeoPackage at `in_sca/sca.gpkg`, the initial audit at `in_audit0/original.shp`).

## Standalone city sites audit

`Limerick_City_Sites_Audit_2026-10.gpkg` (layer `city_sites`) is the council's city sites file as it stands before the county audit is added: 134 sites, with sites drawn twice under one reference merged and rsca 2, 112 and 35 reinstated. Each site carries its capacity plus the planning reconciliation (complete, under construction, permitted not started, expired, in planning, residual, flag). It is the `sites` layer joined to `site_reconciliation`, exported on its own.

## Dashboard workbook

`Limerick_Housing_Supply_Dashboard.xlsx` (built by `supply_dashboard.py` from the GeoPackage): audit land, capacity, consents on and off audit land, and expected completions by year, split by sector, location, tenure and neighbourhood. Dashboard and Breakdowns totals are live formulas on the Sites and Schemes sheets. Delivery years are estimates from Limerick timing medians; the method is on the Assumptions sheet.

## CSO reconciliation

`cso_recon.py` compares CSO BHQ17 (units for which permission granted, Limerick; `inputs/CSO_BHQ17_Limerick.csv`) with granted residential applications in the planning register, split into single dwellings, 2–9 unit schemes, 10+ amendments, other 10+ and schemes in the tracker. Run it before `supply_dashboard.py`. The dashboard's `CSO reconciliation` sheet adds a yearly allowance for one-off houses (CSO 2023–2025 average) and 2–9 unit schemes outside the tracker (register 2023–2025 average), multiplied by an editable build-out share (default 73%, from the delivery study's 1–9 unit band).
