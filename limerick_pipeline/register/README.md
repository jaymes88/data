# Limerick housing land register

One source for housing land in Limerick: the council's audit parcels (our updated version) plus parcels for residential consents outside the audit. It covers the full planning pipeline and the remaining capacity without consent, with each home counted once.


## Start here: one file

`Limerick_Developable_Land.gpkg` is the complete land register in one file:
- **`developable_land`:** one polygon per parcel (452), with every parcel field (73 columns). That covers capacity, consented and future supply, homes by status, delivery by year, bedroom mix, energy, water and wastewater, density working, catchment and GeoDirectory figures, and `permission_list` as text.
- **`permissions`:** one row per counted permission (262), with dates, status, tenure, route, bedroom mix and delivery years, linked to the polygons by `parcel_id`. In QGIS, add a join or a relation on `parcel_id`.
- **`developer` and `landowner`:** `developer` lists the applicants of the parcel's counted permissions, largest first. Each permission's name and source are in the `permissions` layer (`developer`, `developer_source`). Sources, in order: the applicant on the council's ePlanning file (Part 8 files are the council's own), the An Bord Pleanála case page for SHDs, then the CIS project team, CIS description and delivery body. Names are as the source records them; built by `fetch_applicants.py` and `developer_names.py`. `landowner` is the council audit value (Council or Private) and is otherwise blank, for the council to complete.
- **`local_name`:** a standard description, e.g. "Caherdavin: 43 homes, houses – private scheme" or "Kilmallock: council audit site 4, 125 homes capacity". The original CIS heading or audit name is kept in `source_name`.
- **Review (October 2026):** every parcel was reviewed and accepted, so the review columns are gone. The land and permissions removed at review (Kilmallock zoned land 002 and 003, and permission 19/149) stay out on every rebuild through `inputs/removed_parcels.gpkg` (copied to `in_review/` for the build).
- **Servicing:** a parcel with a live planning permission counts as serviced (tier 1), because the council would not have granted it otherwise.

- **Manual land additions:** `inputs/manual_geometry.gpkg` holds land drawn by hand and joined to an existing audit parcel. The first is 4.15 ha added to CITY-107 (27 Oct 2026), within its 2,500-home capacity.
- **Manual capacities:** `inputs/manual_capacity.csv` (copied to `in_review/` for the build) holds capacities set by hand, each with a reason, who set it and when. On those parcels `capacity_manual` = Yes, `capacity_basis` starts "MANUAL OVERRIDE", and the note records the old and new figures. The first is CITY-107, the masterplanned city-centre mixed-use site of about 60 ha, set to 2,500 homes on 27 Oct 2026. Half the site lies in Singland/Garryowen, so the `catchment_split` column shares its land and homes 50/50 between City Centre and Singland/Garryowen in the needs model.

Everything else is either the build engine (`Limerick_Housing_Land_Register.gpkg`) or source data (`inputs/`).

## Tables

| Table | Type | One row per | Key |
|---|---|---|---|
| `parcels` | Polygons | piece of housing land (parcels do not overlap) | `parcel_id` |
| `parcel_permissions` | Table | counted permission, linked to exactly one parcel | `perm_id` → `parcel_id` |
| `parcel_summary` | View (polygons) | parcel, with totals calculated live from `parcel_permissions` | `parcel_id` |
| `active_parcels` | View (polygons) | `parcel_summary` without Finished parcels: land still to deliver homes | `parcel_id` |
| `register_checks` | View | problem to fix (duplicate refs, unlinked permissions, empty consent parcels) | |
| `lookup_values`, `data_dictionary` | Tables | allowed values; field meanings and update rules | |

`Limerick_Housing_Land_Register.xlsx` holds the same two tables for people who don't use GIS. Parcel totals there are SUMIFS on the Permissions sheet, with dropdowns on parcel_id, status and counts_toward_totals, and a checks panel on the Summary sheet.

## How double counting is prevented

