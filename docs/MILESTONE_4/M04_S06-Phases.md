# M04_S06 — Phased Work Breakdown

Companion to `M04_S06-ExcelTemplateDesign.md`. That file is the 252-line checklist; this file slices it into 6 dependency-ordered sessions sized to ~1-3 hours each, in the order they should be tackled.

About 70% of the work funnels through Power Query. Once that's solid the sheets fall out fast — so the early sessions are about de-risking the foundation, not building the visible polish.

---

## Session 1 — De-risk first (30-60 min) — DONE

The round-trip failed on the original openpyxl-based export and was fixed rather than worked around. openpyxl rebuilds the `.xlsx` ZIP from its in-memory model on save and silently drops every part it doesn't model, including the `customXml` part where Power Query lives. Commit `4c4cf7b` replaced it with `api/services/xlsx_patcher.py`, which edits the ZIP in place: it finds each Table by `displayName`, rewrites only that sheet's `<sheetData>` and the Table's `ref`, and copies all other parts through byte-for-byte.

Validated: patching all four data tables leaves the three `customXml` parts, `xl/connections.xml`, and `xl/queryTables/queryTable1.xml` byte-identical, with no parts lost or added. Power Query, slicers, pivots, and charts are all safe across export.

Consequence for the build: `api/assets/collection_template.xlsx` is the source of truth and can hold all your queries and design work. Build in it directly and commit as you go. See `M04_S06-BuildSteps.md` for the workflow.

The biggest unknown is whether openpyxl's save in S05 corrupts pivots, Power Query, or charts on round-trip. Find out *before* building anything fancy on top.

- Open `api/assets/collection_template.xlsx` (the placeholder).
- Add **one** Power Query loading from the `collection_details` table → Close & Load to a new sheet.
- Save.
- Upload it via `POST /collection/mock` → `GET /collection/excel` to get the populated copy.
- Open the populated copy → click **Refresh All**.
- Does the query refresh cleanly? Does the file open without "we found a problem with some content"?

If **yes** → cleared to build the rest with confidence.
If **no** → foundation problem to solve before anything else. The likely culprit is openpyxl save settings in `api/services/collection_excel.py`.

---

## Session 2 — Power Query foundation (1-2 hrs) — DONE

All four base queries, no charts yet. Each is just `Excel.CurrentWorkbook(){[Name="..."]}[Content]` with explicit column type fixes, loaded as "Connection only".

- [x] `qCollection` from `collection_details` — 19 typed columns
- [x] `qPrices` from `card_prices_all_conditions` — 5 typed columns
- [x] `qMultipliers` from `condition_multipliers` — 8 typed columns
- [x] `qHistoric` from `historic_prices` — 6 typed columns

Full M-code for all four is in `M04_S06-BuildSteps.md`.

The Session 1 smoke-test query and its leftover "Test Query" output sheet were removed. The workbook is now exactly four sheets and four tables matching the four backend tables.

Validated by decoding the stored `DataMashup` blob and round-tripping the file through `patch_tables`: all four queries present with the right source table and column count, `qHistoric.sample_date` typed `type date`, `qMultipliers.multiplier` typed `type number`, and every Power Query part byte-identical after export with no parts lost or added.

Confirmed by hand: all four refresh cleanly in a workbook downloaded from the running app, so they evaluate correctly against real populated data and not just in the stored M code.

### The external data source warning is expected

Excel warns on open that the workbook connects to an external data source. It does not. All four queries read tables inside the file via `Excel.CurrentWorkbook()`, and every connection string reads `Data Source=$Workbook$`. Checked for `Web.Contents`, `OData.Feed`, `Sql.Database`, `Odbc`, `File.Contents`, `Folder.Files` and others — none are present.

The warning fires because Excel routes all Power Query through an OLE DB provider, so each query registers in `xl/connections.xml` as `type="5"` (OLEDB). The Trust Center flags any OLEDB connection without inspecting whether it actually leaves the file, so every Power Query workbook triggers it. It cannot be suppressed from inside the file — it is a client-side Trust Center decision. Session 6's Read Me sheet should explain it, since a hiring manager opening the workbook will see the warning before anything else.

---

## Session 3 — Cards Ranked + Sets Ranked (1-2 hrs) — DONE

Easiest sheets — pure tabular output. Builds confidence and tests your PQ.

- [x] **Cards Ranked:** `qCardsRanked` loads `qCollection` sorted by `total_value` desc, with red-white-green color scales on both gain columns and a `containsText` warning rule on `pricing_warning`.
- [x] **Sets Ranked:** `qSetsRanked` is a `Table.Group` on `qCollection` giving distinct cards owned, total quantity, total value and completion percent, with a databar on completion.

Both tabs renamed off their Power Query defaults. Validated: the queries are stored correctly, the databar bounds are pinned rather than automatic, and both sheets and tables survive the export untouched while the patcher rewrites only its four data tables. The internal table numbering shifted twice across this session as sheets were added, confirming the patcher resolves targets by `displayName` rather than file position.

### The databar bounds must be pinned, not automatic

Completion percent uses explicit `0` and `1` bounds. Left on Automatic, Excel scales bars to whatever range the data happens to contain, so a collection whose best set is 40% complete renders a full bar at 40% — which reads as finished. Pinning the bounds makes a bar mean the same thing in every workbook regardless of whose collection it is.

