# M04_S05 — Excel Workbook Population

## Summary

Build the backend infrastructure that populates an Excel template with a user's collection data. The agent reads a template `.xlsx` file from the repo, populates four named Excel tables with collection data, and returns the filled-in workbook as a download.

This story explicitly does NOT include the design or content of the template itself — that is owned by a separate, parallel story handled by the project owner. The agent's responsibility ends at populating the four tables. The template's pivot tables, charts, formulas, Power Query transformations, and visual design are all built outside this story.

The two stories are designed to be developable in parallel — neither blocks the other. Once the agent's story is complete, dropping a finished template into `backend/assets/collection_template.xlsx` is sufficient to make the export feature work end-to-end.

---

## ⚠ Critical Constraint — openpyxl Library Limitation

**This is the most likely thing to go wrong with this story. Read this section carefully and surface any issues immediately rather than working around them silently.**

`openpyxl` has known limitations when working with Excel workbooks that contain complex features like Power Query connections, pivot tables, and conditional formatting. The real template (built in the parallel owner story) WILL contain these features. There is a real risk that `openpyxl` corrupts or strips them when the workbook is saved.

**Required behavior:**

- Build and test against the placeholder template first (see Placeholder Template section below)
- When the real template is delivered, test population against it as a smoke test BEFORE assuming the implementation is complete
- If `openpyxl` corrupts Power Query connections, pivots, or charts after population: **STOP. Surface this as a blocker.** Do NOT:
  - Silently switch to a different library
  - Rewrite the template to avoid the corrupted features
  - Attempt manual XML manipulation as a workaround
  - Use `xlwings` (it requires Excel itself to be installed and does not work on Linux deployment targets)
- Instead: report the specific feature(s) being corrupted, confirm the issue with a minimal repro, and propose options. The project owner will decide whether to revisit the library choice in a follow-up story or restructure the template.

This is non-negotiable. Silently working around the limitation produces a downstream surprise that blocks the entire Excel feature without anyone realizing it. Flag it loudly.

---

## Dependencies

- M04_S02 (User Collection Upload) — provides the session collection data
- M04_S01 (Condition Multiplier Analysis) — provides the multiplier data referenced by one of the tables
- M03_S09 (Enhance Price Snapshot Ingestion) — provides the historic price data referenced by one of the tables
- The `total_with_secrets` schema fix from Milestone 3 — provides the set total denominator

---

## Architecture

### File Locations

- **Template:** `backend/assets/collection_template.xlsx`
  - Read-only — the agent never modifies the template directly
  - The template will be populated by the project owner outside this story
  - For development purposes, an empty placeholder template containing the four tables (with headers only, no data) should be created so the agent can test population
- **Output:** Generated in memory and returned as a file download — not persisted to disk

### High-level Flow

1. User clicks **Download Excel** on the collection dashboard
2. Frontend calls `GET /collection/excel`
3. Backend reads the user's session collection
4. Backend opens the template, populates the four tables, returns the file as an `.xlsx` download
5. The user opens the downloaded file and triggers Excel's "Refresh All" — Power Query and pivot tables refresh from the populated tables and the workbook is ready to use

The user must trigger refresh manually after opening — the agent does not refresh data, charts, or pivots inside the workbook.

---

## API Endpoint

```
GET /collection/excel
```

**Authentication:** Reads the session cookie established in M04_S02.

**Behavior:**

