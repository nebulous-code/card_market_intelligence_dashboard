# M04_S06 — Phased Work Breakdown

Companion to `M04_S06-ExcelTemplateDesign.md`. That file is the 252-line checklist; this file slices it into 6 dependency-ordered sessions sized to ~1-3 hours each, in the order they should be tackled.

About 70% of the work funnels through Power Query. Once that's solid the sheets fall out fast — so the early sessions are about de-risking the foundation, not building the visible polish.

---

## Session 1 — De-risk first (30-60 min)

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

## Session 2 — Power Query foundation (1-2 hrs)

All four base queries, no charts yet. Each is just `Excel.CurrentWorkbook(){[Name="..."]}[Content]` with column type fixes.

- [ ] `qCollection` from `collection_details`
- [ ] `qMultipliers` from `condition_multipliers`
- [ ] `qHistoric` from `historic_prices`
- [ ] `qPrices` from `card_prices_all_conditions`

**Done when:** all four show up in Queries & Connections and refresh without errors.

---

## Session 3 — Cards Ranked + Sets Ranked (1-2 hrs)

Easiest sheets — pure tabular output. Builds confidence and tests your PQ.

- **Cards Ranked:** load `qCollection` sorted by `total_value` desc + conditional formatting on gain columns + warning indicator on rows with `pricing_warning = TRUE`.
- **Sets Ranked:** a `Table.Group` aggregation on `qCollection` (count, sum, completion %) + a databar on completion.

**Done when:** both sheets render correctly with mock data.

---

## Session 4 — Dashboard (2-3 hrs) — the showcase sheet

The biggest single deliverable. Order matters:

1. Pivot tables backing each chart (set-value, variant counts, gainers, losers).
2. KPI cells (formulas off the pivots or off `qCollection`).
3. Charts on top of pivots: pie, bar, treemap, gainers/losers.
4. Slicers wired to pivots (Set, Rarity, Condition, optionally Variant).
5. Clean it up: hide gridlines, theme colors.

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
- Debugging the openpyxl save in `api/services/collection_excel.py` if Session 1 surfaces issues.

---

## How to use this doc

You don't need to know what "done" looks like — you need to know what the next 90 minutes looks like. Start with Session 1; don't plan past it until you know whether the round-trip works.
