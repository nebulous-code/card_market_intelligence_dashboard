# Milestone 6+ — Future Roadmap

This document captures ideas and features that are intentionally deferred beyond Milestone 5. These are not abandoned — they are staged for when the core application is stable, data is mature, and the right foundation is in place to build them well.

Items are loosely grouped by theme. Nothing here has a fixed milestone assignment yet — that planning happens when Milestone 5 is complete and the project's direction is clearer.

---

## Custom Domain

Replace the default `onrender.com` subdomain with a custom domain name for both the frontend and API services. A custom domain makes the portfolio link more memorable and professional when sharing with hiring managers.

- Purchase a domain (Namecheap, Cloudflare, etc.) — typically $10-15/year
- Configure DNS CNAME records pointing to the Render service URLs
- Render handles TLS certificate provisioning automatically
- Update CORS allowed origins in the API to reflect the new domain
- Update `VITE_API_BASE_URL` and `FRONTEND_URL` environment variables in Render

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

## Performance and Scalability

At current scale (4 sets, ~400 cards, daily snapshots) performance is not a concern. At larger scale — 50+ sets, 10,000+ cards, years of daily snapshots — some investment would be needed:

- Database indexes on `price_snapshots` for common query patterns
- Pagination on the card table API endpoint (currently returns all cards in a set)
- Caching layer for expensive aggregation queries (set-level min/avg/max)
- Consider moving price history queries to a materialized view that refreshes nightly after ingestion

---

## Public API

If the project reaches a point where the data and analysis are genuinely useful to the Pokémon TCG community, exposing a read-only public API with rate limiting and API key authentication would be a natural extension. This would also be a portfolio signal — running a public API used by other developers is a different level of credibility than a personal project.
