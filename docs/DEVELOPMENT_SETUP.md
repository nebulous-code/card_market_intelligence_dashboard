# Development Environment Setup

This project supports two development modes to accommodate machines with and without a container runtime available. Both modes connect to the same Neon-hosted PostgreSQL database — there is no local database container to manage.

---

## Modes at a Glance

| | Mode A: Containers | Mode B: Native |
|---|---|---|
| **Database** | Neon (cloud-hosted PostgreSQL) | Neon (cloud-hosted PostgreSQL) |
| **API** | Docker / Podman service | Python venv |
| **Frontend** | Docker / Podman service | `npm run dev` |
| **Requires admin?** | WSL2 must be available | No |
| **Best for** | Home machine, CI, deployment parity | Restricted machines |

---

## Prerequisites

### All Machines

- **Node.js** (v20+) — install via [Scoop](https://scoop.sh): `scoop install nodejs`
- **Python** (3.11+) — install via Scoop: `scoop install python`
- **uv** — fast Python package manager: `scoop install uv` or `pip install uv`
- A **Neon** account: [neon.tech](https://neon.tech) — the free tier is sufficient

### Mode A Only (Containers)

- **Docker** or **Podman** with Compose support
  - Docker Desktop (requires admin on Windows)
  - Podman via Scoop: `scoop install podman && scoop install podman-compose` (requires WSL2)

---

## Neon Database Setup

This is a one-time step. The same Neon instance is used across all machines and both development modes.

1. Create a free account at [neon.tech](https://neon.tech)
2. Create a new project — name it something like `pokemon-cards-dev`
3. Copy the connection string from the Neon dashboard (it will look like `postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb`)
4. Paste it as the `DATABASE_URL` value in your `.env` file (see below)

Database schema is managed with Alembic and applied automatically on API startup — no manual migration step is required.

---

## Environment Configuration

All configuration is handled through a `.env` file in the project root. A template is provided at `.env.example`.

```bash
cp .env.example .env
```

```ini
# .env.example

# --- Database ---
# Neon connection string — used in all environments
DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb

# --- Ingestion ---
POKEMONTCG_API_KEY=your_key_here

# --- Frontend ---
VITE_API_BASE_URL=http://localhost:8000
```

The `.env` file is gitignored. Never commit credentials to the repository.

---

## Mode A: Containers (Docker or Podman)

This mode runs the API, ingestion script, and frontend as containers. It is the recommended mode on machines where Docker or Podman is available and mirrors the production deployment configuration.

**Start all services:**

```bash
# Docker
docker compose up --build

# Podman
podman-compose up --build
```

**Run the ingestion script manually:**

```bash
# Docker
docker compose run ingestion uv run python run.py --set-id base1

# Podman
podman-compose run ingestion uv run python run.py --set-id base1
```

**Stop all services:**

```bash
docker compose down        # Docker
podman-compose down        # Podman
```

Services and ports:

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| API docs (ReDoc) | http://localhost:8000/redoc |

---

## Mode B: Native (No Containers)

This mode runs the API and frontend natively using a Python venv and Node. No admin access or container runtime is required. The database connection is identical to Mode A.

### Step 1 — Run the API

```bash
cd api
uv sync
uv run uvicorn main:app --reload --port 8000
```

### Step 2 — Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

### Step 3 — Run the Ingestion Script

```bash
cd ingestion
uv sync
uv run python run.py --set-id base1
```

Services and ports are the same as Mode A.

---

## Database Migrations

Migrations run automatically on API startup. To generate a new migration after modifying a SQLAlchemy model:

```bash
# From the api/ directory
uv run alembic revision --autogenerate -m "description of change"
uv run alembic upgrade head
```

---

## Notes

- The Neon free tier supports one project with up to 0.5 GB storage, which is sufficient for development and early milestone work.
- Because all machines share the same Neon instance, data ingested on one machine is immediately available on any other.
- Podman is CLI-compatible with Docker. Any `docker` command in this document can be substituted with `podman`, and `docker compose` with `podman-compose`.
- If WSL2 is not available on a restricted machine, Mode B is the only supported option on that machine.
