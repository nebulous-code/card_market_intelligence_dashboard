# M04_S04 — Collection Dashboard Slicers

## Summary

Build the slicer panel UI on the right side of the Collection Dashboard. Wire it into the filter state scaffolding established in M04_S03 so all charts, KPIs, and tables respond reactively to filter changes. Add collapse functionality to both the slicer panel and the existing left app sidebar.

The variant slicer is **blocked pending PPT parser testing** — the slicer's structure is included in this story but variant normalization rules are deferred to the variant story. The slicer should still work for whatever values are currently in the collection.

---

## Dependencies

- M04_S03 (Collection Dashboard) must be complete — this story consumes the `filterState` object and `filteredCollection` computed property established there
- The dashboard charts and tables already read from `filteredCollection`, so this story does not modify any chart code

---

## Slicer Panel — Right Sidebar

### Position and dimensions

- Fixed/sticky to the right edge of the dashboard content area, below the top app bar
- The dashboard content scrolls behind it; the slicer panel does not scroll with the page
- **Expanded width:** 320px
- **Collapsed width:** 64px
- Spans the full vertical height of the dashboard viewport

### Internal layout when expanded

Top to bottom:

1. Panel header with title `Filters` and a chevron icon (`mdi-chevron-right`) to collapse
2. Four slicer regions stacked vertically. Each takes one quarter of the panel height (or one third if the variant slicer is hidden — see Variant Hide Rule below)
3. Bottom of the panel: `Clear All Filters` button — only visible when at least one filter is active

### Internal layout when collapsed

Top to bottom:

1. Chevron icon (`mdi-chevron-left`) at the top to expand
2. Four icon rows with optional count badges — one per slicer
3. Bottom of the panel: small `Clear Filters` icon — only visible when at least one filter is active

### Slicers and their icons

| Slicer | Icon (MDI) |
|---|---|
| Sets | `mdi-cards` |
| Rarity | `mdi-diamond-stone` |
| Condition | `mdi-shield-outline` |
| Variant | `mdi-shimmer` |

The Sets icon (`mdi-cards`) intentionally matches the icon used in the left sidebar's Sets nav item for consistency.

---

## Slicer Behavior

### Excel-style chip toggle logic

Each slicer is a region with chip-style toggles for each available value. The interaction model mirrors Excel slicers:

| User action | Result |
|---|---|
| Initial state | All chips selected (no filter applied — equivalent to `filterState.<dimension>` being an empty Set) |
| Click any chip when all are selected | Deselects everything except the clicked chip. That chip becomes the only selected one. |
| Click an unselected chip when some are selected | Adds that chip to the selection (multi-select) |
| Click an already-selected chip when more than one is selected | Removes just that chip from the selection |
| Click the only-selected chip | No-op. The chip stays selected (cannot reach a zero-selection state through this path). |
| Click `Clear All Filters` button | Returns to the initial state — all chips selected across all slicers |

The user cannot reach a zero-selection state through normal interaction. Cascading filter logic that would produce empty downstream slicers is intentionally not implemented (see M04_S03 design discussion).

### Internal filter state representation

When all chips are selected, the corresponding `filterState.<dimension>` is an empty Set. When a subset is selected, the Set contains exactly the selected values.

```javascript
// All selected — no filter
filterState.sets = new Set()

// Two specific sets selected
filterState.sets = new Set(['base1', 'jungle'])
```

This shape is consumed directly by `filteredCollection` in the dashboard view (defined in M04_S03).

---

## Slicer Region Layout (When Expanded)

Each slicer region has:

1. **Header row** — slicer icon + slicer name + count badge (when filters are active)
2. **Chips area** — wrapping rows of chips, scrollable if values overflow

### Header styling

- Icon at the left, slicer name next to it
- Count badge (number) appears next to the name when filters are active
- When all values are selected (default state), no badge is shown and the icon uses default text color
- When a subset is selected, the icon and the count badge are both colored Magikarp gold (`#F5C842`)

### Chip styling

- Selected chip: filled with primary accent color (`#E8412A`), text in cream
- Unselected chip: outlined only, text in muted color
- Chips wrap onto multiple lines if they don't fit
- Within a slicer region, the chips area scrolls vertically if there are too many to fit in the allocated height — the scrolling is internal to the slicer, not the whole panel

### Region height

Each region takes an equal share of the available vertical space:
- Three slicers visible (variant hidden): each takes 1/3 of the panel
- Four slicers visible: each takes 1/4 of the panel

### Region order top to bottom

1. Sets
2. Rarity
3. Condition
4. Variant (when shown)

---

## Slicer Value Population

### Sets slicer

Populated dynamically from the user's collection. The values are the distinct `set_display_name` of sets present in the collection. Sorted alphabetically.

### Rarity slicer

Populated dynamically from the user's collection. The values are the distinct `rarity` values present in the collection. Sorted using a sensible rarity order — agent's call (e.g. Common → Uncommon → Rare → Rare Holo → Secret Rare → others).

### Condition slicer

