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

Rebuild: run `build_supply_gpkg.py` from the folder holding the study inputs (delivery.pkl, the pipeline workbook, shcp feed/crosswalk, nbh/lea/lda geojson, KPMG and PBSA shapefiles, the council sites GeoPackage at `in_sca/sca.gpkg`).
