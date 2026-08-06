"""Unit tests for ``middleware.body_limit``.

The point of this middleware is *when* it runs, not what it decides:
``read_capped`` already rejects oversized uploads, but only after
Starlette has spooled the whole body. These tests assert the header
inspection and the path scoping; the timing benefit is verified by hand
against a running server.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.body_limit import (
    GUARDED_PATHS,
    ContentLengthLimitMiddleware,
    declared_length,
)


def _scope(headers):
    return {"type": "http", "path": "/collection/upload", "headers": headers}


def _client():
    app = FastAPI()

    @app.post("/collection/upload")
    async def upload():
        return {"ok": True}

    @app.post("/collection/mock")
    async def mock():
        return {"ok": True}

    app.add_middleware(ContentLengthLimitMiddleware)
    return TestClient(app)


# ---------------------------------------------------------------------------
# declared_length
# ---------------------------------------------------------------------------


def test_reads_content_length():
    assert declared_length(_scope([(b"content-length", b"4096")])) == 4096


def test_missing_content_length_is_none():
    assert declared_length(_scope([(b"content-type", b"text/plain")])) is None


def test_unparseable_content_length_is_none():
    """A malformed header must not raise inside middleware, where there
    is no handler to convert the error into a response."""
    assert declared_length(_scope([(b"content-length", b"banana")])) is None


# ---------------------------------------------------------------------------
# Middleware behaviour
# ---------------------------------------------------------------------------


def test_rejects_oversized_upload_on_headers_alone(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(1024 * 1024))
    response = _client().post("/collection/upload", content=b"x" * (2 * 1024 * 1024))
    assert response.status_code == 413
    assert "1 MB limit" in response.json()["detail"]


def test_allows_an_upload_within_the_limit(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(1024 * 1024))
    assert _client().post("/collection/upload", content=b"x" * 100).status_code == 200


def test_passes_through_when_content_length_is_absent(monkeypatch):
    """Chunked transfer encoding sends no Content-Length. The request
    must reach read_capped, which counts real bytes, rather than being
    waved through *or* rejected on a header that does not exist."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")

    def chunks():
        yield b"xxxxxxxxxxxxxxxxxxxx"

    response = _client().post("/collection/upload", content=chunks())
    assert response.status_code == 200


def test_ignores_unguarded_paths(monkeypatch):
    """/collection/mock takes no file, so a large body on it is not the
    thing this guard is for."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "10")
    assert _client().post("/collection/mock", content=b"x" * 5000).status_code == 200


def test_non_http_scopes_pass_through():
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    middleware = ContentLengthLimitMiddleware(app)
    import asyncio

    asyncio.run(middleware({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_guarded_paths_are_the_file_accepting_endpoints():
    """Guards against the set drifting from the router. /collection/mock
    is deliberately absent -- it reads a bundled file, not an upload."""
    assert GUARDED_PATHS == {
        "/collection/upload",
        "/collection/upload/annotated",
    }