- If no active session, return 404 with a JSON body explaining the user needs to upload a collection first
- If session exists, generate the populated workbook and return as a binary `.xlsx` response
- `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `Content-Disposition: attachment; filename="collection-report-{YYYY-MM-DD}.xlsx"` where the date is today

**The endpoint always returns the user's full collection.** Slicer filter state from the URL is intentionally ignored — the user gets their entire collection in the workbook regardless of what's filtered on the dashboard. They can apply their own filters within Excel if they want a narrower view. This is by design: the Excel export is a portable copy of the full collection, not a snapshot of the current view.

---

## Frontend Changes

A `Download Excel` button on the Collection Dashboard. See the dashboard story (M04_S03) for placement details — the button lives in the page header area near the Most Valuable Card row. This story implements the endpoint the button calls; the button itself is added in the dashboard story.

While the download is generating (which may take a few seconds for large collections), the button shows a loading state. Disable it during generation to prevent multiple concurrent requests.

---

## Tables to Populate

The template contains four pre-defined Excel tables (ListObjects). The agent's responsibility is populating these with the correct data. The agent does NOT create the tables — it appends rows to existing empty tables.

### Table 1 — `collection_details` on `Collection Details` sheet

One row per card in the user's collection.

| Column | Type | Source |
|---|---|---|
| `set_id` | TEXT | Canonical set ID |
| `set_name` | TEXT | `sets.name` (display name) |
| `set_printed_total` | INT | `sets.printed_total` |
| `set_total_with_secrets` | INT | `sets.total_with_secrets` |
| `card_id` | TEXT | Canonical card ID |
| `card_number` | TEXT | `cards.number` |
| `card_name` | TEXT | `cards.name` |
| `rarity` | TEXT | `cards.rarity` |
| `supertype` | TEXT | `cards.supertype` |
| `condition` | TEXT | User-provided from upload |
| `variant` | TEXT | User-provided, normalized (Title Case with acronym preservation, blank for standard) |
| `is_first_edition` | BOOLEAN | User-provided (default FALSE if blank) |
| `quantity` | INT | User-provided |
| `purchase_price` | NUMERIC | User-provided, blank if not provided |
| `market_price` | NUMERIC | Most recent `price_snapshots.market_price` for the card at the user's condition |
| `total_value` | NUMERIC | `quantity × market_price` (computed by the agent) |
| `gain_dollar` | NUMERIC | `total_value - (quantity × purchase_price)`, blank if no purchase price |
| `gain_percent` | NUMERIC | `gain_dollar / (quantity × purchase_price)`, blank if no purchase price |
| `pricing_warning` | BOOLEAN | TRUE if the card has a non-standard variant (variant column non-blank) — signals that pricing may be approximate |

**Notes for the agent:**

- `market_price` is fetched from the most recent snapshot matching the card and the user's condition. If no snapshot exists for that exact condition, fall back to NM market price for the same card. Set `pricing_warning` to TRUE when a fallback occurs OR when the user has a non-standard variant.
- `purchase_price`, `gain_dollar`, and `gain_percent` should be left as empty cells (not zeros) when no purchase price was provided. Empty cells let Excel formulas distinguish "not provided" from "zero gain."
- Boolean columns should be written as actual TRUE/FALSE values, not as strings.

### Table 2 — `condition_multipliers` on `Condition Multipliers` sheet

The condition multiplier data filtered to only the sets present in the user's collection.

Source: the `condition_multipliers` table from M04_S01.

| Column | Type | Source |
|---|---|---|
| `set_id` | TEXT | `condition_multipliers.set_id` |
| `set_name` | TEXT | Joined from `sets.name` |
| `grouping_type` | TEXT | `condition_multipliers.grouping_type` (`rarity` or `supertype`) |
| `grouping_value` | TEXT | `condition_multipliers.grouping_value` |
| `from_condition` | TEXT | `condition_multipliers.from_condition` |
| `to_condition` | TEXT | `condition_multipliers.to_condition` |
| `multiplier` | NUMERIC | `condition_multipliers.multiplier` |
| `data_points` | INT | `condition_multipliers.data_points` |

**Notes for the agent:**

- Filter to sets the user actually owns (`set_id IN <user's sets>`). Skip sets with no multiplier data — don't write empty rows.
- Both `grouping_type` values (rarity AND supertype) should be included for each set so Power Query can choose either grouping.

### Table 3 — `historic_prices` on `Historic Prices` sheet

For each card the user owns at a raw condition, twice-monthly historic price snapshots over the last 6 months.

| Column | Type | Source |
|---|---|---|
| `card_id` | TEXT | Card ID |
| `card_name` | TEXT | Joined from `cards.name` for Power Query convenience |
| `set_name` | TEXT | Joined from `sets.name` for Power Query convenience |
| `condition` | TEXT | The user's actual condition for this card |
| `sample_date` | DATE | Either the 1st or the 15th of a month |
| `market_price` | NUMERIC | Price snapshot closest to (but not after) the sample_date |

**Sampling logic:**

- For each card in the collection at a raw condition (NM, LP, MP, HP, DMG), generate sample dates: the 1st and 15th of each month for the past 6 months
- For each sample date, find the most recent `price_snapshots.market_price` for that card and condition where `captured_date <= sample_date`
- If no snapshot exists at or before the sample date, skip that row (do not insert null)
- This produces up to 12 rows per card (2 samples × 6 months)