Populated dynamically from the user's collection — same approach as the M03_S06 card table filter. Hardcoded conditions are not used because graded conditions like `PSA-10` or `BGS-9.5` should appear if the user owns those, and only if they do.

Sorted using a sensible condition order — agent's call (e.g. NM → LP → MP → HP → DMG, then graded conditions appended).

### Variant slicer

Populated dynamically from the user's collection. Values are the distinct variant strings present, with cards having no variant grouped under the chip label `Standard`.

**Important on Standard:** the user's upload uses blank/null for standard cards, not the literal text `"Standard"`. The slicer presents `Standard` as a chip label for these cards but internally the filter state value for that chip is `null` (or a sentinel like `'__standard__'`). The agent's call on the exact representation is fine as long as the filtering logic in `filteredCollection` (defined in M04_S03) treats `Standard` and `null/blank` as equivalent.

### Variant Hide Rule

If the user's collection contains only standard cards (no non-standard variants at all), the variant slicer is hidden entirely and the remaining three slicers expand to one-third of the panel each.

---

## Clear All Filters

### Expanded state

A text button at the bottom of the panel reading `Clear All Filters`.

- Visible only when at least one filter dimension has fewer than all values selected (i.e. any of the four `filterState` Sets is non-empty)
- Clicking it sets all four Sets back to empty (default "no filter" state)
- Styled subtly — secondary text color, no border, hover state in primary accent

### Collapsed state

A small filter-clear icon (`mdi-filter-off`) at the bottom of the panel.

- Visible under the same conditions as the expanded button
- Click behavior is identical — clears all filters
- Has a tooltip showing `Clear All Filters` on hover

---

## URL Persistence

The slicer panel reads and writes filter state to URL query parameters using the same pattern established in M03_S06 and scaffolded in M04_S03:

| Filter | Param | Format |
|---|---|---|
| Sets | `sets` | Comma-separated set IDs (e.g. `?sets=base1,jungle`) |
| Rarities | `rarities` | Comma-separated rarity strings, URL-encoded |
| Conditions | `conditions` | Comma-separated condition codes |
| Variants | `variants` | Comma-separated variant strings, URL-encoded; `Standard` represents the null/blank case |

Use `router.replace()` to update the URL — never `router.push()` — so filter changes don't add browser history entries.

The panel also writes a `slicersCollapsed` boolean to the URL when the panel is collapsed:

- `?slicersCollapsed=true`

---

## Left App Sidebar — Collapse Behavior

The existing left sidebar (Sets, Market Trends, Analyze Your Collection nav) gets the same collapse pattern.

### Dimensions

- **Expanded width:** 240px (current width — no change)
- **Collapsed width:** 64px

### Collapse trigger

- Chevron icon (`mdi-chevron-left` when expanded, `mdi-chevron-right` when collapsed) at the top of the sidebar
- Clicking the chevron OR the empty space in the sidebar (not the icons themselves) toggles the collapse state
- Clicking on a nav icon when collapsed navigates to that page — does NOT expand the sidebar

### Collapsed state appearance

- Each nav item shows only its icon, vertically centered in the 64px width
- The active route's icon is highlighted with primary accent color (existing behavior)
- The app title and subtitle are hidden when collapsed

### State persistence

Sidebar collapse state is **global across all pages** (not per-page). Persist via a simple localStorage key:

```javascript
localStorage.setItem('appSidebarCollapsed', 'true')
```

The sidebar reads this value on app mount and applies the appropriate state. This is intentionally NOT URL-persisted because the user's preference for sidebar layout is not part of the dashboard view — it's a global UI preference.

---

## Slicer Panel State Persistence

The slicer panel collapse state is URL-persisted (via `?slicersCollapsed=true`) because it is dashboard-specific and a shared link should reproduce the exact view the user had including collapsed slicers.

This is the difference between the two collapses:
- **Left sidebar collapse → localStorage** — global UI preference
- **Slicer panel collapse → URL param** — dashboard-specific view state

---

## Test Cases

---

### TC01 — Slicer panel renders on dashboard

**Steps:** Navigate to the collection dashboard with a loaded collection.

**Expected:** A right-side panel is visible at 320px wide. Four slicer sections are stacked vertically (Sets, Rarity, Condition, Variant) with chips populated from the user's collection.

---

### TC02 — Variant slicer hidden when no variants

**Steps:** Use the mock collection (variant-free).

**Expected:** Only three slicers are visible (Sets, Rarity, Condition). Each takes one-third of the panel height. The Variant slicer is not present.

---

### TC03 — Variant slicer visible when variants exist

**Steps:** Upload a collection with at least one non-standard variant card.

**Expected:** Four slicers are visible. Each takes one-quarter of the panel height. Variant slicer is at the bottom.

---

### TC04 — Clicking a chip when all selected isolates that chip

**Steps:** With no filters active, click the `Base Set` chip in the Sets slicer.

**Expected:** Only Base Set is now selected in the Sets slicer. All other set chips are deselected. The dashboard updates to show only Base Set data.

---

### TC05 — Clicking a second chip adds to selection

