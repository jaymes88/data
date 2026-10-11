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
