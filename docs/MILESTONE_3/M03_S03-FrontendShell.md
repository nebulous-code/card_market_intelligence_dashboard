# M03_S03 — Frontend Shell

## Summary

Establish the foundational frontend structure that all current and future views are built inside. This includes a persistent sidebar, a reusable page layout component, Vuetify theme configuration with the Magikarp-inspired dark palette, breadcrumb navigation, global formatting utilities, and reusable empty state and loading skeleton components.

No existing page content should be removed — the goal is to wrap everything in a consistent shell and apply formatting improvements throughout.

---

## Design Decisions

### Theme

Dark mode only for now. No toggle.

| Role | Color | Hex |
|---|---|---|
| Background | Deep navy | `#12121F` |
| Surface (cards, panels) | Slightly lighter navy | `#1E1E30` |
| Primary accent | Magikarp red | `#E8412A` |
| Secondary accent | Magikarp gold | `#F5C842` |
| Primary text | Cream | `#F5EDD6` |
| Secondary text | Muted light grey | `#A0A0B8` |
| Error | Standard red | `#CF6679` |
| Success | Muted green | `#4CAF82` |
| Warning | Amber | `#FFA726` |

The primary accent (`#E8412A`) is used for: active sidebar items, primary buttons, links, and focus states.

The secondary accent (`#F5C842`) is used sparingly for: chart data series, stat highlights, badges, and decorative elements.

### Typography

Use Vuetify's default font stack. No custom font import needed — keep it simple for now.

---

## File Structure

New files to create:

```
frontend/src/
├── plugins/
│   └── vuetify.js          # Theme configuration (update existing or create)
├── layouts/
│   └── AppLayout.vue       # Persistent shell — sidebar + topbar + content slot
├── components/
│   ├── AppBreadcrumbs.vue  # Breadcrumb component
│   ├── EmptyState.vue      # Reusable empty state
│   └── LoadingSkeleton.vue # Reusable loading skeleton wrapper
├── utils/
│   └── formatters.js       # Currency, date, number formatting utilities
└── router/
    └── index.js            # Update with breadcrumb metadata on each route
```

---

## Vuetify Theme Configuration

Update `frontend/src/plugins/vuetify.js` to define the dark theme:

```javascript
import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'magikarp',
    themes: {
      magikarp: {
        dark: true,
        colors: {
          background:     '#12121F',
          surface:        '#1E1E30',
          primary:        '#E8412A',
          secondary:      '#F5C842',
          error:          '#CF6679',
          success:        '#4CAF82',
          warning:        '#FFA726',
          'on-background': '#F5EDD6',
          'on-surface':   '#F5EDD6',
          'on-primary':   '#F5EDD6',
        },
      },
    },
  },
})
```

---

## AppLayout.vue

The persistent shell component. Every view is rendered inside this layout. It consists of three regions:

- **Left sidebar** — fixed width, always visible, contains app title and navigation links
- **Top bar** — spans the content area, contains breadcrumbs
- **Main content area** — scrollable, renders the current route's view via `<slot />`

### Sidebar Navigation Links

For now include these links in order:

| Label | Icon | Route |
|---|---|---|
| Sets | `mdi-cards` | `/sets` |
| Market Trends | `mdi-chart-line` | `/trends` (placeholder — route does not exist yet, disable the link) |

The active link should use the primary accent color (`#E8412A`) as the background highlight.

### Structure

```vue
<template>
  <v-app>
    <v-navigation-drawer permanent width="240" color="surface">
      <!-- App title -->
      <v-list-item
        title="Card Market"
        subtitle="Intelligence Dashboard"
        class="py-4"
      />
      <v-divider />
      <!-- Nav links -->
      <v-list nav>
        <v-list-item
          v-for="item in navItems"
          :key="item.route"
          :to="item.route"
          :prepend-icon="item.icon"
          :title="item.label"
          :disabled="item.disabled"
          active-color="primary"
        />
      </v-list>
    </v-navigation-drawer>

    <v-app-bar flat color="surface" border="b">
      <v-app-bar-title>
        <AppBreadcrumbs />
      </v-app-bar-title>
    </v-app-bar>

    <v-main>
      <v-container fluid class="pa-6">
        <slot />
      </v-container>
    </v-main>
  </v-app>
</template>
```

