# M04_S06 — Excel Template Design

## Summary

Owner-driven checklist for building the Excel template that pairs with the agent-built population code (M04_S05). The agent populates four named tables with collection data; this story is everything else — the worksheets, pivot tables, charts, formulas, Power Query transformations, and visual design that turn raw data into a polished portfolio artifact.

This is a checklist, not an instruction manual. Use it to verify nothing important is missing before considering the template complete.

**Final file location:** `backend/assets/collection_template.xlsx`

---

## Worksheets

The agent's population code expects these four sheets to exist with these exact names:

- [ ] `Collection Details` — agent populates `collection_details` table here
- [ ] `Condition Multipliers` — agent populates `condition_multipliers` table here
- [ ] `Historic Prices` — agent populates `historic_prices` table here
- [ ] `Card Prices` — agent populates `card_prices_all_conditions` table here

Additional worksheets to design and populate manually:

- [ ] `Dashboard` — landing page with KPIs and headline charts
- [ ] `Cards Ranked` — full card list ranked by total value
- [ ] `Sets Ranked` — full set list ranked by total value with completion progress
- [ ] `Upgrade Cost` — the Excel-only upgrade cost analyzer
- [ ] `Price Trends` — historic price visualization

---

## Tables (ListObjects) — Agent-Populated

These four tables exist in the template with empty rows for the agent to populate. Do not delete them or rename them.

### `collection_details`

- [ ] `set_id`
- [ ] `set_name`
- [ ] `set_printed_total`
- [ ] `set_total_with_secrets`
- [ ] `card_id`
- [ ] `card_number`
- [ ] `card_name`
- [ ] `rarity`
- [ ] `supertype`
- [ ] `condition`
- [ ] `variant`
- [ ] `is_first_edition`
- [ ] `quantity`
- [ ] `purchase_price`
- [ ] `market_price`
- [ ] `total_value`
- [ ] `gain_dollar`
- [ ] `gain_percent`
- [ ] `pricing_warning`

### `condition_multipliers`

- [ ] `set_id`
- [ ] `set_name`
- [ ] `grouping_type`
- [ ] `grouping_value`
- [ ] `from_condition`
- [ ] `to_condition`
- [ ] `multiplier`
- [ ] `data_points`

### `historic_prices`

- [ ] `card_id`
- [ ] `card_name`
- [ ] `set_name`
- [ ] `condition`
- [ ] `sample_date`
- [ ] `market_price`

### `card_prices_all_conditions`

- [ ] `card_id`
- [ ] `card_name`
- [ ] `set_name`
- [ ] `condition`
- [ ] `market_price`

---

## Dashboard Sheet

A single landing page where the user lands first when opening the workbook. Should mirror the web dashboard's headline content while showing off Excel's strengths.

### KPIs

- [ ] Total Collection Value
- [ ] Total Card Count
- [ ] Most Valuable Card (per-card price, not total value — same definition as web dashboard)
- [ ] Lifetime Gain ($) — only show if any card has purchase price
- [ ] Lifetime Gain (%) — only show if any card has purchase price

### Charts

- [ ] Pie chart — value by set
- [ ] Variant counts bar chart (logarithmic, only show if non-standard variants exist)
- [ ] Treemap — Excel native treemap chart, set → card hierarchy. Bottom-10% grouping handled in Power Query before charting.
- [ ] Top gainers chart — vertical bar chart (parameterize 3 months default)
- [ ] Top losers chart — vertical bar chart (parameterize 3 months default)

### Slicers

Excel slicers connected to pivot tables driving the dashboard charts.

- [ ] Set
- [ ] Rarity
- [ ] Condition
- [ ] Variant (only show if non-standard variants exist)

---

## Cards Ranked Sheet

Full card listing ranked by total value descending. Power Query joins `collection_details` with current pricing data.

- [ ] Sortable/filterable table of all cards in the collection
- [ ] Columns include: rank, card name, set, condition, variant, 1st edition flag, quantity, market price, total value, purchase price, gain $, gain %, pricing warning
- [ ] Conditional formatting on gain columns (green for positive, red for negative)
- [ ] Visual indicator on rows with `pricing_warning = TRUE`

---

## Sets Ranked Sheet

Full set listing ranked by total value descending. Companion to the web dashboard's Sets Ranked table.

- [ ] Set name
- [ ] Cards owned (unique count)
- [ ] Set total (printed)
- [ ] Set total (with secret rares)
- [ ] Completion % (with toggle or separate columns for secret-rare-inclusive vs not)
- [ ] Total value
- [ ] Percentage of collection
- [ ] Visual progress bar via conditional formatting

