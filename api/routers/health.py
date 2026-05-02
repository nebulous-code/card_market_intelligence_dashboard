"""
Liveness probe used by the cold-start loader on the frontend.

Render's free tier spins the API service down after ~15 minutes of inactivity,
and a wake-up takes ~30 seconds. The frontend polls /health to know when the
server is responsive and uses that signal to swap a full-screen loading
animation out for the real app shell.

This endpoint deliberately avoids the database. A cold database can take
just as long to come back online as the API itself, and we want a clean
"the server is up" signal even before the DB is ready -- skeleton loaders
inside views handle the data-arriving phase separately.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return a static OK payload. No DB access."""
    return {"status": "ok"}
