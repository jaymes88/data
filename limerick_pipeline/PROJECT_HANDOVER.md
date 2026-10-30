# Limerick HDS 2040: project handover

State at **30 October 2026**. Spatialis work for Limerick City and County Council: the residential pipeline, the housing land register, the opportunity sites register and the HDS 2040 needs model, which feed the online dashboards (story, explorer, tracker).

Every figure below was read from the files on this branch on 30 October 2026, not from memory. A new session should check them before changing anything (see the last section).

## Where things live

| Place | What is there |
|---|---|
| GitHub `jaymes88/data`, branch `claude/quirky-edison-lxbpgj`, folder `limerick_pipeline/` | The data products and the scripts that build them (this file). |
| Dropbox `Spatialis/Tools/limerickhds2040/lhds2040-source/` | The dashboard source (story, explorer, tracker, Cloudflare build). Has its own `HANDOVER.md`. Built and deployed from James's Mac. |
| Dropbox `Spatialis/Tools/limerickhds2040/source/` | Raw data: SAPS CSVs, prices workbook, CIS exports, transport zip, the council constraint layers (`flooda.gpkg`, `floodb.gpkg`, `rps.gpkg`, `aca.gpkg`, `derelict_sites.gpkg`, `vacants.gpkg`), and copies of the latest land file and needs model. |
| Dropbox `lhds2040-source/gd/limerick_geod_residential_points.gpkg` | GeoDirectory residential address points (licensed, 49 MB). Not in the repository. Needed for the register build and the validation report. |

Each folder in `limerick_pipeline/` has a README with the method and dated change notes. Read them before changing that folder:
`register/README.md`, `opportunity_sites/README.md`, `needs_model/README.md`, `supply/README.md`, `delivery_study/scripts/README.md`, `scripts/unit_mix/README.md`.

## The datasets and how they connect

```
planning register, CIS, building control, GeoDirectory, CSO
        │
supply/Limerick_Housing_Supply.gpkg  +  supply/Limerick_Housing_Supply_Dashboard.xlsx   (pipeline of schemes, council city audit)
        │
register/  →  Limerick_Housing_Land_Register.gpkg / .xlsx   (build engine: parcels + permissions, no double counting)
          →  Limerick_Developable_Land.gpkg                (the one file people use: developable_land + permissions layers)
          →  Validation_Report.xlsx
        │
        ├── opportunity_sites/Limerick_Opportunity_Sites.gpkg   (separate register; indicative homes, not supply)
        │
        ├── needs_model/Limerick-HDS-2040-needs-model.xlsx       (need by catchment vs land, options, pipeline tab)
        │
        └── Dropbox lhds2040-source/inputs/Limerick_Developable_Land_2026-10-30.gpkg
               → build2/register.py → build2/tracker.py → tracker/data.json → build_all.sh → Cloudflare zip
```

| Dataset | Current file | What it is |
|---|---|---|
| Land register (use this) | `register/Limerick_Developable_Land.gpkg` (same file as Dropbox `Limerick_Developable_Land_2026-10-30.gpkg`) | 452 parcels (`developable_land`, 73 columns) and 262 counted permissions (`permissions`), linked by `parcel_id`. |
| Register engine | `register/Limerick_Housing_Land_Register.gpkg` and `.xlsx` | Same data as tables, views and live formulas. The `.gpkg` is what the scripts patch and export from. |
| Validation | `register/Validation_Report.xlsx` | 30 checks: integrity, provenance against live sources, CSO comparisons, county audit readiness. |
| Opportunity sites | `opportunity_sites/Limerick_Opportunity_Sites.gpkg` | 188 analyst sites with desk-based fields, constraint checks and pick-lists. Kept separate from supply. |
| Needs model | `needs_model/Limerick-HDS-2040-needs-model.xlsx` | Spatialis needs model plus three added tabs: Zoned land vs need, Opportunity sites & options, Pipeline & permissions needed. |
| Supply dashboard | `supply/Limerick_Housing_Supply_Dashboard.xlsx` | Upstream scheme pipeline. **Its delivery estimates (9,051) predate the register's GeoDirectory completions, the netting of built homes and the status overrides. Use the register's figures (8,106).** |