1. Units are only entered on permissions, never on parcels. The one unit figure typed on a parcel is the council's capacity estimate for an audit parcel.
2. Each permission has one `parcel_id`. Parcels do not overlap: consent parcels are clipped to exclude audit land, and consents on the same land (phases, additional applications) share one parcel.
3. Only rows with `counts_toward_totals = Yes` add up. Amendments, repeats and replaced permissions stay on record as `No`.
4. On an audit parcel, supply = consented units + max(capacity − consented, 0). On a consent parcel, supply = consented units.
5. Checks flag a planning reference counted twice, a permission linked to a missing parcel, a duplicate id, and a consent parcel with nothing counted on it.

## Build

Run from the study folder after `supply/build_supply_gpkg.py` and `supply/supply_dashboard.py`:

`python build_land_register.py && python build_register_xlsx.py`

Consent parcels use the planning application boundary where one exists (240 of 265 schemes). The rest get a 25 m circle round the scheme point, flagged in `notes`. The `developable_area_ha` field is the council's net area on audit parcels; `mapped_area_ha` is the polygon as drawn.

## GeoDirectory: completions and finished parcels

With a GeoDirectory residential address extract at `in_geodir/limerick_geod_residential_points.gpkg` (licensed; not committed), the build counts new addresses (created on or after the application was received) inside each permission boundary, kept within its parcel. Each address is credited to one permission only.

- A scheme with built addresses for 95% or more of its units moves to Complete. `status_cis` keeps the CIS status and `status_source` records the extract date. Its delivery-year estimates are zeroed.
- Other differences (new addresses on a scheme recorded as not started, fewer addresses than units on a completed scheme, none found) go to `register_checks` and the GeoDirectory checks sheet for a person to confirm.
- `parcel_status` is calculated: Finished when every counted home is complete and no council capacity is left. Finished parcels stay in the file as delivery history with zero future supply; `active_parcels` leaves them out. Don't delete them.
- An extension of duration counts addresses from 1 January of the parent permission's year (from `related_ref`), so homes built under the parent before the extension was lodged are found.
- Schemes of 10+ homes count as complete when GeoDirectory is one address short (95% of 12 would demand all 12).
- `geod_new_vacant`: new homes GeoDirectory marks vacant. `register_checks` lists Finished parcels where more than 10% are vacant.
- `geod_new_build_outside_parcels` lists clusters of 10+ new addresses (since 2019) outside every parcel, with any granted applications on the land. Recent or active ones point to permissions the register is missing.

Rerun the build with each new extract (quarterly).

## Servicing (council capacity audit)

Only three servicing fields are kept, all from the council capacity audit Excel (May 2026): `energy`, `ue_water` and `ue_wastewater` (Uisce Éireann capacity). Where a parcel has a live planning permission and the audit has no entry, water and wastewater read "Y (permission granted)". `county_audit/council_servicing.py` still reads the full set of columns into `inputs/council_servicing.csv` if they're needed again.

## County settlements audit

**Council polygons (23 Oct 2026).** `inputs/county_audit_2026_sources/DevPlan_Variation_Settlement_RSCA_23_10_26.gpkg` has one layer per settlement, with the Excel figures joined, for Abbeyfeale, Askeaton, Caherconlish, Cappamore, Castleconnell, Croom, Kilmallock, Newcastle West and Rathkeale.
- **Standardising and checking.** `county_audit/rsca26_load.py` standardises the site numbers and joins pieces drawn under one number. It shares an Excel site's capacity between its numbered parts by area (e.g. Kilmallock 1.1 and 1.2), and gives sites not in the Excel the town's average density. The checks are in `inputs/rsca26_checks.csv`.
- **The council file wins.** For these nine towns its polygons replace the earlier matching, outlines and 2022 audit, and no interim zoned-land estimate is made there.
- **Other towns.** Adare, Patrickswell, Bruff, Hospital, Kilfinane and Murroe, and the eight 2022-only settlements, are unchanged.


