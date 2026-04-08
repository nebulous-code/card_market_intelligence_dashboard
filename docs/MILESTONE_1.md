# Milestone 1 — Architecture and Structure

This document covers the technical structure for Milestone 1: the minimum viable demo. The goal is a single vertical slice of the full system with every layer of the stack represented in working form — data ingestion, API, database, and frontend.

---

## Stack

| Layer | Technology |
| --- | --- |
| API | Python, FastAPI, Uvicorn |
| ORM | SQLAlchemy + Alembic |
| Database | PostgreSQL via [Neon](https://neon.tech) |
| Frontend | Vue.js, Vite, Axios |
| UI Components | Vuetify |
| Charts | Chart.js via vue-chartjs |
| Containers | Docker / Podman |

### Database

PostgreSQL is hosted on Neon for all environments — development, restricted machines, and eventually production. There is no local database container. All services connect to Neon via a `DATABASE_URL` environment variable, which means the development database is persistent and shared across machines without any additional setup.

### Containers

Docker Compose (or Podman Compose as a drop-in alternative) manages three services: the API, the ingestion script, and the frontend. On machines where a container runtime is not available, all three run natively with no change to the connection targets or configuration. See [DEVELOPMENT_SETUP.md](./DEVELOPMENT_SETUP.md) for full instructions on both modes.

### Frontend Libraries

Vuetify is used as the component library for layout, navigation, tables, and UI primitives. Chart.js is used for data visualization via the `vue-chartjs` wrapper, which provides a thin Vue-native interface over Chart.js. The two libraries are complementary and do not overlap — Vuetify handles structure and components, vue-chartjs handles charts.

---

## Repository Structure

``` markdown
/
├── docker-compose.yml
├── .env.example
├── README.md
├── docs/
│   ├── PROJECT_OVERVIEW.md
│   ├── DEVELOPMENT_SETUP.md
│   └── MILESTONE_1.md
│
├── api/                        # FastAPI application
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # App entry point
│   ├── database.py             # SQLAlchemy engine and session
│   ├── alembic/                # Database migrations
│   ├── models/
│   │   ├── card.py
│   │   └── set.py
│   ├── routers/
│   │   ├── sets.py
│   │   └── cards.py
│   └── schemas/
│       ├── card.py
│       └── set.py
│
├── ingestion/                  # Data ingestion scripts
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── run.py                  # Entry point
│   ├── pokemontcg.py           # pokemontcg.io API client
│   └── loader.py               # Transforms and writes to the database
│
└── frontend/                   # Vue.js application
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── main.js
        ├── App.vue
        ├── router/
        │   └── index.js
        ├── api/
        │   └── index.js        # Axios service layer
        ├── views/
        │   └── Dashboard.vue
        └── components/
            ├── SetSummaryCard.vue
            ├── CardTable.vue
            └── PriceChart.vue
```

---

## Docker Compose Services

Three services are defined. The database is not a service — it is always Neon.

| Service | Description |
| --- | --- |
| `api` | FastAPI served via Uvicorn. Connects to Neon via `DATABASE_URL`. Runs Alembic migrations on startup. |
| `ingestion` | Runs on demand via `docker compose run ingestion`. Pulls data from pokemontcg.io and writes to the same Neon instance. |
| `frontend` | Vue dev server. Proxies API requests to the `api` service. |

---

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/sets` | List all sets in the database |
| GET | `/sets/{set_id}` | Get a single set with metadata |
| GET | `/sets/{set_id}/cards` | Get all cards for a set |
| GET | `/cards/{card_id}` | Get a single card with its latest price snapshot |

Interactive API documentation is available at `/docs` (Swagger UI) and `/redoc` when the API is running.

---

## Ingestion

Data ingestion is triggered manually via the CLI for Milestone 1. The ingestion script is intentionally not exposed as an API endpoint at this stage — doing so would create an unprotected attack surface on a public repository with no meaningful benefit during development. An authenticated ingestion endpoint is planned as part of Milestone 5.

To trigger an ingest, run the script directly with a set ID argument:

```bash
# Docker / Podman
docker compose run ingestion python run.py --set-id base1

# Native
python run.py --set-id base1
```

The Base Set (`base1`) is the target set for Milestone 1.

---

## Database Schema

Three tables are defined for Milestone 1. The schema is managed with Alembic and applied automatically on API startup.

### `sets`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT | Primary key — pokemontcg.io set ID |
| `name` | TEXT | |
| `series` | TEXT | |
| `printed_total` | INT | Total cards in the printed set |
| `release_date` | DATE | |
| `symbol_url` | TEXT | |
| `logo_url` | TEXT | |
| `created_at` | TIMESTAMP | |

### `cards`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | TEXT | Primary key — pokemontcg.io card ID |
| `set_id` | TEXT | Foreign key → `sets.id` |
| `name` | TEXT | |
| `number` | TEXT | Card number within the set |
| `rarity` | TEXT | |
| `supertype` | TEXT | Pokémon, Trainer, Energy |
| `image_url` | TEXT | |
| `created_at` | TIMESTAMP | |

### `price_snapshots`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | SERIAL | Primary key |
| `card_id` | TEXT | Foreign key → `cards.id` |
| `source` | TEXT | e.g. `tcgplayer`, `ebay` |
| `condition` | TEXT | `normal`, `holofoil`, `reverseHolofoil` |
| `market_price` | NUMERIC(10,2) | |
| `low_price` | NUMERIC(10,2) | |
| `high_price` | NUMERIC(10,2) | |
| `captured_at` | TIMESTAMP | When the snapshot was taken |

The `price_snapshots` table is append-only. Snapshots are never updated in place, which preserves the full price history needed for trend analysis in later milestones.

---

## Frontend — Dashboard View

The Milestone 1 dashboard is a single page with three components:

| Component | Description |
| --- | --- |
| `SetSummaryCard` | Displays set name, series, card count, release date, and logo |
| `PriceChart` | Bar or line chart of average card prices across the set |
| `CardTable` | Paginated, sortable table of cards with name, rarity, and latest market price |

The set displayed is selectable, allowing any ingested set to be explored without requiring code changes.