## Headline figures to check against (30 October 2026)

**Land register** (`Limerick_Developable_Land.gpkg`, layer `developable_land`)

| Measure | Value |
|---|---|
| Parcels | 452 (City 241, County 211); 848.6 developable ha |
| By source | Planning consent – not in council audit 157; Council audit – county 152; Council audit (city) 134; Zoned land – no consent (estimate) 9 |
| Parcel status | No consent 248; Consented – not built 130; Finished 49; Partly built 25 |
| Consented homes | 10,494 = complete 1,643 + under construction 3,885 + permitted not started 4,810 + stalled 156 |
| Not counted as consented | Expired 278; in planning 250 |
| Unconsented capacity | 17,727 |
| Total supply / built / future supply | 28,221 / 2,232 / 25,989 |
| Consented, not yet built | 8,262 |
| Expected completions (sum of `est_*`) | 8,106: Q4 2026 293; 2027 1,759; 2028 1,757; 2029 1,872; 2030 851; 2031+ 1,574 |
| Future supply by place type | City neighbourhoods 17,065; key towns 6,229; large villages 2,133; rest of county 562 |
| Permissions | 262 rows, all counted |

The 156-home gap between consented-not-built (8,262) and expected completions (8,106) is the four stalled permissions (Newcastle West 6, Patrickswell 1, Moroe 3, City 21): consented but given no completions. Footnote it wherever both figures appear.

**Validation report:** 19 PASS, 11 WARN, no FAIL (rerun 30 October 2026).

**Opportunity sites:** 188 sites: 159 opportunity sites (city 79, key towns 10, large villages 70) and 29 rail corridor new town sites (long term, not counted). Indicative homes not already in the register: 15,482 on opportunity sites (city 12,516, key towns 611, villages 2,355); 6,665 on rail corridor sites. Flood: 18 significant, 14 minor. Protected structure or ACA: 25 significant, 56 minor. Derelict Sites Register entry on or next to the site: 22.

**Needs model** (default levers: plan to 2040, S1 Core Strategy allocation, S1 unit mix, S1 working tenure, city-first social with 10% floor and 20% ceiling, Council density minimum, 40% headroom)
- New homes 2026–2040: 39,864. Intro validation: ALL PASS (91 checks).
- Zoned land vs need (24 catchments): need 35,970; identified supply 25,734; 16 of 24 catchments short; additional land 313 ha to 2040, 615 ha with 40% headroom. City neighbourhoods short 12,792; key towns +2,876 overall (Abbeyfeale short 182); villages short 320 overall. Remainder of county (3,894 homes) shown below the total and not analysed.
- Opportunity sites & options: city 12,792 short → 832 covered by opportunity sites where zoning allows → 7,301 with rezoned sites → **5,492 left for infill on sites not yet identified** (about 110 ha at Council densities, about 55 ha at 100 homes/ha). Kings Island flagged as flood constrained: 535 homes to place elsewhere. Villages 684 short → 450 after sites where zoning allows → 0 after all sites. Key towns 182 → 0.
- Pipeline & permissions needed (Limerick, defaults): homes still to deliver 28,488; permissions needed from now 26,806 (about 2,310 a year to May 2038, against 985 a year granted in 2018–2025); applications 25,591; permissions needed before now 7,935.

## Decisions and rules (do not reverse without asking)

Dates are from the commit history and READMEs.

**Scope and counting**
- Each home is counted once. Units sit only on permissions; parcels don't overlap; only `counts_toward_totals = Yes` adds up (register README).
- The study covers 9 city neighbourhoods, 6 key towns and 9 large villages. The rest of the county is out of scope: shown muted, below the totals, as "Remainder of county (not analysed)" (27 Oct).
- All parcels were reviewed and accepted, and the review columns removed. Kilmallock zoned land 002 and 003 and permission 19/149 were removed at review and stay out via `register/inputs/removed_parcels.gpkg` (26–27 Oct).
- A parcel with a live planning permission counts as serviced (tier 1). Servicing fields kept: `energy`, `ue_water`, `ue_wastewater` only (27 Oct).