`inputs/county_audit_2026.gpkg` (layer `sites`) is the county audit the build loads, as parcel source "Council audit – county", with IDs like `CTY-RATHKEALE-3`. It is assembled from:
- **Council capacity audit Excel (May 2026).** 126 sites in 15 settlements, with area, density, capacity, tier, wastewater, permission and site status. The Excel has no polygons, so `county_audit/sca_match.py` matched each site to a zoning polygon by area, zoning type and the permissions it names. Matches were kept where confirmed against the council's maps: all of Kilmallock; corrected placements in Rathkeale, Caherconlish and Castleconnell; Croom except site 4; and elsewhere only the high-confidence matches. 90 sites are placed.
- **Council-supplied polygons** (`inputs/county_audit_2026_sources/*.gpkg`, including Askeaton). All of them are included. The ones with no Excel row yet carry site numbers U1, U2 and so on, or the number from the council map (Caherconlish 7, Castleconnell 9 and 10). Where the council gives no capacity, capacity = area × the town's average density for that type of site in the council Excel (`capacity_basis` says so); the county median is used where the town has none.
- **2022 county audit** (`inputs/RSCA_settlementsDP2022.gpkg`) for what the Excel does not cover: Ballingarry, Bruree, Doon, Dromcolliher, Foynes, Glin, Pallasgreen and Pallaskenry, and Hospital site 5.

`inputs/county_audit_2026_unplaced.csv` lists the 34 Excel sites still without a polygon. To place one, draw or copy its polygon into the `sites` layer with the Excel values, then rebuild. **From now on the GeoPackage is the source: don't rerun `sca_assemble.py`, or manual placements will be overwritten.**

When loading:
- **Capacity:** the council's figure is used, and a council capacity of 0 stands.
- **Permissions on 2026 sites:** the May 2026 sites and council outlines keep their full outline. A permission lying 50%+ inside one is attached to it, so its homes count against the council's capacity there.
- **Permissions on 2022 sites:** these predate later consents. A consent that only partly overlaps a 2022 site keeps its own land; the site is clipped and its capacity scaled to what is left. 2022 sites left under 0.05 ha are dropped.
- **Other fields:** tier and wastewater go into `register_status`; site status, permission, the council's note and how the site was placed go into `notes`.

Towns where some sites are unplaced keep the interim zoned-land estimate on the rest of their new residential zoning (validation check C2).

## Zoned land without consent (interim, for settlements without a council audit)

Askeaton is missing from the national zoning file. Its future residential zoning comes from `inputs/askeaton_zoning.gpkg` (supplied October 2026; copy it to `in_zoning/askeaton_zoning.gpkg` before building). Residential Development Areas are treated as new residential and Residential Service Sites as serviced sites. Phase 2 areas are flagged. The parcels also note Askeaton's Red wastewater status from the council's HDAP 2026.

`pull_zoning.py` downloads Limerick's current zoning (national generalised zoning types, GZT) and the Residential Zoned Land Tax draft map 2027 to `in_zoning/`. The build adds parcels with source "Zoned land – no consent (estimate)" for new residential zoning (R1, plus R3 zones described as new residential, residential development area or serviced sites). It only uses zoning that isn't already in another parcel and isn't built on: existing GeoDirectory homes plus 15 m are cut out, and pieces under 0.1 ha are dropped. Mixed-use and town-centre zoning are not included. Phase 2 zoning is included and flagged.

Capacity = mapped area × developable share × density:
- **Developable share:** 0.91, the council city audit's developable area divided by its mapped area.
- **Density:** the median homes per hectare of permitted Limerick schemes of 10+ homes, measured over the planning boundary. That gives 25 in county towns and villages, 34 in city suburbs and 101 in the city centre (six schemes only). Serviced-site zoning uses the lower quartile of county schemes, 19.
- Each parcel's `density_basis` field states its figure and source. These figures are recalculated from the data on each build.

`rzlt_2027_share` records how much of each parcel is on the RZLT map. Parcels also carry GeoDirectory address counts (`geod_addresses_now`, `geod_new_since_2019`), so building on zoned land without a linked permission shows up on refresh.

## Study catchments

