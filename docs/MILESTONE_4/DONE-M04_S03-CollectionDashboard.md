# M04_S03 — Collection Dashboard

## Summary

Build the dashboard view that renders after a successful collection upload or mock collection load. This story covers the page layout, KPIs, all five charts, both detail tables, the empty state redirect, the reset collection action, and filter state scaffolding that will be wired up in M04_S04 (Slicers).

The variant treatment across the dashboard (variant counts chart and variant slicer behavior) is **blocked pending PPT parser testing** — the variant chart is included in this story as a placeholder that hides itself if no non-standard variants exist, with full variant logic deferred until the parser behavior is confirmed.

---

## Dependencies

- M04_S02 (User Collection Upload) must be complete — this story consumes the session storage and parsed collection data established there
- M04_S01 (Condition Multiplier Analysis) is not strictly required for this story but its existence is assumed for future Excel work
- The `total_with_secrets` schema fix should be done before this story (called out as a Milestone 3 cleanup task)

---

## Route

- **Path:** `/collection/dashboard`
- **File:** `frontend/src/views/CollectionDashboardView.vue`
- **Breadcrumb:** `Analyze Your Collection › Collection Dashboard`
- **Sidebar nav:** Update the "Analyze Your Collection" nav item to use `mdi-book-search` instead of the folder-account icon previously specified in M04_S02

---

## Empty State

If a user navigates to `/collection/dashboard` without an active session (no session cookie, expired session, or session not found), redirect to `/collection` with a message displayed at the top of the upload page:

> **No collection loaded yet** — upload your collection or use the mock collection to get started.

The message should appear in a subtle info banner above the three action cards, not as a modal or alert. It clears once the user successfully loads a collection.

---

## Filter State Scaffolding

This story establishes the filter state architecture but does not build the UI to control it. All charts and tables consume from a shared reactive filter state object that defaults to "all selected" for every dimension.

### Filter state shape

```javascript
const filterState = reactive({
  sets:       new Set(),    // empty = all selected
  rarities:   new Set(),    // empty = all selected
  conditions: new Set(),    // empty = all selected
  variants:   new Set(),    // empty = all selected
})
```

Convention: an empty Set means "no filter applied" (all values pass). When the slicer panel is built in M04_S04, it populates these Sets based on user selections.

### Filtered collection computed property

A single computed property `filteredCollection` derives the visible cards from the full session collection by applying the filter state:

```javascript
const filteredCollection = computed(() => {
  return session.collection.filter(card => {
    if (filterState.sets.size > 0 && !filterState.sets.has(card.set_id)) return false
    if (filterState.rarities.size > 0 && !filterState.rarities.has(card.rarity)) return false
    if (filterState.conditions.size > 0 && !filterState.conditions.has(card.condition)) return false
    if (filterState.variants.size > 0 && !filterState.variants.has(card.variant ?? 'Standard')) return false
    return true
  })
})
```

Every chart and table in this story reads from `filteredCollection`, never from the raw session data. This is what makes filter state work transparently when the slicer story comes online — no chart changes are needed, the slicer just populates the Sets and everything updates reactively.

### URL persistence

Filter state syncs to URL query parameters using the same pattern from M03_S06. Format:

- `?sets=base1,jungle`
- `?rarities=Rare+Holo,Rare`
- `?conditions=NM,LP`
- `?variants=Standard,Reverse+Holo`

For Milestone 4, only the dashboard reads these URL params on mount and writes back when state changes. The slicer panel UI (M04_S04) will be the user-facing way to modify them.

---

## Page Layout

The dashboard is a single scrolling page. Top to bottom:

1. Page header (title + Download Excel button)
2. KPI strip (numeric KPIs in primary row + most valuable card name in secondary row)
3. Treemap
4. Pie chart and variant chart row (50/50 split when both visible; pie takes full width when variant chart is hidden)
5. Price over time chart (full width)
6. Gainers and losers (50/50 split)
7. Top 10 cards by value table (collapsible)
8. Sets ranked by value table (collapsible)

