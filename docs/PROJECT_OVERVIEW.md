# Pokémon Card Market Intelligence Dashboard

## Project Overview

This project is a full-stack portfolio application built around Pokémon card pricing data. The goal is to aggregate data from multiple public APIs, store and serve it through a custom-built REST API, and present it through an interactive Vue.js dashboard with reporting and drill-down capabilities.

The project is designed to demonstrate competency across the full development stack — from data ingestion and API design to frontend development and analytical reporting. A secondary objective is to showcase data skills in Excel and Power BI, which are presented as companion artifacts to the main application.

### Skills Demonstrated

- Full-stack web development (Vue.js frontend, REST API backend)
- Third-party API integration (pokemontcg.io, eBay)
- API design and documentation
- Relational database design and querying
- Data aggregation and transformation
- Analytical reporting and data visualization
- Excel / Power BI (secondary)

---

## Data Sources

| Source | Purpose |
| --- | --- |
| [pokemontcg.io](https://pokemontcg.io) | Card and set metadata, baseline price reference |
| [eBay Completed Sales API](https://developer.ebay.com) | Real transaction prices for market validation |

---

## Architecture Overview

``` markdown
[ External APIs ]
  pokemontcg.io
  eBay API
       │
       ▼
[ Ingestion Service ]
  Scheduled or manually triggered data pull
  Cleans, normalizes, and stores snapshots
       │
       ▼
[ Database ]
  PostgreSQL
  Cards, sets, price history
       │
       ▼
[ Custom REST API ]
  Node.js / Express (or equivalent)
  Serves aggregated data to the frontend
       │
       ▼
[ Vue.js Dashboard ]
  Summary views, trend charts, drill-down tables
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

### Milestone 1 — Minimum Viable Demo

**Goal:** A single thin slice of the full system, end to end. Every layer of the stack is represented in its simplest working form.

**Scope:**

- Integrate pokemontcg.io — pull one set's card data and an initial price snapshot, store in the database
- Build a REST API with a small set of core endpoints: `/sets`, `/sets/:id/cards`, `/cards/:id`
- Build the Vue.js application shell — navigation, one dashboard page with a summary chart and a drill-down table
- Deploy to a public URL (Railway, Render, or equivalent)
- Write a README covering the architecture and how to run the project locally

**Outcome:** A live, publicly accessible application with a GitHub repository. All layers of the stack are functional and connected.

---

### Milestone 2 — Real Market Pricing

**Goal:** Introduce actual transaction data alongside the reference pricing from Milestone 1, and add a time dimension to the dataset.

**Scope:**

- Integrate the eBay completed sales API for the same card set
- Add a `price_history` table; begin collecting periodic price snapshots
- Expose a `/cards/:id/price-history` endpoint from the API
- Add a price history chart to the card detail view in Vue
- Display a comparison between pokemontcg.io reference prices and eBay market prices

**Outcome:** The application now reflects real market behavior and has historical depth that grows over time.

---

### Milestone 3 — Expanded Data and Analytical Reporting

**Goal:** Broaden the dataset and elevate the application from a data viewer to an analytical product.

**Scope:**

- Pull in data across multiple card sets
- Add a set overview page with drill-down navigation into individual cards
- Add a Market Trends section with written analytical conclusions alongside the visualizations — not just charts, but interpretation
- Add filtering, sorting, and column controls to the data tables

**Outcome:** The application demonstrates both technical breadth and the ability to communicate findings from data, not just display them.

---

### Milestone 4 — Excel and Power BI Integration

**Goal:** Demonstrate reporting and business intelligence skills as a complement to the web application.

**Scope:**

- Add export-to-Excel functionality from the Vue frontend, with formatted output (headers, column widths, basic chart)
- Build a Power BI report connected to the PostgreSQL database, covering key metrics and trends
- Link or embed the Power BI report as a companion artifact within the application

**Outcome:** The project now spans the full range of reporting environments — web dashboard, spreadsheet export, and BI tooling.

---

### Milestone 5 — Polish and Hardening

**Goal:** Bring the application to a production-ready standard.

**Scope:**

- Add basic API authentication (read-only API key at minimum)
- Improve error handling, loading states, and empty states throughout the frontend
- Automate data refresh on a schedule rather than requiring manual triggers
- Expand documentation — API reference, architecture notes, and setup guide beyond the README

**Outcome:** The application reflects the kind of care and completeness expected in a production environment, not just a demo.

---

## Repository Structure (Planned)

``` markdown
/
├── api/              # REST API (Node.js / Express or equivalent)
├── ingestion/        # Data ingestion scripts and scheduler
├── frontend/         # Vue.js application
├── db/               # Schema definitions and migrations
├── docs/             # Planning documentation and API reference
│   └── PROJECT_OVERVIEW.md
└── README.md
```

---
