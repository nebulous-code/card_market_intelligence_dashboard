# M03_S06 — Card Table Filters and Sorting

## Summary

Add Excel-style column header filters to the card table on the Set Detail page. Filters are applied client-side against already-loaded card data — no additional API calls are made. The box and whiskers chart updates in real time to reflect the currently filtered cards. Filter state is persisted in URL query parameters so filtered views survive navigation and can be bookmarked or shared.

Sorting is already implemented — this story adds filters only.

---

## Filterable Columns

| Column | Filter Type | Behavior |
|---|---|---|
| Name | Text input | Case-insensitive substring match — filters as user types |
| Supertype | Multi-select dropdown | Shows: `Pokémon`, `Trainer`, `Energy`. Selecting multiple shows cards matching any selected value |
| Rarity | Multi-select dropdown | Populated dynamically from the rarities present in the currently loaded set — not hardcoded |
| Market Price | Range — two number inputs | Min and max inputs. Either can be left blank. Filters to cards where `market_price` is between min and max inclusive. Null prices are excluded when either bound is set |

---

## URL Query Parameter Format

Each active filter maps to a URL query parameter. Parameters are added, updated, or removed as the user interacts with the filters. The URL is updated using Vue Router's `router.replace()` — not `router.push()` — so filter changes do not add entries to the browser history stack.

| Filter | Query param | Example |
|---|---|---|
| Name | `name` | `?name=char` |
| Supertype | `supertype` | `?supertype=Pokémon` or `?supertype=Pokémon,Trainer` |
| Rarity | `rarity` | `?rarity=Rare+Holo` or `?rarity=Rare+Holo,Rare` |
| Min price | `minPrice` | `?minPrice=10` |
| Max price | `maxPrice` | `?maxPrice=500` |

Multiple filters combine with AND logic — a card must match all active filters to appear.

Multi-select values (supertype, rarity) are comma-separated in the URL.

**On page load**, the component reads existing query params from the URL and initializes filter state from them before rendering. This is what makes the state survive navigation — when the user clicks back from a card detail page, Vue Router restores the previous URL including query params, and the component initializes from them.

---

## Filter UI — Column Header Slots

Vuetify's `v-data-table` exposes a `header.{key}` slot for each column that allows custom content to be placed inside the column header. Use these slots to place filter controls directly in the header row below the column label.

The column header slot renders:
1. The column label and sort icon (existing behavior — do not remove)
2. Immediately below, the filter control for that column

This matches the Excel pattern — the label and sort control are on top, the filter input is directly underneath within the same header cell.

### Name column header

A `v-text-field` with:
- `density="compact"`
- `placeholder="Search..."`
- `clearable` — shows an × to clear the filter
- `hide-details` — no validation messages
- Bound to the `name` filter state via `v-model`
- `prepend-inner-icon="mdi-magnify"`

### Supertype column header

A `v-select` with:
- `multiple` — allows selecting more than one value
- `chips` with `small-chips` to show selected values compactly in the header
- `density="compact"`
- `clearable`
- `hide-details`
- Items populated from a hardcoded list: `['Pokémon', 'Trainer', 'Energy']`

### Rarity column header

A `v-select` with the same configuration as Supertype, but items are populated dynamically from the distinct rarity values in the currently loaded card data — not hardcoded. Computed from the card array on load:

```javascript
const availableRarities = computed(() =>
  [...new Set(cards.value.map(c => c.rarity).filter(Boolean))].sort()
)
```

### Market Price column header

Two `v-text-field` inputs side by side using a small flex layout:
- Left input: `placeholder="Min $"`, bound to `minPrice`
- Right input: `placeholder="Max $"`, bound to `maxPrice`
- Both use `type="number"`, `density="compact"`, `hide-details`
- A small label `"Price Range"` above the two inputs

---

## Client-Side Filter Logic

All filtering happens in a computed property that derives the filtered card list from the full card list and the current filter state. The table and chart both consume the filtered list — neither ever accesses the raw card list directly after filters are applied.

```javascript
const filteredCards = computed(() => {
  return cards.value.filter(card => {
    // Name filter — case insensitive substring
    if (filters.name && !card.name.toLowerCase().includes(filters.name.toLowerCase())) {
      return false
    }

    // Supertype filter — match any selected value
    if (filters.supertype.length > 0 && !filters.supertype.includes(card.supertype)) {
      return false
    }

    // Rarity filter — match any selected value
    if (filters.rarity.length > 0 && !filters.rarity.includes(card.rarity)) {
      return false
    }

    // Price range filter — exclude null prices when a bound is set
    if (filters.minPrice !== null || filters.maxPrice !== null) {
      if (card.market_price === null) return false
      if (filters.minPrice !== null && card.market_price < filters.minPrice) return false
      if (filters.maxPrice !== null && card.market_price > filters.maxPrice) return false
    }

    return true
  })
})
```

---

## Chart Integration

The box and whiskers chart currently computes its data from the full card array. Update it to consume `filteredCards` instead. No other changes to the chart are needed — the chart will automatically reflect the active filters because it is reactive to the same computed property the table uses.

This means:
- Filtering to Rare Holo only shows a single box on the chart
- Filtering by price range removes outliers that fall outside the range
- Clearing all filters restores the full chart

Add a subtle note below the chart when filters are active:

```
Showing {filteredCards.length} of {cards.length} cards
```

In secondary text color, small font. Hidden when no filters are active (i.e. filtered count equals total count).

---

