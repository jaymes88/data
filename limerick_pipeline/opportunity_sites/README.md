# Limerick opportunity sites register

Sites spotted on a desk review that look underused or worth investigating, for the council to test against the 2040 housing shortfall. This is separate from the land register: homes here are indicative and are **not** counted as supply.

`Limerick_Opportunity_Sites.gpkg` has two layers:
- **`opportunity_sites`:** one polygon per site, with an ID such as OPP-BRUFF-003.
- **`summary_by_catchment`:** site counts, hectares and indicative homes by catchment.

## Site categories
- **Opportunity site:** in a city neighbourhood, key town or village.
- **Rail corridor new town (long term):** the "EXP" sites at Annacotty, Lisagny, Killonan, Oola, Pallasgreen and Dromkeen. These belong to a longer-term idea of new towns on the rail lines. They're kept out of the neighbourhood and settlement totals and set to 10+ years.

## Fields filled automatically (recalculated by `build_opportunity_sites.py`)
- **Location:** catchment, electoral area and area. Your settlement label decides the catchment.
- **Overlap:** any land register parcels the site overlaps, so no land is counted twice.
- **GeoDirectory:** residential addresses on the site, and how many are vacant or derelict. This covers residential addresses only.
- **Zoning:** the main zone and the full split, whether housing is allowed (Yes / Mixed use / No / Partly), and the share on the RZLT map.
- **Planning history:** the number of applications on the site and the latest one, from the national planning register.
- **Capacity:** the Council density for the catchment (Variation No. 3, as in the needs model) × developable share (0.91, editable) × area gives indicative homes. A second figure excludes any part already in the land register. Confidence starts at Low.
- **Constraints (from the council layers in `inputs/constraints/`):**
  - `flood_zone_a_share` and `flood_zone_b_share`: share of the site in Flood Zone A, and in Flood Zone B outside Zone A. The Zone B layer (47 MB) is not in the repository: it is `floodb.gpkg` in `Dropbox/Spatialis/Tools/limerickhds2040/source/`, and the build reads it from `in_constraints/`. Overlapping polygons in the flood layers are merged first, so no area counts twice.
  - `rps_on_site` and `rps_within_50m`: protected structure numbers on the site and within 50 m (setting). County structures are the October 2026 RPS layer; city structures are from the 2010 City Development Plan layer.
  - `aca_name` and `aca_share`: the ACA the site falls in and the share inside. These come from the 2010 city and county development plan layers.
  - `rps_setting_share` and `heritage_share`: the share of the site within 30 m of a protected structure (the RPS points mark the building, not its curtilage), and the share in an ACA or within that 30 m. One structure on a large site therefore affects only the land around it.
  - `derelict_sites_register`: Derelict Sites Register entries on the site or within 25 m (the entries are points at the address).
  - The pick-list fields are set from these. Flood: significant if 25% or more of the site is in Zone A, or half or more is in Zone A or B; minor if any part (above 1%) is in either. Protected structure or ACA: significant if 25% or more of the site is in an ACA or within 30 m of a protected structure; minor if any part is (above 1%), or a protected structure is within 50 m. Derelict or vacant register: Yes if a derelict site entry is on or next to the site. These thresholds are a judgement; change any site by hand and the entry is kept on rebuild ("Not checked" is not kept).
  - The vacant points supplied are the GeoDirectory vacant residential addresses, which already give `geod_vacant`.
- **Wastewater:** a settlement-level Uisce Éireann status, where the council's HDAP submission names the settlement as Red or Amber.

## Fields to fill in as sites are investigated
- **What's there:** current use and site type. Town and village sites start as Infill (the focus of the review); confirm or change it.
- **Constraints:** archaeology, ecology, access and contamination. Flood, protected structure or ACA are filled automatically but can be overridden.
- **Ownership:** status, type and folio reference. Owner names are not recorded.
- **Delivery:** energy and water, likely route and timeframe, barriers.
- **Tracking:** status, priority, next action, last updated, updated by, notes.

Coded fields have drop-down lists stored in the GeoPackage, which QGIS shows as value lists. "Not yet checked" is kept separate from "Unknown after checking".

**Updating:** run `python build_opportunity_sites.py <returned copy.gpkg>`. Every entry made in the returned copy is kept, existing IDs never change, new polygons get the next ID in their town (their settlement comes from the catchment they sit in), and the automatic fields are recalculated. The last returned copy is in `inputs/`.
