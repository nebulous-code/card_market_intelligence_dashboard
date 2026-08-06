"""Unit tests for ``middleware.rate_limit``.

The limiter is tested directly with an injected clock rather than
through the app with sleeps, so window boundaries can be asserted
exactly and the suite stays fast. Integration through the real app is
covered at the end.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware import rate_limit
from middleware.rate_limit import (
    LIMITED_PATHS,
    RateLimiter,
    RateLimitMiddleware,
    client_key,
    max_requests,
    window_seconds,
)


class _Clock:
    """Manually advanced monotonic clock."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _scope(path="/collection/upload", headers=None, client=("10.0.0.1", 1234)):
    return {
        "type": "http",
        "path": path,
        "headers": headers or [],
        "client": client,
    }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_MAX_REQUESTS", raising=False)
    monkeypatch.delenv("RATE_LIMIT_WINDOW_SECONDS", raising=False)
    assert max_requests() == 10
    assert window_seconds() == 600


@pytest.mark.parametrize("bad", ["", "  ", "abc", "0", "-1"])
def test_malformed_config_falls_back(monkeypatch, bad):
    """A typo must not silently disable the limiter or set it to zero,
    which would reject every request."""
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", bad)
    assert max_requests() == 10


def test_config_is_overridable(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "30")
    assert window_seconds() == 30


# ---------------------------------------------------------------------------
# Client identification
# ---------------------------------------------------------------------------


def test_client_key_prefers_forwarded_header():
    """Behind Render's proxy the socket peer is always the proxy, so
    keying on it would throttle every user as a single client."""
    scope = _scope(headers=[(b"x-forwarded-for", b"203.0.113.7")])
    assert client_key(scope) == "203.0.113.7"


def test_client_key_takes_first_hop_of_the_chain():
    scope = _scope(headers=[(b"x-forwarded-for", b"203.0.113.7, 70.41.3.18, 10.0.0.1")])
    assert client_key(scope) == "203.0.113.7"


def test_client_key_ignores_blank_forwarded_header():
    scope = _scope(headers=[(b"x-forwarded-for", b"   ")])
    assert client_key(scope) == "10.0.0.1"


def test_client_key_falls_back_to_socket_peer():
    """The local development case, where no proxy is in front."""
    assert client_key(_scope()) == "10.0.0.1"


def test_client_key_handles_missing_client():
    assert client_key(_scope(client=None)) == "unknown"


# ---------------------------------------------------------------------------
# Window behaviour
# ---------------------------------------------------------------------------


def test_allows_up_to_the_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "3")
    limiter = RateLimiter(clock=_Clock())
    assert [limiter.check("a")[0] for _ in range(3)] == [True, True, True]


def test_blocks_past_the_limit(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "3")
    limiter = RateLimiter(clock=_Clock())
    for _ in range(3):
        limiter.check("a")
    allowed, retry_after = limiter.check("a")
    assert allowed is False
    assert retry_after > 0


def test_clients_are_counted_separately():
    limiter = RateLimiter(clock=_Clock())
    for _ in range(10):
        limiter.check("noisy")
    assert limiter.check("quiet")[0] is True


def test_window_slides_rather_than_resetting(monkeypatch):
    """A fixed window would let a caller spend a full allowance at the
    end of one window and another immediately after the boundary --
    double the intended burst. A sliding window frees capacity only as
    individual hits age out.
    """
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    clock = _Clock()
    limiter = RateLimiter(clock=clock)

    limiter.check("a")            # t=0
    clock.advance(30)
    limiter.check("a")            # t=30
    assert limiter.check("a")[0] is False

    clock.advance(31)             # t=61, first hit has aged out
    assert limiter.check("a")[0] is True
    # The t=30 hit is still inside the window, so capacity is not fully
    # restored -- this is the property a fixed window would violate.
    assert limiter.check("a")[0] is False


def test_retry_after_reflects_time_until_capacity(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "1")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    clock = _Clock()
    limiter = RateLimiter(clock=clock)
    limiter.check("a")
    clock.advance(50)
    _, retry_after = limiter.check("a")
    assert 1 <= retry_after <= 11


