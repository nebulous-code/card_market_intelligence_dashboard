"""
FastAPI application entry point.

On startup, Alembic migrations are run automatically so the database schema
is always up to date without a manual migration step.
"""

import subprocess
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import cards, sets

app = FastAPI(
    title="Pokémon Card Market Intelligence API",
    description="Serves card metadata and price snapshots for the dashboard.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sets.router)
app.include_router(cards.router)


@app.on_event("startup")
def run_migrations():
    """Run `alembic upgrade head` before the app begins accepting requests."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Alembic migration failed — see stderr above.")
    print(result.stdout)


@app.get("/", include_in_schema=False)
def root():
    return {"status": "ok", "docs": "/docs"}
