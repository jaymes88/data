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
- **Wastewater:** a settlement-level Uisce Éireann status, where the council's HDAP submission names the settlement as Red or Amber.

## Fields to fill in as sites are investigated
- **What's there:** current use and site type. Town and village sites start as Infill (the focus of the review); confirm or change it.
- **Constraints:** flood, protected structure or ACA, archaeology, ecology, access, contamination.
- **Ownership:** status, type and folio reference. Owner names are not recorded.
- **Delivery:** energy and water, likely route and timeframe, barriers.
- **Tracking:** status, priority, next action, last updated, updated by, notes.

Coded fields have drop-down lists stored in the GeoPackage, which QGIS shows as value lists. "Not yet checked" is kept separate from "Unknown after checking".

Rerunning the build script overwrites the file. Once people start filling in the register, merge their edits rather than rerunning.