**Council data**
- Council audit capacity is used as given, including 0. The council's 23 Oct 2026 settlement polygons replace earlier matching for Abbeyfeale, Askeaton, Caherconlish, Cappamore, Castleconnell, Croom, Kilmallock, Newcastle West and Rathkeale. Where the council gives no capacity, the town's average density is used.
- `register/inputs/county_audit_2026.gpkg` is now the source for the county audit: don't rerun `sca_assemble.py` (register README).

**Manual inputs** (each logged with a reason in `register/inputs/`)
- **CITY-107**, the masterplanned city-centre mixed-use site, is set to 2,500 homes by hand (`manual_capacity.csv`, 27 Oct). A 4.15 ha addition is within the same capacity (`manual_geometry.gpkg`). The parcel is now 72.7 ha as mapped. It was described as about 60 ha when the capacity was set, and as 70 ha later; the register README still says "about 60 ha".
- **CITY-107 split:** half its land and homes are in Singland/Garryowen, so `catchment_split = City Centre:0.5;Singland/Garryowen:0.5`. The needs model gives each 1,244 homes; the tracker build cuts the parcel in two (28 Oct).
- **Status overrides:** later evidence overrides a permission's status (`status_overrides.csv`, 30 Oct). The first four (2460570, 2560399, 21630, 2460046; 174 homes) have building control commencement notices, so they are under construction from their commencement dates. Add rows as new notices appear.

**Delivery estimates**
- Estimates are net of homes already built (30 Oct). Each permission's yearly estimates add to at most its units minus `units_built` (GeoDirectory built count), taken off the earliest years first (`net_built.py`). This removed 589 homes on 19 part-built schemes that had been counted again (largest: Greenpark SHD, 121 of 371).

**Land file fields**
- `developer` holds applicant names: council ePlanning first, then An Bord Pleanála for SHDs, then CIS. Names are as recorded.
- `landowner` is the council audit value (Council or Private), otherwise blank for the council to complete; "Unknown" was cleared (28 and 30 Oct).
- `local_name` is a standard description; the original name is in `source_name`.

**Opportunity sites**
- The register is separate from supply; its homes are indicative.
- Most town and village sites are infill. "EXP" sites are rail corridor new towns, long term and not counted.
- Sites keep their IDs on rebuild, and entries in a returned copy are kept.

**Opportunity sites constraints (28 Oct; thresholds are analyst judgement, not policy tests)**
- **Flood:** significant if 25% or more of the site is in Zone A, or 50% or more is in Zone A or B; minor if any part is.
  - Zone B is counted outside Zone A only.
  - Overlapping flood polygons are merged first.
- **Heritage:** measured as a share of the site.
  - The share used is the part in an ACA or within 30 m of a protected structure.
  - Significant at 25% or more; minor for any part, or a protected structure within 50 m.
  - A single structure on a large site no longer makes the whole site significant.
- **Derelict Sites Register:** Yes if an entry is on the site or within 25 m.

**Needs model**
- Headroom 40% (lever).
- City infill density lever (default 100 homes/ha). Its purpose is to show the council that density is the only way to meet the city target.
- Kings Island is flagged as flood constrained.

**Tracker tool**
- The "Pipeline & permissions needed" tab reproduces the tracker's forecasting tool exactly on default settings. `needs_model/pipe_check.py` confirms this.

## Known limits and open items

