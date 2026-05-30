"""
Liveness probe used by the cold-start loader on the frontend.

Render's free tier spins the API service down after ~15 minutes of inactivity,
and a wake-up takes ~30 seconds. The frontend polls /wake to know when the
server is responsive and uses that signal to swap a full-screen loading
animation out for the real app shell.

The path is /wake rather than something more conventional like /health
because common ad-blocker filter lists block well-known liveness paths on
shared hosts (uBlock Origin's lists hit /health on *.onrender.com). /wake
is uncommon enough not to be on those lists today.

This endpoint deliberately avoids the database. A cold database can take
just as long to come back online as the API itself, and we want a clean
"the server is up" signal even before the DB is ready -- skeleton loaders
inside views handle the data-arriving phase separately.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/wake")
def wake() -> dict[str, str]:
    """Return a static OK payload. No DB access."""
    return {"status": "ok"}
