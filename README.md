# Pokémon Card Market Intelligence Dashboard

A full-stack web application that aggregates Pokémon card pricing data from multiple sources and presents it through an interactive dashboard with drill-down reporting and trend analysis.

This is a portfolio project built to demonstrate full-stack development, API design, data pipeline construction, and analytical reporting skills.

---

## What It Does

- Pulls card and set metadata from the [pokemontcg.io](https://pokemontcg.io) API
- Collects real market transaction data from the eBay completed sales API
- Stores historical price snapshots in PostgreSQL to track trends over time
- Serves the aggregated data through a custom-built REST API
- Presents everything in a Vue.js dashboard with charts, filterable tables, and drill-down views

---

## Stack

| Layer | Technology |
| --- | --- |
| API | Python, FastAPI |
| ORM / Migrations | SQLAlchemy, Alembic |
| Database | PostgreSQL (Neon) |
| Frontend | Vue.js, Vite |
| Scheduled Ingestion | GitHub Actions |
| Deployment | Docker / Podman |

---

## Project Status

| Milestone | Description | Status |
| --- | --- | --- |
| 1 | Minimum viable demo — full vertical slice | In progress |
| 2 | Real market pricing via eBay, price history | Not started |
| 3 | Multi-set support, analytical reporting | Not started |
| 4 | Excel export, Power BI integration | Not started |
| 5 | Auth, automation, production hardening | Not started |

---

## Documentation

Planning and architecture documentation is in the [`docs/`](./docs) folder.

- [Project Overview](./docs/PROJECT_OVERVIEW.md) — goals, milestones, and architecture
- [Development Setup](./docs/DEVELOPMENT_SETUP.md) — how to run the project locally
- [Milestone 1](./docs/MILESTONE_1.md) — detailed scope and structure for the current milestone
