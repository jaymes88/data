# Limerick housing land register

One source for housing land in Limerick: the council's audit parcels (our updated version) plus parcels for residential consents outside the audit. It covers the full planning pipeline and the remaining capacity without consent, with each home counted once.

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

## County settlements audit

`inputs/RSCA_settlementsDP2022.gpkg` is the council's audit of sites in the smaller Development Plan 2022 settlements, received October 2026. It holds 48 sites in 13 settlements, each with an area and a density. It loads as parcel source "Council audit – county", with IDs like `CTY-BRUFF-1`:
- **Capacity:** area × the council density. Foynes gives a range (10-22), so the midpoint is used.
- **Tiers:** the council's TAZ tier is kept in `register_status` (Tier 1 serviced, Tier 2 serviceable).
- **Hospital site 5:** it is zoned Enterprise & Employment and has no density, so it carries the register's own area × density estimate and a note.
- **Later consents:** the audit was drawn for the 2022 plan. A consent lying 95%+ inside a site joins that site's parcel. A consent that only overlaps a site keeps its own land, and the site is clipped and its capacity scaled to what is left. Sites left under 0.05 ha are dropped: 7 were, all covered by consents granted since.
- **Interim estimates:** interim zoned-land parcels in the audited settlements are replaced by the audit.

The audit does not cover the Local Area Plan towns. Abbeyfeale, Adare, Caherconlish, Castleconnell, Croom, Kilmallock, Newcastle West, Patrickswell and Rathkeale stay on the interim estimate below. Validation checks C1–C3 report this.

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