With the study catchments at `in_catch/lccc_catchments_All.shp` (9 city neighbourhoods, 6 key towns, 9 large villages), each parcel gets `catchment`, `catchment_type` and `catchment_share`: the catchment it overlaps most and the share of the parcel inside it. Parcels touching no catchment are "Rest of county". Permissions carry their parcel's catchment.

- The GeoPackage has a `catchment_summary` view and a `ref_study_catchments` layer.
- The Excel has a Catchments sheet of live SUMIFS.

The neighbourhood polygons are identical to the ones used elsewhere in the study. The catchment file numbers them differently from 2 onwards: King's Island is 2 there and 1a elsewhere.

Parcels outside every catchment but clearly tied to a key town or large village are counted in that settlement's figures, with the reason in `catchment_basis`:
1. zoned in that settlement's local area plan; or
2. within 500 m of the catchment; or
3. named in the scheme title and within 2 km.

The rest stay as Rest of county.

## Every parcel contributes

Parcels that would otherwise add nothing get a capacity, with the reason in `capacity_basis`:
- **Consent parcels with no live permission:** the units of the expired permission (7 parcels) or of the application still in planning (10 parcels). The land has already been put forward for housing.
- **Anything still without capacity:** council audit parcels the council left at 0 (10 small city-centre sites and CITY-169), and consent parcels with no unit count (4). These get developable area × the density for their area type. Where no developable area is recorded, it's the mapped area × 0.91.

## Indicative yield on every parcel

`density_estimate_units` = developable area (or mapped area x the audit's developable share) x the local median density of permitted Limerick schemes. Filled for all parcels so land can be compared on one basis. It does not enter the totals: `capacity_used` (council capacity, zoning estimate, or consented units) does.

## Validation

`validate_register.py` writes `Validation_Report.xlsx`: integrity checks (I), provenance against the live planning register, An Coimisiún Pleanála and BCMS (P), external checks against CSO (E), county audit readiness (C), and a stratified QA sample with planning links for a person to open. Rerun after every rebuild and after the county settlements audit is loaded.

## Delivery estimates net of homes already built (30 October 2026)

The yearly delivery estimates (`est_q4_2026` to `est_2031_plus`) now cover only homes not yet built. For each permission they add up to at most its units minus `units_built` (the GeoDirectory built count for part-built schemes), and any excess comes off the earliest years first (`net_built.py`, also called from `build_land_register.py`). Before this, 589 homes on 19 part-built schemes were in the estimates although GeoDirectory already showed them built; the largest was Greenpark SHD (121 of 371).

Counted expected completions are now 8,106 (was 8,695): Q4 2026 293, 2027 1,723, 2028 1,711, 2029 1,955, 2030 851, 2031+ 1,574. The remaining difference from consented homes not yet built (8,262) is 156 homes in four stalled permissions, which are counted as consented but given no expected completions.

The fix was applied to the saved register, workbook and land file with `python net_built.py`. `Validation_Report.xlsx` was rerun on 30 October 2026: 18 PASS, 12 WARN, no FAIL, as before. The only change is P5 (not-started schemes with a building control commencement notice), up from 2 to 4 with the NBCO data published 29 October: 2460570 (40 homes, commenced 21/10/2026) and 2460046 (7 homes, 16/10/2026) join 2560399 and 21630.

## Status overrides (30 October 2026)

`inputs/status_overrides.csv` lists permissions whose status later evidence has changed; `status_overrides.py` applies it (and `build_land_register.py` calls it on a full rebuild). The first four are schemes the register showed as not started that have a building control commencement notice in the NBCO data published 29 October 2026: 2460570 (40 homes), 2560399 (76), 21630 (51) and 2460046 (7). They are now under construction from their commencement dates, with delivery estimates re-projected by the supply dashboard's method for schemes on site. Homes under construction rise from 3,711 to 3,885; total expected completions stay at 8,106 but about 90 move from 2029 into 2027–2028. The validation report was rerun: 19 PASS, 11 WARN (P5 now passes).