**Steps:** Continuing from TC04, click the `Jungle` chip.

**Expected:** Both Base Set and Jungle are selected. The dashboard now shows data from both sets. The URL contains `?sets=base1,jungle`.

---

### TC06 — Clicking a selected chip removes it

**Steps:** Continuing from TC05, click the `Base Set` chip.

**Expected:** Only Jungle remains selected. The dashboard updates to show only Jungle data.

---

### TC07 — Cannot deselect the only-selected chip

**Steps:** Continuing from TC06 with only Jungle selected, click the `Jungle` chip.

**Expected:** Jungle remains selected. No state change occurs. The dashboard does not show an empty state.

---

### TC08 — Clear All Filters resets everything

**Steps:** Apply filters in multiple slicers. Click `Clear All Filters`.

**Expected:** All slicers return to "all selected" state. The Clear All Filters button disappears. The URL query params for filters are removed.

---

### TC09 — Count badge appears with active filters

**Steps:** Select two specific sets. Look at the Sets slicer header.

**Expected:** A `2` badge appears next to the Sets slicer name. Both the icon and the badge are colored Magikarp gold.

---

### TC10 — Slicer panel collapses

**Steps:** Click the chevron at the top of the slicer panel.

**Expected:** The panel collapses to 64px wide. The chevron now points the opposite direction (`mdi-chevron-left`). Each slicer's icon is visible. The dashboard content area expands to fill the freed space.

---

### TC11 — Count badges visible when collapsed

**Steps:** With filters applied to the Sets slicer (e.g. 2 selected), collapse the slicer panel.

**Expected:** The Sets icon shows a `2` badge in Magikarp gold next to it. Other slicers without active filters show their icons in default color with no badge.

---

### TC12 — Slicer collapse state persists in URL

**Steps:** Collapse the slicer panel. Refresh the page.

**Expected:** The slicer panel is still collapsed after refresh. The URL contains `?slicersCollapsed=true`.

---

### TC13 — Left sidebar collapses independently

**Steps:** Click the chevron at the top of the left app sidebar.

**Expected:** The left sidebar collapses to 64px. Nav icons remain visible. The dashboard content area expands. The slicer panel state is unchanged.

---

### TC14 — Left sidebar nav still works when collapsed

**Steps:** With the left sidebar collapsed, click the Sets icon.

**Expected:** Navigates to `/sets`. The sidebar remains collapsed (does not auto-expand).

---

### TC15 — Left sidebar state persists across pages

**Steps:**
1. On the dashboard, collapse the left sidebar
2. Navigate to `/sets`

**Expected:** The left sidebar is still collapsed on the Sets page. localStorage contains `appSidebarCollapsed=true`.

---

### TC16 — Slicer values populated dynamically

**Steps:** Upload a collection that contains only Common and Uncommon cards.

**Expected:** The Rarity slicer shows only `Common` and `Uncommon` chips. `Rare Holo`, `Secret Rare`, etc. are not present even though those rarities exist in the broader database.

---

### TC17 — URL filter params restore state on load

**Steps:** Load `/collection/dashboard?sets=base1&rarities=Rare+Holo` directly.

**Expected:** The dashboard loads with Sets filtered to Base Set only and Rarity filtered to Rare Holo only. The chips reflect this state. The dashboard charts and tables show data filtered accordingly.

---

### TC18 — Standard variant chip filters null variants correctly

**Steps:** Upload a collection with both Standard and Reverse Holo cards. In the Variant slicer, select only `Standard`.

**Expected:** The dashboard shows only cards with no variant set (null/blank). Reverse Holo cards are hidden.

---

### TC19 — Slicer scrolls internally when many values

**Steps:** Upload a collection with many distinct rarities (10+).

**Expected:** The Rarity slicer's chip area scrolls internally without scrolling the entire slicer panel or the page. The slicer's height stays at one-quarter (or one-third) of the panel.

---

### TC20 — Slicer panel and dashboard scrolling are independent

**Steps:** Scroll the dashboard content area.

**Expected:** The slicer panel stays fixed in place. The left app sidebar also stays fixed. Only the dashboard content between them scrolls.

---

## Notes for the Agent

**This story does not modify chart code.** Charts and tables in M04_S03 are already wired to read from `filteredCollection`. This story populates the filter state — that's it. If a chart's behavior is wrong with filters applied, the bug is in the chart's filter handling (M04_S03), not in this story.

**The variant slicer's structure is built but variant normalization is deferred.** The slicer should treat variant strings as-is (no normalization, no comma splitting, no parser calls) for now. The dedicated variant story will revisit this once the PPT parser behavior is confirmed.

**Cannot reach a zero-selection state.** This is intentional — clicking the only selected chip is a no-op rather than deselecting it. Without this rule, users could filter the dashboard to "show nothing" which would be confusing. The Excel-style behavior we're modeling has the same constraint.

**Two collapses, two persistence mechanisms.** The left sidebar uses localStorage (global). The slicer panel uses URL params (dashboard-specific). Don't accidentally use one mechanism for both — it'd produce surprising behavior on shared links.
