# M03_S04 — Set and Card Views

## Summary

Build out the pages that fill the frontend shell established in M03_S03. This story covers the Set List page, the Set Detail page (refactored from the existing dashboard), the Card Detail page (breadcrumb and formatting updates), and a Market Trends placeholder page. By the end of this story the app has a complete navigable structure from set list through to individual card detail.

---

## Dependencies

- M03_S03 (Frontend Shell) must be complete before this story is implemented. All components in this story are built inside `AppLayout`, use `AppBreadcrumbs`, and use formatters from `utils/formatters.js`.
- The API change described in the **API Changes** section below must be implemented alongside the frontend work.

---

## API Changes

### `GET /cards/{card_id}` — Add set display name and set total to response

The card detail endpoint must be updated to include two additional fields in its response so the frontend can build breadcrumbs and the card label without additional API calls:

| Field | Source | Example |
|---|---|---|
| `set_display_name` | `sets.name` joined from the card's `set_id` | `"Base Set"` |
| `set_printed_total` | `sets.printed_total` joined from the card's `set_id` | `102` |

These fields require a join from `cards` to `sets` in the existing query. Update the SQLAlchemy query, the Pydantic response schema, and the API router accordingly.

The breadcrumb label for a card is constructed on the frontend as:
```
{card.name} {card.number}/{card.set_printed_total}
```
Example: `Charizard 4/102`

---

## New Formatter — `formatCompactCurrency`

Add the following to `utils/formatters.js` alongside the existing formatters. Used on set cards where space is limited:

```javascript
/**
 * Format a number as compact USD currency.
 * Examples: 399.99 → '$400' | 1234.56 → '$1.2K' | 15000 → '$15K' | null → '—'
 */
export function formatCompactCurrency(value) {
  if (value === null || value === undefined || isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value)
}
```

---

## Pages

### 1. Set List Page — `/sets`

**Route:** `/sets`
**File:** `frontend/src/views/SetListView.vue`
**Breadcrumb:** `Sets` (no link — root level)

#### Layout

A responsive grid of set cards. On wide screens show 4 cards per row, on medium screens 3, on narrow screens 2. Use Vuetify's grid system (`v-row` / `v-col`) with breakpoint props.

Above the grid, a simple page title: **"Sets"** in large text with a subtitle showing the total number of sets currently in the database (e.g. `4 sets`).

Show a `LoadingSkeleton` with `type="card"` while the sets are loading. Show an `EmptyState` if the API returns zero sets.

#### Set Card Design

Each set is represented as a vertical card (`v-card`) styled to resemble a Pokémon card in proportion and layout. Fixed height of approximately 320px, fixed width filling the grid column.

**Structure top to bottom:**

1. **Image area** — top 40% of the card. The set logo image fills this area with `object-fit: contain` on a slightly darker background (`#12121F`). If no logo is available show a placeholder with the set name initials centered.

2. **Divider** — thin line in the primary accent color (`#E8412A`) separating image from stats.

3. **Set name** — bold, primary text color, one line, truncated if too long.

4. **Meta row** — two items on one line in secondary text color using small text:
   - Left: card count (e.g. `102 cards`)
   - Right: release date formatted as `Jan 1999` (month + year only, no day — use a new `formatMonthYear` formatter)

5. **Price mini-table** — a 2-row × 3-column layout at the bottom of the card. No visible table borders — just aligned text. Header row in secondary text color, value row in primary text color using `formatCompactCurrency`:

   ```
   Min      Avg      Max
   $0.25    $12.4K   $400K
   ```

   Min = lowest `market_price` across all cards in the set with a price snapshot.
   Avg = average `market_price` across all cards in the set with a price snapshot.
   Max = highest `market_price` across all cards in the set with a price snapshot.

   If no price data exists for the set yet, show `—` in all three cells with a note in secondary text: `No pricing data yet`.

6. **Hover state** — on hover, apply a subtle primary accent border (`#E8412A`, 1px) and slight elevation increase. The entire card is clickable and navigates to `/sets/{set_id}`.

#### API Call

```
GET /sets
```

The existing endpoint returns set metadata. Min/avg/max prices must also be returned. Either:
- Add these fields to the existing `GET /sets` response (preferred — one API call per page load), OR
- The frontend makes a second call per set (not preferred — N+1 problem)

**Preferred approach:** Update `GET /sets` to include `min_price`, `avg_price`, and `max_price` fields computed from the `price_snapshots` table. These can be null if no snapshots exist.

Add a `formatMonthYear` formatter to `utils/formatters.js`:
```javascript
export function formatMonthYear(value) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
  })
}
```

---

### 2. Set Detail Page — `/sets/:setId`

**Route:** `/sets/:setId`
**File:** `frontend/src/views/SetDetailView.vue`
**Breadcrumb:** `Sets › {Set Name}`

This page replaces the existing dashboard. The set is determined by the URL parameter — remove the dropdown selector entirely.

