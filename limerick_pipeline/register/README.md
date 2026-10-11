# Limerick housing land register

One source for housing land in Limerick: the council's audit parcels (our updated version) plus parcels for residential consents outside the audit. It covers the full planning pipeline and the remaining capacity without consent, with each home counted once.

## Tables

| Table | Type | One row per | Key |
|---|---|---|---|
| `parcels` | Polygons | piece of housing land (parcels do not overlap) | `parcel_id` |
| `parcel_permissions` | Table | counted permission, linked to exactly one parcel | `perm_id` → `parcel_id` |
| `parcel_summary` | View (polygons) | parcel, with totals calculated live from `parcel_permissions` | `parcel_id` |
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

## GeoDirectory: completions and built-out parcels

With a GeoDirectory residential address extract at `in_geodir/limerick_geod_residential_points.gpkg` (licensed; not committed), the build counts new addresses (created on or after the application was received) inside each permission boundary, kept within its parcel. Each address is credited to one permission only.

- A scheme with built addresses for 95% or more of its units moves to Complete. `status_cis` keeps the CIS status and `status_source` records the extract date. Its delivery-year estimates are zeroed.
- Other differences (new addresses on a scheme recorded as not started, fewer addresses than units on a completed scheme, none found) go to `register_checks` and the GeoDirectory checks sheet for a person to confirm.
- `parcel_status` is calculated: Built out when every counted home is complete and no council capacity is left. Built-out parcels stay in the register as delivery history; future supply is zero. Filter them off the map rather than deleting.
- `geod_new_build_outside_parcels` lists clusters of 10+ new addresses (since 2019) outside every parcel, with any granted applications on the land. Recent or active ones point to permissions the register is missing.

Rerun the build with each new extract (quarterly).