def test_expired_clients_are_evicted(monkeypatch):
    """The store is keyed by a caller-supplied header, so it must not
    grow without bound -- an attacker could rotate the header to drive
    a memory leak deliberately."""
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    clock = _Clock()
    limiter = RateLimiter(clock=clock)
    for i in range(50):
        limiter.check(f"client-{i}")
    assert len(limiter._hits) == 50

    clock.advance(61)
    limiter.check("someone-new")
    assert len(limiter._hits) == 1


def test_tracked_client_ceiling_is_enforced(monkeypatch):
    """Eviction on expiry is not enough on its own: a burst of distinct
    keys inside one window would still grow the store without bound, so
    there is a hard ceiling as well."""
    monkeypatch.setattr(rate_limit, "_MAX_TRACKED_CLIENTS", 5)
    limiter = RateLimiter(clock=_Clock())
    for i in range(20):
        limiter.check(f"client-{i}")
    assert len(limiter._hits) <= 6


def test_reset_clears_state():
    limiter = RateLimiter(clock=_Clock())
    limiter.check("a")
    limiter.reset()
    assert limiter._hits == {}


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def _app_with_limiter(limiter):
    app = FastAPI()

    @app.post("/collection/upload")
    def upload():
        return {"ok": True}

    @app.get("/sets")
    def sets():
        return {"ok": True}

    app.add_middleware(RateLimitMiddleware, limiter=limiter)
    return TestClient(app)


def test_middleware_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "2")
    client = _app_with_limiter(RateLimiter(clock=_Clock()))

    assert client.post("/collection/upload").status_code == 200
    assert client.post("/collection/upload").status_code == 200

    blocked = client.post("/collection/upload")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert int(blocked.headers["Retry-After"]) > 0
    assert "Too many uploads" in blocked.json()["detail"]


def test_middleware_leaves_read_endpoints_alone(monkeypatch):
    """Reads are cheap and cached. Throttling them would break browsing
    for anyone who merely clicks around quickly."""
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "1")
    client = _app_with_limiter(RateLimiter(clock=_Clock()))
    for _ in range(10):
        assert client.get("/sets").status_code == 200


def test_limited_paths_match_the_real_write_endpoints():
    """Guards against the path set drifting away from the router."""
    assert LIMITED_PATHS == {
        "/collection/upload",
        "/collection/upload/annotated",
        "/collection/mock",
    }


def test_429_from_the_real_app_carries_cors_headers(client, monkeypatch):
    """Regression guard on middleware ordering.

    Starlette's ``add_middleware`` inserts at position 0, so the last
    middleware registered is the outermost. If the limiter is registered
    after CORS it wraps it, and the 429 goes out with no
    Access-Control-Allow-Origin -- the browser then reports an opaque
    network failure and the frontend never sees the status or the
    message. This asserts the order that makes the 429 usable.
    """
    monkeypatch.setenv("RATE_LIMIT_MAX_REQUESTS", "1")
    origin = {"Origin": "http://localhost:5151"}
    garbage = {"file": ("x.txt", b"not a workbook", "text/plain")}

    # The first call is rejected by the upload guard, which is fine --
    # what matters is that the limiter counted it, so the second call is
    # throttled. Using a payload that needs no database data keeps this
    # test about middleware ordering and nothing else.
    assert client.post("/collection/upload", files=garbage, headers=origin).status_code == 422
    blocked = client.post("/collection/upload", files=garbage, headers=origin)

    assert blocked.status_code == 429
    assert blocked.headers["access-control-allow-origin"] == "http://localhost:5151"
    # And the wait time must be readable by cross-origin JS, which it is
    # not unless CORS explicitly exposes it.
    assert "retry-after" in blocked.headers
    assert "Retry-After" in blocked.headers["access-control-expose-headers"]


def test_non_http_scopes_pass_through():
    """Lifespan and websocket scopes have no path and must not be
    inspected as if they did."""
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    middleware = RateLimitMiddleware(app, limiter=RateLimiter(clock=_Clock()))
    import asyncio

    asyncio.run(middleware({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]