The "Reset Collection" action lives in the top-right corner of the Sets Ranked by Value table for visual consistency with the existing pattern.

---

## Page Header

A single row at the top of the dashboard above the KPI strip:

- **Left:** page title `Collection Dashboard`
- **Right:** `Download Excel` button

### Download Excel Button

A primary-styled button with `mdi-microsoft-excel` (or `mdi-file-excel-outline`) icon and the label `Download Excel`.

**Behavior:**

- Clicking the button initiates a download from `GET /collection/excel`
- While the request is in flight, show a loading state on the button (e.g. `Generating...` with a spinner) and disable further clicks
- The download returns the user's full collection regardless of any active slicer filters — this is intentional; users can filter within Excel if they want a narrower view
- The endpoint itself is implemented in M04_S05. For this story, the button can be implemented and wired to call the endpoint — if the endpoint isn't yet available, calling it will return an error which is acceptable for now (the button itself works correctly when the endpoint comes online)

If the user has no active session somehow (edge case — they should already be redirected away from this view), the button shows an error toast: "Please load a collection before downloading."

---

## KPI Strip

Two rows.

### Primary row — numeric KPIs

Either 2 or 4 cards depending on whether the user provided purchase prices. Cards are arranged horizontally with equal widths.

| KPI | Always shown? | Format |
|---|---|---|
| Total Collection Value | Yes | Currency, e.g. `$12,450.99` |
| Total Card Count | Yes | Number with thousand separators, e.g. `387 cards` |
| Lifetime Gain ($) | Only if at least one card has purchase price | Currency with sign, e.g. `+$1,240.50` or `-$432.00` |
| Lifetime Gain (%) | Only if at least one card has purchase price | Percentage with sign, e.g. `+12.4%` or `-8.7%` |

For the gain KPIs, the calculation is across cards that have a purchase price only — cards without purchase price are excluded from the gain numerator and denominator.

### Secondary row — most valuable card

A single thinner row across the full width showing:

> **Most Valuable Card:** Charizard (Base Set 4/102, NM) — $399.99

**Definition of "most valuable":** the card with the highest individual `market_price` (per-card value). NOT `quantity × market_price`. If a user has 3 copies of a $20 card and one copy of a $59 card, the $59 card is shown — not the $20 card.

**Tie-breaking:** If multiple cards tie for highest market price, pick deterministically by card_id alphabetically.

The card name is a link to the card detail page with `?from=collection`. The text uses the existing label/value pattern from other parts of the app — bold label, regular value.

---

## Treemap

See M04 design conversation for the full spec. Implementation specifics:

- **Hierarchy:** Set → Card (two levels)
- **Sizing:** Each card rectangle = `quantity × current market price`
- **Colors:** Each set uses a color from the `palette_colors` table (created in this story — see Database Changes below). Cards within a set share the parent's color via a transparent fill with a solid outline.
- **Bottom 10% grouping:** Cards making up the bottom 10% of a set's total value are consolidated into a single "Other (N cards)" rectangle. The 10% threshold is a constant in the chart component code. Grouping only applies if the set has 5+ cards AND grouping consolidates at least 3 of them.
- **Other rectangle:** Same color as parent set with a slightly muted fill
- **Layout:** Natural placement by the treemap algorithm
- **Labels:** Set name on each region (always); card name on rectangles large enough to fit; "Other (N cards)" on grouped rectangles when it fits
- **Hover:**
  - Card rectangle → card name, set, quantity, market price, total value, percentage of collection
  - Other group → number of cards grouped, combined total value, highest-value card in the group
  - Set region (empty space) → set name, total value, percentage of collection, number of cards
- **Click:** Card rectangles navigate to `/cards/:cardId?from=collection`. Other rectangles and set regions have no click action.
- **Library:** `vue3-treemap-chart` or D3-based treemap. Agent picks based on Vue 3 / Vite compatibility.

---

## Pie Chart — Value by Set

