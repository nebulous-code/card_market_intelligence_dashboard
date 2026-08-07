# Milestone 6+ — Future Roadmap

This document captures ideas and features that are intentionally deferred beyond Milestone 5. These are not abandoned — they are staged for when the core application is stable, data is mature, and the right foundation is in place to build them well.

Items are loosely grouped by theme. Nothing here has a fixed milestone assignment yet — that planning happens when Milestone 5 is complete and the project's direction is clearer.

---

## Power BI Report

Originally scoped into Milestone 4 and descoped when the Excel workbook absorbed the same purpose. Kept here rather than dropped, because a Power BI report would demonstrate a different toolchain rather than repeat what the workbook already shows.

Reasons it was deferred rather than built:

- The Excel workbook already demonstrates self-service BI over the same data — Power Query, a slicer-driven dashboard, pivots and a parameterised analyzer
- A `.pbix` file cannot be opened by a reviewer without Power BI Desktop, whereas the workbook opens anywhere
- Publishing to Power BI Service for a shareable link requires a paid tier for most sharing scenarios

If revisited, the natural shape is a direct connection to the Postgres instance rather than an import of the collection session, since the interesting Power BI story is the market-wide price history rather than a single user's collection.

---

## Custom Domain — API Half

The frontend now serves from `cards.nebulouscode.com`. The API deliberately stayed on its Render hostname, so this entry covers only the remaining half.

Moving the API under `nebulouscode.com` as well — `api.cards.nebulouscode.com` is the natural shape — would buy one concrete thing beyond tidiness. Today the two sides sit on different registrable domains, so the browser treats them as separate sites and the collection session cookie must be `SameSite=None`. Under a shared registrable domain they become same-site and it could drop to `SameSite=Lax`, which is the safer default and does not depend on third-party cookie behaviour that browsers keep tightening.

- A second CNAME pointing at the API service; Render provisions TLS automatically
- Update `VITE_API_BASE_URL` in the frontend service
- `FRONTEND_URL` is already correct and would not change
- Relax `_cookie_samesite()` in `api/routers/collection.py` from `none` to `lax`, which its docstring already flags

Not urgent. The current setup works; this removes a workaround rather than fixing a bug.

---

## UI / UX Design Overhaul

The frontend shell established in Milestone 3 is functional and consistent but not a finished design. A dedicated design pass would address:

- Typography hierarchy and spacing refinements
- Responsive layout improvements for smaller screens
- Animation and micro-interaction polish
- Accessibility audit — keyboard navigation, color contrast, screen reader support
- Potential migration to a more customized component style moving away from default Vuetify aesthetics

This was explicitly flagged during Milestone 3 planning as post-Milestone 5 work. The shell is designed to make this pass straightforward — visual changes without structural rewrites.

---

## Save and Compare Filters

Allow users to save named filter configurations and compare two filter sets side by side.

**Example use cases:**
- Save `"Base Set Holos"` as a filter preset (Rarity = Rare Holo, Set = Base Set)
- Compare prices for 1st Edition vs Unlimited printings of the same cards side by side
- Save a personal watchlist of specific cards as a named filter

**Implementation considerations:**
- Filter presets could live in localStorage or URL-shareable slugs — no backend required for personal use
- Side-by-side comparison would require a split-pane view component
- This builds naturally on the URL query param filter persistence established in M03_S06

---

## Variant Pricing Analysis

During Milestone 2 planning, variant cards (shadowless, 1st Edition, misprint, promo, etc.) were intentionally quarantined from standard pricing and stored in metadata without being surfaced in the frontend. The reasoning was to avoid contaminating standard price data until enough metadata had accumulated to make informed decisions.

Once sufficient variant data exists this feature would:

- Surface variant pricing as a distinct data layer separate from standard card pricing
- Show premium multipliers — e.g. `1st Edition Charizard trades at 4.2× the Unlimited price`
- Add variant filtering to the card table and chart
- Potentially a dedicated variant analysis page

**Prerequisite:** A meaningful volume of variant metadata must exist before this is worth building. Review the table after 3-6 months of ingestion to assess coverage.

---

## Admin Panel

Several operational capabilities are currently only accessible via direct database queries or command-line scripts. An admin panel would surface these in the UI:

**Ingestion management:**
- Trigger a manual ingestion run for a specific set without SSH access
- View ingestion run history — date, sets processed, match rates, errors
- Review and resolve low-confidence card matches
- Add or edit entries in `set_identifiers` without writing raw SQL

**Data management:**
- View and manage sets in the database
- Manually correct card number mappings that failed automated matching
- Flag cards or price snapshots for exclusion from analysis

**Access control:**
- Admin panel should sit behind API key authentication (Milestone 5 auth layer is the prerequisite)
- Read-only public dashboard vs. admin write access