---

## AppBreadcrumbs.vue

Reads breadcrumb data from the current route's `meta.breadcrumbs` array and renders a Vuetify `v-breadcrumbs` component.

### Route meta format

Each route that needs breadcrumbs defines them in `router/index.js` as a `breadcrumbs` array on the route's `meta` object. Each breadcrumb item has a `title` and optionally a `to` route path. The last item in the array is the current page and should not be a link.

Example for the card detail page:
```javascript
{
  path: '/cards/:cardId',
  component: CardDetailView,
  meta: {
    breadcrumbs: [
      { title: 'Sets', to: '/sets' },
      { title: 'Base Set', to: '/sets/base1' },   // dynamic — see below
      { title: 'Charizard' },                      // current page, no link
    ]
  }
}
```

For dynamic breadcrumbs (set name, card name) the component reads from the route params and the current page's loaded data. The breadcrumb component should accept an optional `dynamicCrumbs` prop that allows the parent view to override specific breadcrumb titles with values resolved at runtime — for example the set name or card name loaded from the API.

### Rendering

Use `v-breadcrumbs` with the divider set to `›`. The last item should be plain text (not a link) and use the primary text color. Previous items should use the secondary text color and be styled as links.

---

## Router Updates

Update `frontend/src/router/index.js` to add `meta.breadcrumbs` to every route:

| Route | Breadcrumbs |
|---|---|
| `/sets` | `Sets` (no link — this is the root) |
| `/sets/:setId` | `Sets` → `{Set Name}` |
| `/cards/:cardId` | `Sets` → `{Set Name}` → `{Card Name}` |
| `/trends` | `Sets` → `Market Trends` (placeholder) |

For routes with dynamic segments (`{Set Name}`, `{Card Name}`), the breadcrumb title defaults to the route param (e.g. `base1`) until the view loads the real name and updates it via the `dynamicCrumbs` mechanism.

---

## EmptyState.vue

A reusable component shown when a table or chart has no data to display. Replaces blank areas throughout the app.

### Props

| Prop | Type | Default | Description |
|---|---|---|---|
| `icon` | String | `mdi-magnify-off` | MDI icon name |
| `title` | String | `'No data found'` | Heading text |
| `message` | String | `''` | Optional supporting text |

### Usage

```vue
<EmptyState
  icon="mdi-currency-usd-off"
  title="No price data yet"
  message="Pricing data for this card has not been ingested yet."
/>
```

### Appearance

Centered vertically and horizontally within its container. Icon at 64px in secondary text color. Title in primary text color. Message in secondary text color. Subtle border or card background to visually separate it from the page background.

---

## LoadingSkeleton.vue

A thin wrapper around Vuetify's `v-skeleton-loader` that provides consistent loading states across the app. Replaces any existing spinner implementations.

### Props

| Prop | Type | Default | Description |
|---|---|---|---|
| `loading` | Boolean | `true` | Whether to show the skeleton |
| `type` | String | `'table'` | Vuetify skeleton type — `'table'`, `'card'`, `'list-item'`, `'chart'` etc. |

### Usage

```vue
<LoadingSkeleton :loading="isLoading" type="table">
  <CardTable :cards="cards" />
</LoadingSkeleton>
```

When `loading` is true the skeleton is shown. When false the default slot content is shown.

---

## Formatters — `utils/formatters.js`

A utility module that exports formatting functions used throughout the app. Import and use these everywhere a price, date, or number is displayed. Never format these values inline in a component.

```javascript
/**
 * Format a number as USD currency.
 * Returns '—' for null, undefined, or non-numeric values.
 * Examples: 399.99 → '$399.99' | 0 → '$0.00' | null → '—'
 */
export function formatCurrency(value) {
  if (value === null || value === undefined || isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

/**
 * Format an ISO date string to a readable date.
 * Examples: '2026-04-13' → 'Apr 13, 2026' | null → '—'
 */
export function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * Format a plain number with comma separators.
 * Examples: 1234 → '1,234' | null → '—'
 */
export function formatNumber(value) {
  if (value === null || value === undefined || isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US').format(value)
}

/**
 * Format a decimal as a percentage.
 * Examples: 0.1234 → '12.34%' | null → '—'
 */
export function formatPercent(value) {
  if (value === null || value === undefined || isNaN(value)) return '—'
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}
```

