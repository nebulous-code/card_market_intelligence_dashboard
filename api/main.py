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

import subprocess
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the two sets of URL routes: one for sets, one for cards.
from routers import cards, sets

# Create the FastAPI application. The title and description appear in the
# automatically generated interactive documentation at /docs.
app = FastAPI(
    title="Pokemon Card Market Intelligence API",
    description="Serves card metadata and price snapshots for the dashboard.",
    version="1.0.0",
)

# Configure Cross-Origin Resource Sharing (CORS).
#
# By default, browsers refuse to let a web page on one address (the frontend
# at port 5173) make requests to a different address (this API at port 8000).
# This is a browser security feature called the same-origin policy.
#
# This middleware tells the browser it is safe to allow those requests.
# Both localhost and 127.0.0.1 are listed because they refer to the same
# machine but browsers treat them as different origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register the route groups with the application.
# Each router is a collection of related URL endpoints defined in its own file.
app.include_router(sets.router)   # handles /sets and /sets/{id}/cards
app.include_router(cards.router)  # handles /cards/{id}


@app.on_event("startup")
def run_migrations():
    """
    Apply any pending database migrations before the server accepts requests.

    This function is called automatically by FastAPI at startup. It runs
    the Alembic tool to compare the current database schema against the
    migration scripts and applies anything that has not been applied yet.

    Think of it like a software update check that runs every time the
    server boots -- if everything is already up to date, it does nothing.

    Raises:
        RuntimeError: Raised if the migration command exits with a non-zero
            return code, which means something went wrong. The server will
            refuse to start so it does not run against a broken schema.
    """
    # Call the Alembic command line tool as a subprocess.
    # "upgrade head" means: bring the database up to the latest version.
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )

    # A non-zero return code means the migration failed.
    # Print the error output and stop the server rather than continuing
    # with a potentially broken or outdated database schema.
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("Alembic migration failed -- see stderr above.")

    # Print whatever Alembic reported so it shows up in the server logs.
    print(result.stdout)


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