- **Slices:** One per set, sized by `sum(quantity × market_price)` for cards in that set
- **Colors:** Distinct color per set from the `palette_colors` table
- **On-slice label:** Percentage only, shown on slices large enough to fit
- **Legend:** Beside the chart with color square + set name
- **Hover tooltip:** Set name, total value, percentage of collection, number of cards from that set
- **Library:** Chart.js via vue-chartjs

### Layout interaction with variant chart

When the variant chart is visible, this chart and the variant chart split the row 50/50. When the variant chart is hidden (no non-standard variants in the collection), this chart takes the full row width.

---

## Variant Counts Bar Chart

**Status:** Implemented in this story but variant treatment is **blocked pending PPT parser testing**. For now, treat the chart as a placeholder that shows nothing meaningful — the variant column from the upload is captured but normalization is deferred. The chart logic should:

- Read `card.variant` and `card.is_first_edition` from the session collection
- If `card.variant` is set OR `card.is_first_edition` is true, count the card toward those categories
- Show the chart only if there are non-standard variants (`card.variant` is set OR `is_first_edition` is true) on at least one card

The full variant chart spec is documented but the implementation should be conservative until the parser story is complete:

- **Bars:** One per non-standard variant present in the collection. Standard cards excluded.
- **Bar length:** Total quantity (each card contributes its quantity to every variant it matches when comma-separated)
- **Sort:** Quantity descending
- **X axis:** Logarithmic scale, count of cards
- **Color:** Magikarp gold (`#F5C842`)
- **Hover:** Variant name, total quantity, number of unique cards
- **Empty state:** Hide the chart entirely if no non-standard variants exist

---

## Price Over Time Chart

- **Y axis:** Total collection value in USD, formatted as compact currency
- **X axis:** Dates, formatted by window length (`Mar 15` for short windows, `Mar 2026` for longer)
- **Time window selector:** Preset buttons — `7D / 30D / 90D / 6M / All`. A preset is disabled if the collection's price history doesn't extend that far back.
- **Default window:** `30D`, or the largest available preset if 30 days of data doesn't exist yet
- **Line styling:** Magikarp red, with a filled area underneath fading to transparent
- **Data calculation:** For each date in the window, sum `quantity × market_price` across all cards in `filteredCollection`. Use Last Observation Carried Forward — if a card has no snapshot on a given date, use the most recent prior snapshot; if no prior snapshot exists, use the earliest available snapshot for that card.
- **Hover tooltip:** Date, total collection value on that date, change in dollars since the start of the visible window (e.g. `+$245 since Mar 15`)
- **Library:** Chart.js via vue-chartjs

The time scale selector controls both this chart AND the gainers/losers section below it. The selector lives above this chart with a footnote on the gainers/losers section: `Time window controlled by the selector above.`

---

## Gainers and Losers

Two vertical bar charts side by side. Gainers on the left, losers on the right.

### Layout

- 50/50 width split
- Both charts share the same Y axis percentage scale so visual heights are directly comparable
- Above the dual chart on the right side: count selector buttons (`3 / 5 / 10 / 20`), default `5`
- Below the charts: footnote `Time window controlled by the selector above.`
- Below the footnote: insufficient data note (only when applicable)

### Sort order and direction

- **Gainers chart:** Sort by percentage descending. Tallest bar (biggest gain) on the left side of the chart, shortest visible bar on the right.
- **Losers chart:** Sort by absolute percentage descending. Tallest bar (largest loss in magnitude) on the left, shortest on the right. Bars display the negative percentage value (e.g. `-23%`) but their visual height represents the magnitude.

### Bar styling