**Notes for the agent:**

- Only include cards where `condition` is one of `NM`, `LP`, `MP`, `HP`, `DMG`. Skip graded conditions and any unrecognized conditions.
- Only include the user's actual condition per card — do not include other conditions even if data is available.

### Table 4 — `card_prices_all_conditions` on `Card Prices` sheet

For each card the user owns at a raw condition, the current market price at every condition above their current condition. Used by Power Query to power the upgrade cost analyzer.

| Column | Type | Source |
|---|---|---|
| `card_id` | TEXT | Card ID |
| `card_name` | TEXT | Denormalized for Power Query convenience |
| `set_name` | TEXT | Denormalized for Power Query convenience |
| `condition` | TEXT | An upgrade target condition (NM, LP, MP, HP) |
| `market_price` | NUMERIC | Most recent market price for the card at this condition |

**Inclusion rules:**

For each card in the user's collection:

- If the card is at a graded condition (PSA-*, BGS-*, CGC-*) → no rows
- If the card is at an unrecognized condition → no rows
- If the card is at NM → no rows (already at top of ladder)
- If the card is at a raw condition below NM → one row per condition above the user's current condition that has price data:

| User's condition | Conditions to include rows for |
|---|---|
| DMG | HP, MP, LP, NM |
| HP | MP, LP, NM |
| MP | LP, NM |
| LP | NM |

If a target condition has no price snapshot in the database, skip that row entirely (do not write null prices). Power Query treats missing rows as "no data" and falls back to the condition multiplier table.

---

## Implementation Notes

### Library

Use `openpyxl`. It supports:
- Reading existing `.xlsx` templates
- Appending rows to existing ListObjects (Excel tables) by their name
- Preserving Power Query connections, pivot tables, and chart references in the template

See the Critical Constraint section at the top of this doc for the limitations and the required handling if those limitations are hit.

### Population Pattern

For each of the four tables:

1. Open the template
2. Locate the table by name on its sheet
3. Clear any existing data rows (preserve the header row)
4. Append new rows from the database
5. Update the table's range reference to match the new row count

The `openpyxl` `Worksheet.tables` dictionary provides access to ListObjects by name. Updating the table's `ref` attribute extends or shrinks its range.

### Avoiding Template Corruption

To minimize the risk described in the Critical Constraint section:

- Open the template with `openpyxl.load_workbook(..., keep_vba=False, keep_links=True)`
- Save with `workbook.save(buffer)` to a `BytesIO` buffer rather than writing to disk
- Do not attempt to refresh data connections, evaluate formulas, or modify charts programmatically
- Test with a known-good template before deploying

### Performance Considerations

A 200-card collection with full historic data may produce around 2,400 rows in `historic_prices` plus 800 rows in `card_prices_all_conditions` plus the ~200 in `collection_details` plus maybe 500 in `condition_multipliers`. That's roughly 4,000 rows total — well within `openpyxl`'s comfortable range. No streaming or chunking is needed for typical collection sizes.

For large collections (1,000+ cards) the response may take several seconds. Acceptable for this story but worth noting for future optimization.

---

## Placeholder Template

The agent must create a basic placeholder template at `backend/assets/collection_template.xlsx` so testing can proceed without waiting for the real template. The placeholder should contain:

- Four worksheets with the names listed above
- Four ListObjects with the names and column headers listed above
- No formatting, no charts, no pivots, no Power Query
- A simple chart on a fifth sheet showing total_value by set_name from the `collection_details` table — purely to validate that data refreshes work end-to-end

This placeholder is replaced by the real template later. The agent should NOT attempt to design the placeholder for end-user use — it is purely a development aid.

---

## Test Cases

---

### TC01 — Endpoint returns 404 without active session

**Steps:**
1. Without a session cookie, hit `GET /collection/excel`

**Expected:** 404 response with a JSON body explaining a collection must be uploaded first.

---

### TC02 — Endpoint returns workbook with active session

**Steps:**
1. Upload the mock collection
2. Hit `GET /collection/excel`

**Expected:** Binary `.xlsx` response. Filename matches `collection-report-YYYY-MM-DD.xlsx`. Content-Type is the Excel MIME type.

---

