# Pokémon Card Market Intelligence Dashboard

A full-stack web application that aggregates Pokémon card data and presents it through an interactive dashboard with charts, sortable tables, and drill-down views.

This is a portfolio project built to demonstrate full-stack development, API design, data pipeline construction, and analytical reporting skills.

---

## Demo

[Check Out The Demo](https://cards.nebulouscode.com/)

---

## What It Does

- Pulls card and set metadata from [TCGdex](https://tcgdex.dev) — a free, open-source Pokémon TCG API
- Stores card data in PostgreSQL hosted on [Neon](https://neon.tech)
- Serves the data through a custom-built REST API (FastAPI)
- Presents everything in a Vue.js dashboard with a set selector, price chart, and sortable card table

---

## Stack

| Layer | Technology |
| --- | --- |
| API | Python 3.12, FastAPI, Uvicorn |
| ORM / Migrations | SQLAlchemy, Alembic |
| Database | PostgreSQL via Neon |
| Frontend | Vue 3, Vite, Vuetify 3, Chart.js |
| Package Management | uv |
| Containers | Docker / Podman |

---

## Project Status

| Milestone | Description | Status |
| --- | --- | --- |
| 1 | Minimum viable demo — full vertical slice | Complete |
| 2 | Real market pricing, price history | Complete |
| 3 | Multi-set support, analytical reporting | Complete |
| 4 | Collection upload, dashboard, Excel export | Complete |
| 5 | Upload resource caps, rate limiting, interface states | Complete |

---

## Running Locally

### Prerequisites

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) — `scoop install uv` or `pip install uv`
- A [Neon](https://neon.tech) account (free tier is sufficient)

### 1. Configure environment

```bash
cp .env.example .env
```

Fill in `DATABASE_URL` with your Neon connection string. It must include `?sslmode=require`.

### 2. Run the API

```bash
cd api
uv sync
./run.ps1      # Windows
./run.sh       # macOS / Linux
```

The API runs on [http://localhost:8151](http://localhost:8151). Alembic migrations run automatically on startup — no manual schema setup required.

### 3. Run the ingestion script

Run this once to populate the database. Safe to re-run — sets and cards are upserted.

```bash
cd ingestion
uv sync
./run_ingest.ps1 -SetId base1   # Windows
./run_ingest.sh base1           # macOS / Linux
```

### 4. Run the frontend

```bash
cd frontend
npm install
./run.ps1      # Windows
./run.sh       # macOS / Linux
```

The dashboard runs at [http://127.0.0.1:5151](http://127.0.0.1:5151).

---

## API Reference

Interactive API documentation is available while the API is running:

| | URL |
| --- | --- |
| Swagger UI | [http://localhost:8151/docs](http://localhost:8151/docs) |
| ReDoc | [http://localhost:8151/redoc](http://localhost:8151/redoc) |

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/sets` | List all sets |
| GET | `/sets/{set_id}` | Get a single set |
| GET | `/sets/{set_id}/cards` | Get all cards for a set |
| GET | `/cards/{card_id}` | Get a single card with latest prices |

---

## Deployment

Both services run on [Render](https://render.com); the database is [Neon](https://neon.tech).

| | Address |
| --- | --- |
| Dashboard | `https://cards.nebulouscode.com` |
| API | `https://card-market-api.onrender.com` |

The dashboard is served from a custom domain via a CNAME pointing at its Render service; Render provisions the TLS certificate. The API deliberately stays on its Render hostname.

That split means the browser sees two different registrable domains, so requests from the dashboard to the API are genuinely cross-origin. Two settings follow from it and must agree, or the collection upload silently stops working:

| Service | Variable | Value |
| --- | --- | --- |
| API | `FRONTEND_URL` | `https://cards.nebulouscode.com` |
| Dashboard | `VITE_API_BASE_URL` | `https://card-market-api.onrender.com` |

`FRONTEND_URL` is the origin CORS allows — scheme included, no trailing slash. The session cookie is issued `SameSite=None; Secure` for the same reason; see `_cookie_samesite()` in `api/routers/collection.py`.

The API sleeps on the free tier, so a first request after idle can take thirty seconds or more. The frontend polls `/wake` and shows a loading screen rather than hiding it.

---

## Documentation

- [Project Overview](./docs/PROJECT_OVERVIEW.md) — goals, milestones, and architecture
- [Development Setup](./docs/DEVELOPMENT_SETUP.md) — detailed setup instructions for all platforms
- [Milestone 1](./docs/MILESTONE_1.md) — scope and structure for the current milestone
- [TCGdex API Specs](./docs/tcgdex_api_specs.md) — internal reference for the TCGdex REST API