---

## Upgrade Cost Sheet

The Excel-only feature — calculate the cost to upgrade portions of the collection to a target condition.

### Parameters (user-controlled)

- [ ] Target condition selector — dropdown (NM, LP, MP, HP)
- [ ] Pricing strategy selector — `Sell at Market` or `Full Replacement Cost`

### Logic

- [ ] For each card in the collection, identify whether it's at or above the target condition
- [ ] If below the target, calculate upgrade cost using `card_prices_all_conditions` join
- [ ] Fall back to `condition_multipliers` when target condition price is missing for a card
- [ ] Apply the chosen pricing strategy to determine final upgrade cost per card

### Output

- [ ] Per-card upgrade cost table with: card name, set, current condition, target condition, current value, target value, upgrade cost, source (actual price vs inferred from multiplier)
- [ ] Pivot table grouping upgrade costs by set
- [ ] Total upgrade cost summary at the top of the sheet
- [ ] Note explaining the methodology and that graded cards are excluded
- [ ] Visual indicator distinguishing actual prices from multiplier-inferred prices

---

## Price Trends Sheet

Visualization of the historic price data the agent populates.

- [ ] Line chart of total collection value over time (using `historic_prices` aggregated)
- [ ] Slicer to filter the chart by set
- [ ] Date axis using twice-monthly samples
- [ ] Pivot table backing the chart for transparency

---

## Power Query Queries

These should be set up to refresh from the agent-populated tables. The user clicks "Refresh All" after opening the file.

- [ ] Query loading from `collection_details` (the foundation for most other queries)
- [ ] Query loading from `condition_multipliers`
- [ ] Query loading from `historic_prices`
- [ ] Query loading from `card_prices_all_conditions`
- [ ] Aggregation query for set-level summaries
- [ ] Aggregation query for time-series collection value
- [ ] Upgrade cost calculation query joining collection details with prices and multipliers
- [ ] Bottom-10% grouping query for treemap pre-aggregation
- [ ] Variant aggregation query (handles comma-separated variant splitting and 1st Edition derivation)

---

## Visual Polish

Items that make the workbook feel finished rather than functional.

- [ ] Consistent color palette across all charts and conditional formatting (Magikarp red/gold theme to match the web dashboard, or a standard professional palette — your call)
- [ ] All sheets have a clean header row with a sheet title
- [ ] Currency formatting (`$#,##0.00`) applied to all monetary columns
- [ ] Percentage formatting applied to all percentage columns
- [ ] Date formatting consistent across all date columns
- [ ] Frozen header rows on all data sheets
- [ ] Hidden gridlines on the Dashboard sheet for a cleaner look
- [ ] Tab colors to group related sheets (e.g. agent-populated tabs in one color, calculated/visual tabs in another)
- [ ] Print-ready setup on key sheets (page breaks, print titles)
- [ ] Hyperlinks between sheets for navigation (e.g. Dashboard → Cards Ranked)

---

## Documentation

A small README-style sheet explaining the workbook to anyone opening it.

- [ ] `Read Me` sheet (or similar) at position 1
- [ ] Brief overview of what the workbook does
- [ ] Note that "Refresh All" must be clicked to populate data from the source tables
- [ ] List of sheets with one-line descriptions
- [ ] Note about the Upgrade Cost sheet methodology
- [ ] Note about graded cards being excluded from upgrade analysis
- [ ] Note about variant pricing being approximate (matches the web dashboard's pricing_warning concept)

---

## Final Validation

Before considering the template complete:

- [ ] Open the placeholder version of the file (with empty agent-populated tables) and confirm everything still functions without breaking
- [ ] Drop in a known-good populated workbook (from a successful agent run) and confirm Refresh All updates everything correctly
- [ ] Confirm pivot tables, charts, and Power Query queries don't get corrupted when the agent saves the file via openpyxl (this is the M04_S05 risk — coordinate testing with that story)
- [ ] Test with the mock collection data
- [ ] Test with a real collection upload
- [ ] Test with a small collection (1-5 cards) to ensure no charts break with sparse data
- [ ] Test with a large collection (200+ cards) to ensure no performance issues

---

## Out of Scope

These are NOT part of this story — leave them for future milestones:

- Mobile-friendly Excel layout (the workbook is designed for desktop Excel)
- Macros or VBA (keep it formulas/Power Query only)
- Connection to external data sources (the workbook is self-contained once populated)
- User-configurable themes or color palettes
- Advanced features like sparklines per row (unless they fit naturally)