### Apply formatters throughout existing components

After creating the formatters, update all existing components that display prices, dates, or numbers to use them:

- `CardTable.vue` — price column
- `SetSummaryCard.vue` — release date, card count
- `PriceChart.vue` — axis labels and tooltips
- `CardDetailView.vue` (Milestone 2) — all price values

---

## Applying the Layout

Wrap the root `App.vue` or each view with `AppLayout`. The recommended approach is to wrap at the router view level in `App.vue`:

```vue
<template>
  <AppLayout>
    <router-view />
  </AppLayout>
</template>
```

This means every route automatically gets the sidebar, top bar, and breadcrumbs without any per-view configuration.

---

## Test Cases

---

### TC01 — Dark theme is applied globally

**Steps:** Open the app in a browser.

**Expected:** Background is deep navy (`#12121F`), cards and panels are slightly lighter (`#1E1E30`), primary buttons and active nav items are Magikarp red (`#E8412A`). No white or light grey backgrounds anywhere on the page.

---

### TC02 — Sidebar is present on all pages

**Steps:** Navigate to `/sets`, then to a set detail page, then to a card detail page.

**Expected:** The sidebar is visible and unchanged on all three pages. The active nav item highlights in the primary accent color on the Sets link. The Market Trends link is visible but disabled (not clickable).

---

### TC03 — Breadcrumbs update correctly on navigation

**Steps:**
1. Navigate to `/sets` — note the breadcrumb
2. Click into a set — note the breadcrumb
3. Click the Details button on a card — note the breadcrumb

**Expected:**
- `/sets` shows: `Sets`
- Set detail shows: `Sets › Base Set`
- Card detail shows: `Sets › Base Set › Charizard`

The `Sets` and `Base Set` portions are clickable links. The last item (current page) is plain text.

---

### TC04 — Breadcrumb links navigate correctly

**Steps:** From the card detail page, click `Base Set` in the breadcrumb.

**Expected:** Navigates back to the Base Set detail page without a full page reload.

---

### TC05 — Currency formatting is applied to all price values

**Steps:** Open the card table on the dashboard and the card detail page.

**Expected:** All price values display as `$399.99` format. No raw decimal numbers like `399.99` appear anywhere. Null or missing prices display as `—` rather than blank, `null`, `undefined`, or `0`.

---

### TC06 — Date formatting is applied

**Steps:** Open the set detail page and look at the release date.

**Expected:** Release date displays as `Jan 09, 1999` format, not `1999-01-09` or a raw ISO string.

---

### TC07 — Empty state appears when no data is present

**Steps:** If possible, temporarily query a set that has no cards. Otherwise review the card detail page for a card with no price snapshots.

**Expected:** An `EmptyState` component is shown with an appropriate icon and message rather than a blank area or an empty table with no rows.

---

### TC08 — Loading skeleton appears during data fetch

**Steps:** Open the network tab in browser dev tools, throttle the connection to Slow 3G, then navigate to the set detail page.

**Expected:** A skeleton loader appears in place of the card table while the API request is in flight. The skeleton disappears and the table appears once data loads.

---

### TC09 — Formatters handle null and undefined gracefully

**Steps:** In the browser console, import and test the formatters directly:
```javascript
import { formatCurrency, formatDate, formatNumber } from '@/utils/formatters'
console.log(formatCurrency(null))       // → '—'
console.log(formatCurrency(undefined))  // → '—'
console.log(formatCurrency(399.99))     // → '$399.99'
console.log(formatDate(null))           // → '—'
console.log(formatDate('1999-01-09'))   // → 'Jan 9, 1999'
console.log(formatNumber(1234))         // → '1,234'
```

**Expected:** All outputs match the values shown above.

---

### TC10 — Market Trends nav link is disabled

**Steps:** In the sidebar, attempt to click the Market Trends link.

**Expected:** Nothing happens — the link is visually muted and does not navigate. No 404 error occurs.