- **City protected structures and ACAs** come from 2010 City Development Plan files. County protected structures are the October 2026 layer. Check against the current plan's RPS and ACAs.
- **The Flood Zone B file** (`floodb.gpkg`, Dropbox `source/`) contains overlapping duplicate polygons. The build merges them; dissolve the layer if it is used elsewhere. It is too large for the repository.
- **Vacancy:** the vacant points supplied are GeoDirectory vacant addresses, not the vacant sites levy register. They duplicate `geod_vacant`.
- **CIS licence:** CIS data is licensed. Check the licence before promoter names are shown to the council on the live site.
- **Private individuals:** the `developer` field includes some private individuals' names from the planning register. That is public record, but review before wider sharing.
- **County audit gaps:** 34 council Excel sites are still without a polygon (`register/inputs/county_audit_2026_unplaced.csv`). Two plan areas still use interim zoning estimates (validation C2).
- **Full rebuilds:**
  - **Register:** `build_land_register.py` needs these inputs that are not in the repository. Download each again:
    - `in_zoning/` (`pull_zoning.py`);
    - `in_pp_full/sites.gpkg` (`supply/pull_sites.py`);
    - `in_geodir/` (GeoDirectory, from Dropbox);
    - `in_catch/lccc_catchments_All.shp` (the study catchments; export the `ref_study_catchments` layer from the register engine if the shapefile is lost);
    - `lea.geojson` (Tailte Éireann / CSO LEA 2019, county like Limerick);
    - `nbh.geojson` (`delivery_study/`).

    The supply GeoPackage and dashboard are treated as fixed inputs: rebuilding them needs older working files that are no longer available.
  - **Validation report:** needs the GeoDirectory points and `bcms_lim.pkl`, rebuilt from the NBCO "Building Commencement and Completion Data" CSV filtered to Limerick. It also needs `reg.pkl` (`scripts/pull_register.py`), `cso_recon.pkl` (`supply/cso_recon.py`), `lea.geojson`, and copies of `rel.py`, `build_supply_gpkg.py`, `delivery_data.py` and `sources.py` in the working folder.
- **Small changes without a full rebuild:** apply them to the saved register with `register/net_built.py` and `register/status_overrides.py` (both safe to rerun), then:
  1. `export_land_layer.py` (land file);
  2. recalculate the register workbook;
  3. rebuild the needs model's pipeline tab with `hds_pipeline_tab.py`.
- **Tracker (Dropbox):**
  - `build2/register.py` reads `inputs/Limerick_Developable_Land_2026-10-30.gpkg`, and `build2/tracker.py` uses relative paths (both updated 30 Oct; old versions kept as `*_2026-10-28.py.bak`).
  - `relocate.py` was run on the Mac, so other workspaces must run `python3 relocate.py ../source` first.
  - Node.js is installed on the Mac, with the libraries in `~/lhds_libs/story`.
  - `build_all.sh` ran cleanly on 30 Oct.
  - The dashboard conversation was asked to log these changes in `lhds2040-source/HANDOVER.md`.
- **Opportunity sites in the dashboard source:** `lhds2040-source/inputs/` held 28 October opportunity site files. The current one is `opportunity_sites/Limerick_Opportunity_Sites.gpkg` here.

## Working preferences

- **Writing:** plain, concise British English. No buzzwords.
- **Sources:** never invent quotations, figures, policy references or page numbers. Write "Source not verified" where a source can't be checked. Keep quoted text, policy interpretation and professional opinion distinct.
- **Accuracy comes first:**
  - check results against the files and say what was verified;
  - flag judgement calls (thresholds, densities, manual capacities) as such.
- **Never send email from the connected Gmail.**
- **Commits:** commit to the branch above with clear messages, and update the folder README with a dated note for any method change.

## Starting a new session

1. Read this file, then the README of each folder you'll touch.
2. Check the headline figures. If any differ, stop and report before changing anything:
   ```python
   import geopandas as gpd
   d = gpd.read_file('limerick_pipeline/register/Limerick_Developable_Land.gpkg', layer='developable_land')
   E = ['est_q4_2026', 'est_2027', 'est_2028', 'est_2029', 'est_2030', 'est_2031_plus']
   print(len(d), d.consented_units.sum(), d.under_construction_units.sum(), d.future_supply_units.sum(),
         round(d[E].sum().sum()), (d.future_supply_units - d.unconsented_capacity).sum())
   # expected: 452 10494.0 3885.0 25989.0 8106 8262.0
   ```
3. For anything involving the dashboards, read Dropbox `lhds2040-source/HANDOVER.md` too. The Dropbox files are the source of truth for the dashboard build.
