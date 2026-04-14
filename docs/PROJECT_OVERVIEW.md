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

### Milestone 3 — Expanded Data and Reporting

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

### Milestone 4 — Excel and Power BI Integration

**Goal:** Demonstrate reporting and business intelligence skills as a complement to the web application.

**Scope:**

- Add export-to-Excel from the Vue frontend with formatted output
- Build a Power BI report connected to the PostgreSQL database
- Collection CSV feature — users upload a CSV of their cards and receive an Excel report of collection value and performance

**Outcome:** The project spans the full range of reporting environments — web dashboard, spreadsheet export, and BI tooling.

---

### Milestone 5 — Polish and Hardening

**Goal:** Bring the application to a production-ready standard.

**Scope:**

- Add API key authentication
- Improve error handling, loading states, and empty states throughout the frontend
- Expand documentation — API reference, architecture notes
- Production hardening and monitoring improvements

**Outcome:** The application reflects the care and completeness expected in a production environment.

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