#### Layout

**Top section — Set Header**
A horizontal strip at the top of the page showing:
- Set logo (small, ~80px tall) on the left
- Set name (large heading) and series name (subtitle) next to the logo
- Release date and total card count on the right in secondary text color

**Middle section — Price Distribution Chart**
A box and whiskers plot showing price distribution by rarity. See Chart Specification below.

**Bottom section — Card Table**
The existing card table, refactored to live in this view. See Card Table section below.

Show `LoadingSkeleton` while data is loading for both the chart and table sections independently — the chart and table should load and display as their data arrives rather than waiting for both.

#### Box and Whiskers Chart Specification

**Library:** `chartjs-chart-box-plot` plugin for Chart.js, used via `vue-chartjs`.

Install:
```bash
npm install @sgratzl/chartjs-chart-boxplot
```

Register the plugin in the component before use:
```javascript
import { BoxPlotController, BoxAndWiskers } from '@sgratzl/chartjs-chart-boxplot'
import { Chart } from 'chart.js'
Chart.register(BoxPlotController, BoxAndWiskers)
```

**Data:** One box per rarity group present in the set. Each box is computed from the `market_price` values across all cards of that rarity that have at least one price snapshot. Show all rarity groups regardless of how many data points they have.

**Rarity order (X axis, left to right):**
`Common → Uncommon → Rare → Rare Holo`
Plus any other rarities present in the data, appended alphabetically after the standard four.

**Y axis:** Logarithmic scale. Label the axis `Market Price (USD)`. Format tick labels as compact currency using `formatCompactCurrency`.

**Colors:**
- Box fill: primary accent color at 30% opacity (`rgba(232, 65, 42, 0.3)`)
- Box border and whiskers: primary accent color (`#E8412A`)
- Median line: secondary accent color (`#F5C842`)
- Outlier points: secondary accent color (`#F5C842`) at 70% opacity

**Tooltip:** On hover over a data point or box, show:
- Rarity name
- Min, Q1, Median, Q3, Max values formatted as `formatCurrency`
- Number of cards in this rarity group

**Empty state:** If the set has no price snapshots at all, show `EmptyState` with message `"Price data has not been ingested for this set yet."` in place of the chart.

**API call:**
```
GET /sets/{set_id}/cards
```
The frontend computes the box plot data client-side from the cards and their latest price snapshots. No new endpoint needed.

#### Card Table

The existing `CardTable.vue` component, placed below the chart. Keep all existing columns. Apply the following updates:

- Price columns (`market_price`, `low_price`) formatted using `formatCurrency` — `—` for null values
- A **Details** button on the far right of each row navigating to `/cards/{card_id}`
- Default sort: by card number ascending
- The table should be independently loadable from the chart — do not block table render on chart data

---

### 3. Card Detail Page — `/cards/:cardId`

**Route:** `/cards/:cardId`
**File:** `frontend/src/views/CardDetailView.vue` (already exists — update in place)
**Breadcrumb:** `Sets › {Set Display Name} › {Card Name} {Number}/{Set Total}`

Example breadcrumb: `Sets › Base Set › Charizard 4/102`

- `Sets` links to `/sets`
- `Base Set` links to `/sets/base1`
- `Charizard 4/102` is plain text (current page)

The set display name and set printed total come from the updated `GET /cards/{card_id}` response (see API Changes above). The breadcrumb is built using these values after the API call resolves. Until the data loads, show a skeleton breadcrumb or the raw card ID as a fallback.

#### Formatting Updates

Apply formatters to all values on this page:
- All price values → `formatCurrency` (null → `—`)
- `captured_at` date → `formatDate`
- Card number displayed as `{number}/{set_printed_total}` (e.g. `4/102`)

No other structural changes to this page in this story. Layout and chart improvements are deferred to a later milestone.

---

### 4. Market Trends Placeholder — `/trends`

**Route:** `/trends`
**File:** `frontend/src/views/TrendsView.vue`
**Breadcrumb:** `Sets › Market Trends`

A single page containing only an `EmptyState` component:

```vue
<EmptyState
  icon="mdi-chart-timeline-variant"
  title="Market Trends"
  message="Market trend analysis is coming in a future update."
/>
```

Enable the Market Trends nav link in `AppLayout.vue` now that the route exists. Remove the `disabled` prop from that nav item.

---

## Router Summary

Update `frontend/src/router/index.js` with the following routes and breadcrumb metadata:

```javascript
const routes = [
  {
    path: '/',
    redirect: '/sets',
  },
  {
    path: '/sets',
    component: SetListView,
    meta: {
      breadcrumbs: [
        { title: 'Sets' },
      ],
    },
  },
  {
    path: '/sets/:setId',
    component: SetDetailView,
    meta: {
      breadcrumbs: [
        { title: 'Sets', to: '/sets' },
        { title: ':setId' },  // replaced dynamically by the view
      ],
    },
  },
  {
    path: '/cards/:cardId',
    component: CardDetailView,
    meta: {
      breadcrumbs: [
        { title: 'Sets', to: '/sets' },
        { title: ':setId', to: '/sets/:setId' },  // replaced dynamically
        { title: ':cardId' },                      // replaced dynamically
      ],
    },
  },
  {
    path: '/trends',
    component: TrendsView,
    meta: {
      breadcrumbs: [
        { title: 'Sets', to: '/sets' },
        { title: 'Market Trends' },
      ],
    },
  },
]
```

The root path `/` redirects to `/sets` so the set list is the app's entry point.

---

## Test Cases

---

### TC01 — Root path redirects to set list

**Steps:** Navigate to the app root URL (e.g. `http://localhost:5173/`).

**Expected:** Automatically redirects to `/sets`. The set list page loads and the breadcrumb shows `Sets`.

---

### TC02 — Set list shows all ingested sets

**Steps:** Navigate to `/sets`.

**Expected:** One card appears per set in the database. Each card shows the set logo, name, card count, release date (month + year format), and the min/avg/max price mini-table. If price data exists the values are formatted as compact currency. If not, `—` appears in all three cells.

---

### TC03 — Set card hover state

**Steps:** Hover over a set card on the set list page.

**Expected:** A 1px primary accent color border appears around the card and the card elevation increases slightly. The cursor changes to a pointer.

---

### TC04 — Set card click navigates to set detail

**Steps:** Click a set card on the set list page.

**Expected:** Navigates to `/sets/{set_id}`. The breadcrumb updates to `Sets › {Set Display Name}`. The set header, chart, and card table load for that set.

---

### TC05 — Box and whiskers chart renders with logarithmic Y axis

**Steps:** Navigate to a set detail page that has price snapshot data.

**Expected:** The chart renders with one box per rarity. The Y axis is logarithmic — tick intervals increase multiplicatively (e.g. $0.10, $1, $10, $100, $1000). The axis label reads `Market Price (USD)`. Tick values are formatted as compact currency.

---

### TC06 — Box and whiskers chart colors match theme

**Steps:** Inspect the chart visually on the set detail page.

**Expected:** Box fill is semi-transparent red, box borders and whiskers are solid primary red (`#E8412A`), median line is gold (`#F5C842`), outlier dots are semi-transparent gold.

---

### TC07 — Box and whiskers tooltip shows correct data

**Steps:** Hover over a box or outlier point on the chart.

**Expected:** Tooltip shows the rarity name, min/Q1/median/Q3/max values formatted as full currency (e.g. `$12.50`), and the number of cards in that rarity group.

---

### TC08 — Chart shows empty state when no price data exists

**Steps:** Navigate to a set that has been ingested via TCGdex but has no price snapshots yet.

**Expected:** The chart area shows the `EmptyState` component with the message `"Price data has not been ingested for this set yet."` The card table still loads and displays card metadata normally.

---

### TC09 — Card table prices formatted correctly

**Steps:** Navigate to any set detail page with price data.

**Expected:** All price values in the table show as `$399.99` format. Null prices show as `—`. No raw decimal numbers appear.

---

### TC10 — Details button navigates to card detail

**Steps:** Click the **Details** button on any row in the card table.

**Expected:** Navigates to `/cards/{card_id}`. The breadcrumb shows `Sets › {Set Display Name} › {Card Name} {Number}/{Set Total}`.

---

### TC11 — Card detail breadcrumb is fully correct

**Steps:** Navigate to a card detail page (e.g. `/cards/base1-4`).

**Expected:** Breadcrumb reads `Sets › Base Set › Charizard 4/102`. Specifically:
- `Sets` is a link to `/sets`
- `Base Set` is a link to `/sets/base1`
- `Charizard 4/102` is plain text with no link

---

### TC12 — Card detail breadcrumb set link works

**Steps:** From a card detail page, click the set name in the breadcrumb.

**Expected:** Navigates to the correct set detail page. The breadcrumb updates to `Sets › {Set Name}`.

---

### TC13 — Card detail prices and dates formatted

**Steps:** Navigate to any card detail page that has price snapshot data.

**Expected:** All prices display as `$399.99`. Dates display as `Apr 13, 2026`. Card number displays as `4/102` format. Null values display as `—`.

---

### TC14 — Market Trends page loads without error

**Steps:** Click Market Trends in the sidebar.

**Expected:** Navigates to `/trends`. The breadcrumb shows `Sets › Market Trends`. The empty state component is visible with the chart icon and the coming soon message. No console errors.

---

### TC15 — Market Trends nav link is now enabled

**Steps:** Look at the sidebar on any page.

**Expected:** The Market Trends link is no longer visually muted and is clickable. (This is the opposite of what TC10 in M03_S03 verified — confirm that the disabled state has been removed.)