### TC03 — `collection_details` table populated correctly

**Steps:** Open the downloaded workbook. Navigate to the Collection Details sheet.

**Expected:** The `collection_details` table contains one row per card in the mock collection. All columns are populated correctly. `total_value` matches `quantity × market_price` for each row.

---

### TC04 — Boolean columns are real booleans

**Steps:** In the downloaded workbook, click a cell in the `is_first_edition` or `pricing_warning` column.

**Expected:** Excel recognizes the cell as a boolean value (formulas like `=AND(is_first_edition, ...)` work). The cells display `TRUE` or `FALSE`, not the strings `"TRUE"` or `"FALSE"`.

---

### TC05 — Empty cells for missing purchase price

**Steps:** Inspect rows in `collection_details` for cards without a purchase price.

**Expected:** `purchase_price`, `gain_dollar`, and `gain_percent` are empty cells (not zeros, not text). `ISBLANK()` returns TRUE for these cells.

---

### TC06 — `condition_multipliers` filtered to user's sets

**Steps:** Upload a mock collection with only Base Set cards. Open the downloaded workbook's Condition Multipliers sheet.

**Expected:** All rows have `set_id = 'base1'`. No rows for Jungle, Fossil, or other sets the user doesn't own.

---

### TC07 — Historic prices have twice-monthly samples

**Steps:** Open the Historic Prices sheet for a single card.

**Expected:** Sample dates are exclusively the 1st or 15th of a month. Up to 12 rows per card over a 6-month window.

---

### TC08 — Historic prices skip missing data

**Steps:** Pick a card that was added to the database recently (less than 6 months ago).

**Expected:** Only sample dates after the card's earliest snapshot have rows. No rows with null market_price.

---

### TC09 — `card_prices_all_conditions` excludes graded cards

**Steps:** Upload a collection containing at least one PSA-graded card. Open the Card Prices sheet.

**Expected:** No rows for the graded card. Only raw cards have rows in this table.

---

### TC10 — `card_prices_all_conditions` includes only upgrade conditions

**Steps:** Pick a card the user owns at LP. Filter the Card Prices sheet to that card.

**Expected:** Exactly one row with `condition = NM`. No rows for LP, MP, HP, or DMG (LP is the user's current condition; MP/HP/DMG are below it; NM is above).

---

### TC11 — `card_prices_all_conditions` empty for NM cards

**Steps:** Pick a card the user owns at NM.

**Expected:** Zero rows for that card in the Card Prices sheet.

---

### TC12 — Filter state ignored

**Steps:** Apply slicer filters on the dashboard so only Base Set cards are visible. Click Download Excel.

**Expected:** The downloaded workbook contains the user's FULL collection — including cards from sets that were filtered out on the dashboard. The Excel export is independent of dashboard filter state.

---

### TC13 — Download button on dashboard

**Steps:** With a loaded collection, click the Download Excel button on the dashboard.

**Expected:** Download begins. Button shows a loading state during generation. After download completes, button returns to normal state.

---

### TC14 — Template structure preserved

**Steps:** Compare the worksheet structure of the downloaded workbook to the template.

**Expected:** Same number of sheets, same sheet names, same table names. No data or sheets have been added or removed by the population process.

---

### TC15 — Pricing warning set for variant cards

**Steps:** Upload a collection containing a card with a non-blank variant. Inspect the `pricing_warning` column for that row.

**Expected:** `pricing_warning` is TRUE for the variant card, FALSE for cards without variants.

---

## Notes for the Agent

**The template is replaced post-implementation.** Build the placeholder template with the bare minimum to support testing. Do not invest time in styling, formulas, or design — that work is owned by a separate, parallel story. As long as the four named tables exist with correct headers, the population code can be developed and tested.

**Don't refresh the workbook programmatically.** The user triggers Refresh All in Excel after opening the file. Attempting to refresh from Python typically requires Excel itself to be installed (xlwings) or specialized libraries that are unreliable on Linux servers. Trust the user to refresh.

**Read the Critical Constraint section at the top of this document.** The `openpyxl` corruption risk is real and the required behavior is non-negotiable. If `openpyxl` fails to preserve the real template's features after population, surface the issue immediately and propose options. Do not silently work around it.

**The endpoint ignores filter state.** The user always gets their full collection regardless of dashboard slicers. They can filter inside Excel if they want a narrower view.