- **Gainers:** Green from the design palette doc (designer's specific shade)
- **Losers:** Red from the design palette doc (designer's specific shade — the same Magikarp red used elsewhere is a fallback)
- **Percentage label:** Inside the bar near the Y axis end. If the bar is too small to fit the label inside, place it outside the bar.

### Minimum movement filter

Cards with absolute percentage movement below 5% are excluded entirely. The 5% threshold is a backend constant adjustable in code, not user-facing.

### Insufficient data note

Show the note only when there's a shortfall in either chart. Wording examples:

- Both charts short: `Showing 3 gainers and 4 losers. Your collection has fewer cards moving more than 5% in this window.`
- Only gainers short: `Showing 3 gainers. Your collection has fewer than 5 cards gaining more than 5% in this window.`
- Only losers short: `Showing 4 losers. Your collection has fewer than 5 cards losing more than 5% in this window.`

The 5% threshold value should appear in the message dynamically (so changing the constant updates the message).

### Hover and click

- **Hover:** Card name, set, percentage change, absolute dollar change, price at start of window, current price
- **Click:** Navigate to `/cards/:cardId?from=collection`

---

## Top 10 Cards by Value Table

- **Columns:** Card image thumbnail, Card name, Set, Condition (with `1st Ed` badge inline), Variant, Quantity, Market price, Total value, Gained $ (conditional), Gained % (conditional)
- **Conditional columns:** The Gained $ and Gained % columns only appear if at least one card in the user's collection has a purchase price. Cells are blank for rows without a purchase price even when the columns are visible.
- **Default sort:** Total value descending
- **Sortable headers:** All columns sortable with ascending/descending arrows
- **No filter or search**
- **Row count:** Top 10. Shows fewer rows if collection has fewer cards. No pagination.
- **Click behavior:** Navigate to `/cards/:cardId?from=collection`
- **Collapsible:** Chevron icon next to the table title, open by default. Collapsed state persists in URL params.
- **Slicers respected:** All

---

## Sets Ranked by Value Table

- **Columns:** Rank, Set name, Cards owned, Set total, Completion progress bar, Total value, Percentage of collection
- **Default sort:** Total value descending (no user re-sorting; rank derives from this)
- **Click behavior on a row:** Sets the dashboard's set filter to that set, hiding all other rows. User clears via the slicer (M04_S04) or via the Clear Filter button that appears near the table when a set filter is active.
- **Title:** Static — `Sets Ranked by Value` regardless of filter state
- **Progress bar:**
  - Filled portion uses an info blue color from the design palette doc
  - Unfilled portion is empty/surface color
  - When 100% complete, the filled portion changes to Magikarp gold (`#F5C842`)
  - The progress bar visualizes `cards_owned / set_total` where the denominator depends on the secret rares toggle
- **Secret rares toggle:** Adjacent to the table — toggles the denominator between `printed_total` (default) and `total_with_secrets`. Affects only the completion progress bar in this table.
- **Collapsible:** Same chevron pattern as the Top 10 table.
- **Reset Collection action:** Top-right corner of this table's header. A small text button styled subtly. Clicking it clears the session and redirects to `/collection`.
- **Slicers respected:** All

---

## Database Changes

### New Table — `palette_colors`

A simple ordered list of hex colors used for set coloring across the dashboard.

```sql
CREATE TABLE palette_colors (
    id            SERIAL PRIMARY KEY,
    color_hex     TEXT NOT NULL,
    display_order INT NOT NULL UNIQUE
);
```

### Seed Data

Seed with the existing Magikarp palette as the starting point. The agent should insert these in the migration:

```sql
INSERT INTO palette_colors (color_hex, display_order) VALUES
    ('#E8412A', 1),  -- Magikarp red (primary)
    ('#F5C842', 2),  -- Magikarp gold (secondary)
    ('#A0A0B8', 3),  -- Muted grey-blue
    ('#1E1E30', 4),  -- Surface navy (only useful as outline contrast)
    ('#4CAF82', 5),  -- Success green
    ('#FFA726', 6),  -- Warning amber
    ('#CF6679', 7),  -- Error red
    ('#F5EDD6', 8);  -- Cream
```

(The user may add or replace entries via direct SQL during development. New entries take effect on the next page load with no code change required.)

### Alembic migration

Create a reversible Alembic migration that creates `palette_colors` and inserts the seed rows.

---

## API Changes

### New Endpoint — `GET /palette`

Returns the palette colors ordered by `display_order`.

```json
{
  "colors": ["#E8412A", "#F5C842", "#A0A0B8", "#1E1E30", "#4CAF82", "#FFA726", "#CF6679", "#F5EDD6"]
}
```

The frontend fetches this once on dashboard mount and assigns colors to sets in the order they appear in the data. New sets pick up whatever color comes next. If there are more sets than colors, the list cycles back to the start.

---

## Test Cases

---

### TC01 — Empty state redirect

**Steps:** Without uploading a collection, navigate to `/collection/dashboard`.

**Expected:** Redirected to `/collection`. A banner appears reading "No collection loaded yet — upload your collection or use the mock collection to get started."

---

### TC02 — KPI strip shows 2 KPIs without purchase prices

**Steps:** Upload a collection without purchase prices in any row. Navigate to dashboard.

**Expected:** Primary row shows two KPI cards: Total Collection Value and Total Card Count. Lifetime Gain cards are absent. Secondary row shows the most valuable card.

---

### TC03 — KPI strip shows 4 KPIs with purchase prices

**Steps:** Upload a collection with purchase prices on at least one row.

**Expected:** Primary row shows four KPI cards including Lifetime Gain ($) and Lifetime Gain (%). Cards without purchase prices are still excluded from the gain calculation but the columns appear.

---

### TC04 — Most valuable card uses per-card price not total value

**Steps:** Upload a collection containing:
- 3 copies of Card A at $20 each (total value $60)
- 1 copy of Card B at $59 (total value $59)

**Expected:** The Most Valuable Card line in the secondary KPI row shows Card B ($59), not Card A. The "most valuable" calculation uses individual `market_price`, not `quantity × market_price`.

---

### TC05 — Most valuable card link works

**Steps:** Click the card name in the secondary KPI row.

**Expected:** Navigates to `/cards/:cardId?from=collection`. The back button on the card detail page reads `← Dashboard`.

---

### TC06 — Download Excel button visible in page header

**Steps:** Open the dashboard.

**Expected:** A `Download Excel` button appears in the top-right corner of the page header, on the same row as the page title. Icon is a Microsoft Excel or file-excel icon. Button uses primary styling.

---

### TC07 — Download Excel button triggers download

**Steps:** Click the Download Excel button.

**Expected:** The button enters a loading state showing "Generating..." with a spinner. A request is made to `GET /collection/excel`. When the response comes back, a file download begins. The button returns to its normal state.

---

### TC08 — Download ignores active slicer filters

**Steps:**
1. Apply a slicer filter on the dashboard (e.g. set to Base Set only)
2. Click Download Excel

**Expected:** The downloaded workbook contains the user's FULL collection — including cards from other sets that were filtered out on the dashboard. The Excel export is independent of dashboard filter state.

---

### TC09 — Treemap renders with set outlines

**Steps:** View the treemap on the dashboard.

**Expected:** Each set's region has a clear colored outline. Cards within a set share the set's color via transparent fill. The outline color matches across all cards in the same set.

---

### TC10 — Treemap "Other" grouping appears

**Steps:** View a set in the treemap that has many low-value cards.

**Expected:** A single "Other (N cards)" rectangle is visible representing the bottom 10% of value. Hovering it shows the count and combined total value.

---

### TC11 — Pie chart takes full width when no variants

**Steps:** Use the mock collection (which has no variants).

**Expected:** The pie chart fills the entire row. The variant chart is not present in the layout.

---

### TC12 — Pie chart shares row when variants exist

**Steps:** Upload a collection with at least one non-standard variant.

**Expected:** The pie chart and variant chart appear side by side, each taking 50% of the row width.

---

### TC13 — Price over time defaults to 30D

**Steps:** Open the dashboard for a collection with at least 30 days of price history.

**Expected:** The price over time chart shows a line covering the last 30 days. The `30D` button is active, others are clickable.

---

### TC14 — Price over time disables out-of-range presets

**Steps:** Open the dashboard for a collection where the oldest price snapshot is only 14 days old.

**Expected:** `7D` is active by default (or `30D` if it falls back). Presets longer than the available data range are visually disabled and not clickable.

---

### TC15 — Time scale controls both charts

**Steps:** Click the `90D` preset.

**Expected:** Both the price over time chart AND the gainers/losers calculation update to use a 90-day window. The footnote under gainers/losers reflects this.

---

### TC16 — Gainers and losers respect minimum movement threshold

**Steps:** Open the dashboard. Pick a card you know moved less than 5%.

**Expected:** That card does not appear on either gainers or losers chart.

---

### TC17 — Insufficient data note appears with correct phrasing

**Steps:** Set the count selector to `20` for a collection with only 4 gainers and 7 losers above the threshold.

**Expected:** Below the gainers/losers charts, a note reads "Showing 4 gainers and 7 losers. Your collection has fewer cards moving more than 5% in this window." The 5% value matches the current threshold constant.

---

### TC18 — Top 10 table excludes gain columns when no purchase prices

**Steps:** Upload a collection with no purchase prices. View the Top 10 table.

**Expected:** The Gained $ and Gained % columns are entirely absent from the table header and rows.

---

### TC19 — Sets ranked filter on click

**Steps:** Click a set row in the Sets Ranked by Value table.

**Expected:** The dashboard's set filter activates for that set. All other charts and tables update to reflect only that set. The Sets Ranked table now shows only the selected set. A Clear Filter button appears near the table.

---

### TC20 — Reset collection clears session

**Steps:** Click the Reset Collection button in the Sets Ranked table header.

**Expected:** The session is cleared on the backend, the cookie is removed, and the user is redirected to `/collection`. The collection page no longer shows any persisted data.

---

### TC21 — Collapsible tables persist state in URL

**Steps:**
1. Collapse the Top 10 table via its chevron
2. Refresh the page

**Expected:** The Top 10 table is still collapsed after refresh. The URL contains a query param representing the collapsed state.

---

### TC22 — Slicers respected by every chart

**Steps:** Manually apply a filter via URL params (e.g. `?sets=base1`). Refresh the page.

**Expected:** All charts, KPIs, and tables show only Base Set data. The pie chart shows one slice, the treemap shows one set's cards, the gainers/losers charts only consider Base Set cards, the Top 10 table only contains Base Set cards, the Sets Ranked table only shows Base Set.

---

### TC23 — Palette endpoint returns colors in order

**Steps:** Hit `GET /palette` directly.

**Expected:** Returns the seeded colors in the order matching `display_order`.

---

### TC24 — Most valuable card breaks ties consistently

**Steps:** Upload a collection where two or more cards tie for the highest market price.

**Expected:** The same card appears in the secondary KPI row consistently across page refreshes. Tie-breaking is by card_id alphabetically.

---

## Notes for the Agent

**Variant treatment is blocked.** Capture variant data from the upload but do not implement variant normalization, the variant chart's full logic, or variant-aware filtering until the dedicated variant story is built. Comment any variant-related code with `// TODO: variant story` so it's easy to find later.

**Filter state is scaffolded but no UI to control it.** Build all charts to read from `filteredCollection`. The slicer panel UI lives in M04_S04 — assume it exists and just populates the filter state object.

**LOCF for price history.** The Last Observation Carried Forward logic for the price over time chart is critical — without it the chart will have gaps and look broken. Test specifically with cards that have sparse history.

**Mock collection is variant-free.** When testing locally, the mock collection (M04_S02) has no variants, so the variant chart should be hidden when using mock data. Verify this is the case before adding test data with variants.

**Most valuable card uses per-card price.** Not total value. A single $59 card beats three $20 cards even though the trio's total value is higher. This is intentional and tested in TC04.

**Download Excel button calls an endpoint that lives in M04_S05.** The endpoint may not exist yet when this story is implemented — that's acceptable. Wire the button correctly, handle the response, and the feature will work end-to-end once M04_S05 is also complete.
