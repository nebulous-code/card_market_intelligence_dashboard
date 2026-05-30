"""
API entry point for the Pokemon Card Market Intelligence Dashboard.

This file creates the web server application and connects all of its
pieces together: the database migration runner, the browser security
policy, and the URL route handlers.

When the server starts it automatically updates the database schema by
running any pending migrations. This means you never need to manually
run database setup commands -- just start the server and it takes care
of itself.
"""

import asyncio
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the URL route groups: sets, cards, reference data, trends, and liveness.
from routers import cards, collection, health, palette, reference, sets, trends


async def run_migrations() -> None:
    """Apply pending Alembic migrations without blocking app startup.

    Runs as a background task so the event loop serves requests -- notably
    the DB-free ``/health`` probe -- the instant uvicorn is up, instead of
    waiting on a cold database connection. On a Render free-tier wake the
    schema is already at head, so this is a fast no-op once the (also cold)
    Neon database accepts a connection. Decoupling it from startup is what
    lets the cold-start loader's wake signal return immediately rather than
    sitting behind a multi-second cold-DB connect.

    Because the app is already serving, a failure can't abort startup; it is
    surfaced loudly in the logs instead. DB-touching endpoints will error
    until the schema is fixed, but ``/health`` stays up so the frontend can
    still detect liveness.
    """
    proc = await asyncio.create_subprocess_exec(
        "alembic",
        "upgrade",
        "head",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        print(stderr.decode(), file=sys.stderr)
        print("Alembic migration failed -- see stderr above.", file=sys.stderr)
    else:
        print(stdout.decode())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown tasks.

    FastAPI calls this context manager once when the server starts. Code
    before the ``yield`` runs at startup; code after it runs at shutdown.
    Using ``lifespan`` is the modern replacement for the deprecated
    ``@app.on_event("startup")`` and ``@app.on_event("shutdown")`` decorators.

    Migrations are kicked off as a background task rather than awaited so the
    server starts accepting requests immediately -- see ``run_migrations`` for
    why this matters for the Render cold-start path.
    """
    # --- Startup ---
    # Held on app.state so the task isn't garbage-collected mid-run.
    app.state.migration_task = asyncio.create_task(run_migrations())

    yield  # Server is now running and accepting requests.

    # --- Shutdown ---
    # Stop an in-flight migration so shutdown isn't blocked waiting on it.
    task = app.state.migration_task
    if not task.done():
        task.cancel()


# Create the FastAPI application. The title and description appear in the
# automatically generated interactive documentation at /docs.
app = FastAPI(
    title="Pokemon Card Market Intelligence API",
    description="Serves card metadata and price snapshots for the dashboard.",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS).
#
# By default, browsers refuse to let a web page on one address (the frontend
# at port 5173) make requests to a different address (this API at port 8000).
# This is a browser security feature called the same-origin policy.

origins = [
    "http://localhost:5173", 
    "http://127.0.0.1:5173",
    os.environ.get("FRONTEND_URL",""),
]

# This middleware tells the browser it is safe to allow those requests.
# Both localhost and 127.0.0.1 are listed because they refer to the same
# machine but browsers treat them as different origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in origins if o],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the route groups with the application.
# Each router is a collection of related URL endpoints defined in its own file.
app.include_router(sets.router)       # handles /sets and /sets/{id}/cards
app.include_router(cards.router)      # handles /cards/{id}
app.include_router(reference.router)  # handles /reference/conditions, /reference/variants, /reference/rarities
app.include_router(trends.router)     # handles /trends/* (condition multipliers, future analyses)
app.include_router(collection.router) # handles /collection/* (template, upload, mock, session)
app.include_router(palette.router)    # handles /palette (color palette for dashboard charts)
app.include_router(health.router)     # handles /health (used by the cold-start loader)


@app.get("/", include_in_schema=False)
def root():
    """
    Root health check endpoint.

    Returns a simple confirmation that the server is running and points
    to the interactive documentation. This endpoint is hidden from the
    generated API docs since it is only useful for quick sanity checks.

    Returns:
        dict: Contains a status field set to "ok" and a docs field with
            the path to the Swagger UI documentation.
    """
    return {"status": "ok", "docs": "/docs"}
