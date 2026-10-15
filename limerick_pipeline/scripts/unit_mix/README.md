# Unit mix from planning files

`planning_file_mix.csv` (repo root) holds bedroom mixes read from planning documents for large counted schemes where CIS and the register text gave none. `build_workbook.py` uses it before the CIS or register description, with the source "Planning file documents" and the document named in Mix Note.

Sources, in order of preference:
1. The council planner's report at decision: a unit-by-unit schedule or contributions schedule.
2. The schedule of accommodation or housing quality assessment submitted with the application.
3. An Bord Pleanála / An Coimisiún Pleanála inspector's report, which has a unit mix table, for appealed schemes and SHDs.

`eplan_docs.py` lists and fetches documents from the council's iDocs viewer; opening it means accepting the council's copyright notice. `ocr.py` OCRs scanned PDFs (tesseract). `one_mix.py <ref>` pulls the pre-decision planner's reports for one file and prints the lines that mention bedrooms. Every figure in the CSV was checked by reading the page; downloaded documents are not stored in the repo.

Two schemes have a different unit count in the documents than in the tracker, and the CSV notes this:
- 25/60653: 42 in the documents, 40 in the tracker.
- 18/1193: 49 in the documents, 58 in the tracker.

Older files (2018–2020) only have post-decision documents online, so most of them can't be resolved this way.