---

## Collection CSV Upload and Excel Report Expansion

The collection feature planned for Milestone 4 covers the basic flow — upload a CSV, get an Excel report back. A later milestone could expand this significantly:

- **Saved collections** — let users store their collection in the app with a generated shareable link rather than managing a CSV file manually
- **Collection performance over time** — show how a collection's total value has changed based on accumulated price snapshots
- **Trade analyzer** — given two collections, suggest fair trades based on current market prices
- **Want list** — a separate list of cards the user is looking to acquire, with price alerts when values drop below a target

---

## Price Alerts and Notifications

Allow users to set a target price on a card and receive a notification when the market price crosses that threshold.

- Email notification via the existing Gmail SMTP infrastructure
- Alert configuration stored per card per user (requires some form of user identity — even just an email address without full auth)
- Daily digest option — instead of instant alerts, a morning summary of cards that crossed thresholds overnight

---

## Additional Data Sources

The current pricing pipeline relies solely on PokemonPriceTracker. Additional sources would improve data quality and enable cross-market analysis:

- **Cardmarket** — European market prices in EUR, available on PPT's Business tier or directly via Cardmarket's API
- **Additional eBay markets** — UK, EU eBay completed sales for international price comparison
- **PSA population reports** — how many copies of a card exist at each grade, which affects pricing significantly for high-value cards

---

## Expanded Set Coverage

The project currently targets Base Set, Jungle, Fossil, and Pokémon 151. Future expansion could cover:

- Full classic era — Base Set 2, Team Rocket, Gym Heroes, Gym Challenge, Neo sets
- Full modern era — Sword and Shield series, Scarlet and Violet series
- Japanese exclusives — sets that never had an English release
- Promo cards — harder to map but valuable for completionists

Expansion is straightforward once the set mapping infrastructure (M03_S01) is stable — it's primarily an operational task of registering new sets and running ingestion.

---

## Unpriced-Card Count on the Dashboard

Deferred from the pricing coverage design (`docs/PRICING_COVERAGE_DESIGN.md`). That design adds `price_missing` and `price_missing_reason` columns to the collection table, which is the durable record of what was excluded from a valuation — but it only helps someone who already suspects a problem and goes looking.

A single figure on the Dashboard, "cards without pricing: N", would make it discoverable without any of the layout difficulty that made a dynamic warning block unattractive. One cell, fixed height, sitting where the user is already reading the totals it qualifies.

Applies to both the Excel Dashboard sheet and the web dashboard. On the web side it may be redundant with the header banner that design already calls for; on the Excel side there is no equivalent, so the KPI is the only discoverability mechanism the workbook would have beyond the About sheet.

Worth revisiting once there is evidence of people actually hitting unpriced sets — the count is only interesting if it is sometimes non-zero.

---

## Run Nightly Ingestion Against Dev

The ingestion workflow reads a single `DATABASE_URL` secret, which points at production. Every branch resolves the same secret, so a `workflow_dispatch` run from a feature branch writes to prod exactly like the scheduled one does. **There is no way to test an ingestion change without running it against live data.**

That is not theoretical. Debugging the `ON CONFLICT` cardinality failure took several runs against production, each one either writing rows or rolling back, with the only feedback being a summary email and manual database queries.

What this would need:

- A second secret, something like `DEV_DATABASE_URL`, pointing at the dev Neon branch
- A `workflow_dispatch` input selecting the target, defaulting to production so the scheduled run is unchanged
- The credit budget is not a blocker — a full Base Set pull with history and eBay is roughly 300 credits against a 20,000/day allowance, so a dev run costs about 1.5% of a day

Two things make this more valuable than it first looks. Dev already carries far richer data than prod (518k snapshots with all five conditions, versus prod's NM-only history), so it is the better environment for exercising the multiplier and Excel paths. And ingestion is the part of the system with the least test coverage of its real failure modes, because those only appear against a live API and a real database.

Worth pairing with a `--dry-run` flag that fetches and parses but does not write, which would catch shape changes in the PPT response without touching either database.

---

## Performance and Scalability

At current scale (4 sets, ~400 cards, daily snapshots) performance is not a concern. At larger scale — 50+ sets, 10,000+ cards, years of daily snapshots — some investment would be needed:

- Database indexes on `price_snapshots` for common query patterns
- Pagination on the card table API endpoint (currently returns all cards in a set)
- Caching layer for expensive aggregation queries (set-level min/avg/max)
- Consider moving price history queries to a materialized view that refreshes nightly after ingestion

---

## Public API

If the project reaches a point where the data and analysis are genuinely useful to the Pokémon TCG community, exposing a read-only public API with rate limiting and API key authentication would be a natural extension. This would also be a portfolio signal — running a public API used by other developers is a different level of credibility than a personal project.