Completion is measured against `set_printed_total`, while cards owned counts distinct `card_id` including secret rares numbered beyond that total. Owning secrets can therefore push a set past 100%, which is correct and worth showing; with the bounds pinned those simply render as a full bar. `set_total_with_secrets` is aggregated in the query but not displayed, in case that denominator is preferred later.

### Mock collection covers the duplicate-card case

`qSetsRanked` counts `List.Count(List.Distinct([card_id]))` rather than rows, because the same card appears once per condition and variant owned. A playset held in three conditions is three rows but one card toward set completion.

The original mock collection could not exercise this: 20 rows, 20 unique cards, every quantity 1, so row count, distinct cards, and total quantity were identical everywhere. The distinction was invisible both to testing and to anyone evaluating the workbook. Three duplicate-card rows and one quantity bump were added, giving each set a different combination:

| set | rows | unique cards | total quantity | shows |
| --- | --- | --- | --- | --- |
| Base Set | 6 | 5 | 7 | duplicate and quantity above one |
| Jungle | 6 | 5 | 6 | duplicate only |
| Fossil | 6 | 5 | 6 | duplicate only |
| 151 | 5 | 5 | 7 | quantity above one, no duplicate |

Validated by uploading the edited fixture to a running API: it passes validation, and `base1-4`, `base2-3` and `base3-5` each come back twice at different conditions. `POST /collection/mock` now reports 26 cards across 4 sets from 23 rows, so the card-count KPI also differs from the row count.

**Done when:** both sheets render correctly with mock data.

---

## Session 4 — Dashboard (2-3 hrs) — the showcase sheet — IN PROGRESS

The biggest single deliverable. Order matters:

1. [x] Pivot tables backing each chart (set-value, variant counts, gainers, losers).
2. [ ] KPI cells (formulas off the pivots or off `qCollection`).
3. [x] Charts on top of pivots: pie, bar, gainers/losers.
4. [~] Slicers wired to pivots — `set_name` done and driving all four pivots; Rarity, Condition and optionally Variant still to add.
5. [ ] Clean it up: hide gridlines, hide working sheets, theme colors.

The theme is applied: `Card Market Dashboard`, accent `E8412A`, Aptos Display / Aptos. See the theme packaging note below.

All four pivots share a single `pivotCacheDefinition`, which is what lets one slicer drive every chart. New pivots must be made by **copying an existing pivot**, never Insert -> PivotTable: a fresh insert builds its own cache and a slicer silently fails to reach it.

### Treemap is deliberately not in the Excel build

Excel cannot build a treemap (or sunburst, histogram, box-and-whisker, waterfall, funnel) from a PivotTable — only classic chart types work with pivots. A static treemap from a helper table would ignore the slicers, and a dead chart sitting among live ones reads as broken rather than intentional. Decision: let the web app own the treemap. The two artifacts are not required to reach feature parity in either direction; the workbook has Upgrade Cost, which the site does not.

### Outstanding issues

- **Top Gainers / Top Losers plot two series on one value axis.** `gain_dollar` spans roughly plus or minus 320 while `gain_percent` reaches 39.5 (3947%), so the percent bars are drawn but visually flat. The percent series needs a secondary axis. Note that a bar-plus-line combo is not available here: Excel will not combine a horizontal bar series with a line series, so both stay bars on separate axes, and the two axes need distinguishing colors or titles so a reader does not assume one scale.
- **`refreshOnLoad` is not set on `qCollection`.** Five of six connections have it. `qCollection` feeds `tData`, which backs every pivot, so on open the ranked sheets refresh while the dashboard quietly does not.

**Done when:** clicking a slicer updates all dashboard charts together.

---

## Session 5 — Upgrade Cost (2-3 hrs) — the Excel-only feature

The most complex sheet but contained — leave it for when you have momentum from Session 4.

- Two parameter cells with data-validation dropdowns (target condition, pricing strategy).
- A PQ query that joins `qCollection` → `qPrices` on target condition → falls back to `qMultipliers` when missing.
- Output table + a "source" column (actual vs inferred).
- Pivot grouping by set + total at top.

**Done when:** changing the target dropdown updates the upgrade cost total.

---

## Session 6 — Price Trends + polish + Read Me + final validation (1-2 hrs)

The "ship it" session.

- **Price Trends:** line chart from `qHistoric` aggregated → set slicer.
- **Polish pass:** currency/percent/date formatting, frozen headers, tab colors, hyperlinks between sheets.
- **Read Me sheet** (8 lines is plenty).
- Run the final validation list at the bottom of the spec.
- Drop the file at `api/assets/collection_template.xlsx`.

---

## Where Claude can help

Claude can't open the `.xlsx`, but can produce:

- **Power Query M-code** for any of these queries — especially the bottom-10% treemap grouping, the upgrade-cost join with multiplier fallback, and the variant-token splitter (these are non-trivial).
- **DAX or Excel formulas** for KPIs (e.g., the "only show if any card has purchase price" gates).
- **Conditional-formatting rules** for the gain columns, warning indicator, completion databar.
- **Inspecting the saved `.xlsx` directly** — Claude can unzip the workbook, decode the `DataMashup` blob to list the queries actually stored in it, and run the template through `patch_tables` to confirm nothing is dropped on export. Useful as a fast check after saving, without needing a deploy.
- Debugging `api/services/xlsx_patcher.py` if a future part (slicer, pivot cache, chart) turns out not to survive export.

---

## How to use this doc

You don't need to know what "done" looks like — you need to know what the next 90 minutes looks like. Start with Session 1; don't plan past it until you know whether the round-trip works.