## Filter Reset

Add a **Clear Filters** button that appears only when at least one filter is active. Place it in the toolbar area above the table, aligned right.

Clicking it:
1. Resets all filter state to empty/null
2. Removes all filter query params from the URL via `router.replace({ query: {} })`

Use a `v-btn` with `variant="text"` and `prepend-icon="mdi-filter-off"` so it does not compete visually with the table content.

---

## URL Sync Implementation

Use a `watch` on the filter state object to update the URL whenever any filter changes:

```javascript
watch(filters, (newFilters) => {
  const query = {}
  if (newFilters.name) query.name = newFilters.name
  if (newFilters.supertype.length) query.supertype = newFilters.supertype.join(',')
  if (newFilters.rarity.length) query.rarity = newFilters.rarity.join(',')
  if (newFilters.minPrice !== null) query.minPrice = newFilters.minPrice
  if (newFilters.maxPrice !== null) query.maxPrice = newFilters.maxPrice
  router.replace({ query })
}, { deep: true })
```

Use `onMounted` to initialize filter state from URL params when the component first loads:

```javascript
onMounted(() => {
  const q = route.query
  if (q.name) filters.name = q.name
  if (q.supertype) filters.supertype = q.supertype.split(',')
  if (q.rarity) filters.rarity = q.rarity.split(',')
  if (q.minPrice) filters.minPrice = Number(q.minPrice)
  if (q.maxPrice) filters.maxPrice = Number(q.maxPrice)
})
```

---

## Test Cases

---

### TC01 — Name filter narrows table and chart

**Steps:**
1. Navigate to a set detail page
2. Type `char` in the Name filter

**Expected:** The table immediately narrows to only cards whose name contains `"char"` (case insensitive — `Charizard`, `Charmeleon`, `Charmander`). The chart updates to show only the rarity groups represented by those cards. The note below the chart shows `Showing 3 of 102 cards`.

---

### TC02 — Name filter updates URL

**Steps:** Same as TC01.

**Expected:** The URL updates to include `?name=char` without a full page reload or a new browser history entry.

---

### TC03 — Rarity filter populates dynamically

**Steps:** Click the Rarity dropdown in the column header.

**Expected:** The dropdown shows only the rarity values that exist in the current set — no hardcoded values. If a set has no Secret Rares, Secret Rare does not appear in the list.

---

### TC04 — Multi-select rarity filter

**Steps:** Select `Rare Holo` and `Rare` from the Rarity filter.

**Expected:** The table shows cards of either rarity. The URL contains `?rarity=Rare+Holo,Rare`. The chart shows boxes for only those two rarity groups.

---

### TC05 — Supertype filter

**Steps:** Select `Trainer` from the Supertype filter.

**Expected:** Only Trainer cards appear in the table. The chart updates accordingly. The URL contains `?supertype=Trainer`.

---

### TC06 — Price range filter excludes null prices

**Steps:** Enter `100` in the Min Price input.

**Expected:** Only cards with a `market_price` of $100 or more appear. Cards with no price data (`null`) are excluded from the table. The URL contains `?minPrice=100`.

---

### TC07 — Combined filters use AND logic

**Steps:** Select `Rare Holo` from Rarity and enter `200` in Min Price.

**Expected:** Only cards that are both Rare Holo AND have a market price of $200 or more appear. The URL contains both `?rarity=Rare+Holo&minPrice=200`.

---

### TC08 — Filter state survives navigation

**Steps:**
1. Apply a Rarity filter for `Rare Holo`
2. Click Details on a card to navigate to the card detail page
3. Click `Base Set` in the breadcrumb to navigate back to the set detail page

**Expected:** The Rarity filter is still applied — the table shows only Rare Holo cards. The URL still contains `?rarity=Rare+Holo`.

---

### TC09 — Filtered URL can be bookmarked and restored

**Steps:**
1. Apply filters — e.g. `?rarity=Rare+Holo&minPrice=100`
2. Copy the full URL from the browser address bar
3. Open a new browser tab and paste the URL

**Expected:** The set detail page loads with the filters already applied — the table shows only Rare Holo cards with price over $100, the chart reflects those filters, and the filter controls show the active values.

---

### TC10 — Clear Filters button appears and works

**Steps:**
1. Apply any filter
2. Note the Clear Filters button appears above the table
3. Click it

**Expected:** All filter controls reset to empty. The table shows all cards. The chart shows all rarity groups. The URL query string is cleared. The Clear Filters button disappears.

---

### TC11 — Clear Filters button is hidden when no filters active

**Steps:** Navigate to a set detail page with no query params in the URL.

**Expected:** The Clear Filters button is not visible.

---

### TC12 — Chart note shows correct counts

**Steps:** Apply the Rarity filter for `Rare Holo` on Base Set (4 Rare Holo cards).

**Expected:** A note below the chart reads `Showing 4 of 102 cards` in small secondary text. After clearing filters the note disappears.

---

### TC13 — Sorting still works with filters applied

**Steps:**
1. Filter by Rarity `Rare Holo`
2. Click the Market Price column header to sort descending

**Expected:** The filtered results sort correctly — only Rare Holo cards, sorted by price descending. Sorting does not clear or interfere with active filters.

---

### TC14 — Name filter clear button works

**Steps:**
1. Type a name in the Name filter
2. Click the × (clearable) icon inside the text field

**Expected:** The name filter clears, the table resets to show all cards (subject to other active filters), and the `name` param is removed from the URL.
