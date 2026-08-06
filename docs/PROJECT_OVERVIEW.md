# Pokémon Card Market Intelligence Dashboard

## Project Overview

This project is a full-stack portfolio application built around Pokémon card pricing data. The goal is to aggregate data from multiple public APIs, store and serve it through a custom-built REST API, and present it through an interactive Vue.js dashboard with reporting and drill-down capabilities.

The project is designed to demonstrate competency across the full development stack — from data ingestion and API design to frontend development and analytical reporting. A secondary objective is to showcase data skills in Excel and Power BI, which are presented as companion artifacts to the main application.

### Skills Demonstrated

- Full-stack web development (Vue.js frontend, FastAPI backend)
- Third-party API integration (TCGdex, PokemonPriceTracker)
- API design and documentation
- Relational database design and querying
- Data aggregation and transformation
- Analytical reporting and data visualization
- Excel / Power BI (secondary)

---

## Data Sources

| Source | Purpose |
| --- | --- |
| [TCGdex](https://tcgdex.dev) | Card and set metadata — free, open source REST API |
| [PokemonPriceTracker](https://pokemonpricetracker.com) | TCGPlayer market prices and eBay graded sale data |

---

## Architecture Overview

```
[ External APIs ]
  TCGdex
  PokemonPriceTracker
       │
       ▼
[ Ingestion Service ]
  Scheduled via GitHub Actions (nightly)
  Cleans, normalizes, and stores snapshots
       │
       ▼
[ Database ]
  PostgreSQL via Neon (serverless, cloud-hosted)
  Cards, sets, price snapshots, set identifier mappings
       │
       ▼
[ Custom REST API ]
  Python / FastAPI
  Serves aggregated data to the frontend
       │
       ▼
[ Vue.js Dashboard ]
  Set list, set detail, card detail views
  Price distribution charts, drill-down tables, filters
  Export to Excel
       │
       ▼
[ Power BI Report ] (secondary)
  Connected directly to the database
  Companion analytical artifact
```

---

## Development Philosophy

This project is built incrementally using a vertical slice approach. Each milestone represents a stable, deployable state of the application. The goal at every stopping point is a live URL and a clean repository — something that could be reviewed at any stage of development without requiring explanation or caveat.

Milestones are ordered so that the most foundational skills are demonstrated first, with each subsequent milestone layering on additional depth rather than replacing what came before.

---

## Milestones

### Milestone 1 — Minimum Viable Demo ✅

**Goal:** A single thin slice of the full system, end to end. Every layer of the stack is represented in its simplest working form.

**Scope:**

- Integrate TCGdex — pull Base Set card data and store in the database
- Build a REST API with core endpoints: `/sets`, `/sets/:id/cards`, `/cards/:id`
- Build the Vue.js application shell — one dashboard page with a summary chart and a drill-down table
- Deploy to Render (prod and dev environments)
- Write a README and planning documentation

**Outcome:** A live, publicly accessible application with a GitHub repository. All layers of the stack are functional and connected.

---

### Milestone 2 — Real Market Pricing ✅

**Goal:** Introduce real market pricing data and add a time dimension to the dataset.

**Scope:**

- Integrate PokemonPriceTracker API for TCGPlayer market prices
- Implement watermark-based daily price snapshot ingestion via GitHub Actions
- Add a card detail page with price history chart
- Expose a `/cards/:id/price-history` endpoint

**Outcome:** The application reflects real market pricing with historical depth that grows over time.

---

### Milestone 3 — Expanded Data and Reporting (Complete)

**Goal:** Stabilize the data pipeline, broaden the dataset to multiple sets, and build out the full frontend navigation structure.

**Scope:**

- Implement a `set_identifiers` mapping table linking canonical set IDs to TCGdex and PPT names
- Improve ingestion logging, email summaries, and GitHub Actions artifact uploads
- Build the frontend shell — persistent sidebar, breadcrumb navigation, Magikarp dark theme, global formatters
- Add set list page, set detail page (box and whiskers price chart by rarity), and card detail breadcrumbs
- Add column filters and sorting to the card table with URL-persisted filter state
- Add a cold start loading experience with health check polling and Lottie animation
- Ingest Jungle, Fossil, and Pokémon 151

**Outcome:** A navigable multi-set application with a polished frontend structure and reliable data pipeline.

---

### Milestone 4 — Collection Analysis and Excel Integration (Complete)

**Goal:** Demonstrate reporting and business intelligence skills as a complement to the web application.

**Scope:**

- Condition multiplier analysis — observed price ratios between card conditions
- Collection upload — users submit a workbook of their cards and get it validated, priced and stored against a session
- Collection dashboard in the web app, with slicers over set, rarity, condition and variant
- Export-to-Excel from the Vue frontend, populating a designed workbook with the user's collection
- Excel template built on Power Query: dashboard with linked slicers, ranked sheets, an upgrade-cost analyzer, and a value-over-time chart

**Outcome:** The project spans web dashboard and spreadsheet reporting, with the Excel workbook standing as an analytical artifact in its own right rather than a flat data dump.

**Descoped:** the Power BI report originally listed here was not built. The Excel workbook covers the same ground — self-service BI over the same data — and a `.pbix` file is a weaker portfolio artifact than a workbook a reviewer can open without a Power BI licence. Moved to the Milestone 6+ roadmap rather than dropped.

---

### Milestone 5 — Polish and Hardening (Complete)

**Goal:** Bring the application to a production-ready standard.

**Scope:**

- Upload resource caps — request size, zip decompression bombs, archive shape, and row count, so an unauthenticated upload cannot exhaust memory or the database
- Rate limiting on the three write endpoints, keyed on the forwarded client address
- Error and empty states across every view that fetches data, with a shared error component and a tested message normalizer
- A catch-all route, so a mistyped URL is a page rather than a blank body

**Outcome:** The application reflects the care and completeness expected in a production environment. See [`docs/MILESTONE_5/DONE-M05_S01-HardeningAndStates.md`](./MILESTONE_5/DONE-M05_S01-HardeningAndStates.md).

**Descoped:** API key authentication. The frontend is a public SPA, so any key it carries ships in the JavaScript bundle and authenticates nothing, and there is no privileged operation to protect — every write is scoped to the caller's own session cookie. The real exposure was resource abuse, which the caps and rate limits address directly. Authentication becomes necessary when the Milestone 6 admin panel or a public API exists.

**Also descoped:** a hand-written API reference, since FastAPI generates one at `/docs`, and monitoring beyond what Render provides.

---

### Milestone 6+ — Future Roadmap

Ideas and enhancements staged for after Milestone 5 is complete. See [`docs/MILESTONE_6_PLUS_ROADMAP.md`](./MILESTONE_6_PLUS_ROADMAP.md) for the full list.

Highlights include custom domain setup, UI/UX design overhaul, saved and comparable filter presets, variant pricing analysis (1st Edition, Shadowless, etc.), an admin panel for ingestion management, expanded set coverage, price alerts, and a potential public API.

---

## Stack

| Layer | Technology |
| --- | --- |
| API | Python, FastAPI, Uvicorn |
| ORM / Migrations | SQLAlchemy, Alembic |
| Database | PostgreSQL via Neon |
| Frontend | Vue.js, Vite, Vuetify |
| Charts | Chart.js via vue-chartjs |
| Ingestion Scheduling | GitHub Actions |
| Deployment | Render (prod + dev) |

---

## Repository Structure

```
/
├── api/                  # FastAPI application
├── ingestion/            # Data ingestion scripts
├── frontend/             # Vue.js application
├── .github/
│   └── workflows/        # GitHub Actions (nightly ingestion)
├── docs/                 # Planning and architecture documentation
│   ├── PROJECT_OVERVIEW.md
│   ├── DEVELOPMENT_SETUP.md
│   ├── MILESTONE_1.md
│   ├── MILESTONE_2.md
│   ├── MILESTONE_6_PLUS_ROADMAP.md
│   └── stories/          # Per-story design docs (M03_S01, M03_S02, etc.)
└── README.md
```
