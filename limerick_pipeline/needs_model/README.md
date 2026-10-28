# HDS 2040 needs model: land tabs

`Limerick-HDS-2040-needs-model.xlsx` is the Spatialis needs model with two tabs added:
- **Zoned land vs need** (`hds_land_tab.py`): homes needed 2026–2040 by catchment against the land register's identified supply, valued at Council densities, with the additional land needed to 2040 and with headroom. The remainder of the county sits below the total and is not analysed.
- **Opportunity sites & options** (`hds_options_tab.py`): what the opportunity sites register could add, what is left for infill on sites not yet identified, and the land that infill needs at Council density or at a higher city infill density (a lever). Catchments with constrained infill, currently Kings Island for flood risk, are flagged so their remainder can be placed elsewhere.

To rebuild: `python hds_land_tab.py <model.xlsx> tmp.xlsx && python hds_options_tab.py tmp.xlsx <out.xlsx>`. Then recalculate in Excel or LibreOffice. The supply and opportunity figures are snapshots of the land register and the opportunity sites register; the need figures are live formulas.
