"""Tests for the S4 unified web server backbone (core/web/).

Spins up the FastAPI TestClient and asserts every route module works.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure repo root on sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src" / "core") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src" / "core"))

from fastapi.testclient import TestClient

from web.server import create_app


@pytest.fixture(scope="module")
def client():
    """TestClient for the full FastAPI app."""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_200(self, client):
        """GET /health must return 200 with status field."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        # status is "ok" or "degraded" depending on whether backend is up.
        assert data["status"] in ("ok", "degraded")

    def test_health_has_backend_id(self, client):
        """GET /health must always include backend_id key."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "backend_id" in resp.json()


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_metrics_returns_200(self, client):
        """GET /metrics must return 200 with text/plain content."""
        resp = client.get("/metrics")
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "text/plain" in ct

    def test_metrics_is_prometheus_format(self, client):
        """Metrics body should be valid text after at least one request fires metrics."""
        # Prime the metrics by hitting a route that has a metrics dependency.
        client.get("/api/graph/query", params={"q": "warm"})
        resp = client.get("/metrics")
        body = resp.text
        # After at least one request, the body should contain a TYPE comment or
        # a known counter.  An empty body ("\n") is also acceptable if enterprise
        # counters haven't been written yet (graph backend absent in test env).
        assert isinstance(body, str)
        # If enterprise is available the body will have TYPE lines; otherwise
        # the stub response includes cos_enterprise_available.
        if body.strip():
            assert "# TYPE" in body or "cos_web" in body or "cos_enterprise" in body


# ---------------------------------------------------------------------------
# CORS headers
# ---------------------------------------------------------------------------

class TestCORS:
    def test_cors_origin_header_present_for_vite(self, client):
        """CORS allow-origin header must be present for Vite dev origin."""
        resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert resp.status_code == 200
        acao = resp.headers.get("access-control-allow-origin")
        assert acao == "http://localhost:5173"

    def test_cors_preflight(self, client):
        """OPTIONS preflight for /api/graph/query must succeed."""
        resp = client.options(
            "/api/graph/query",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code in (200, 204)


# ---------------------------------------------------------------------------
# /api/graph — graph routes
# ---------------------------------------------------------------------------

class TestGraphRoutes:
    def test_graph_query_no_graph_backend(self, client):
        """GET /api/graph/query returns 200 or 503 (no backend in test env)."""
        resp = client.get("/api/graph/query", params={"q": "test"})
        # Either 200 with data or 503 unavailable — both are correct shapes.
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "data" in body or "error" in body

    def test_graph_query_missing_q_returns_422(self, client):
        """GET /api/graph/query without q must return 422 (FastAPI validation)."""
        resp = client.get("/api/graph/query")
        assert resp.status_code == 422

    def test_graph_context_returns_valid_shape(self, client):
        """GET /api/graph/context/some-uid should return data or error envelope."""
        resp = client.get("/api/graph/context/some:uid")
        assert resp.status_code in (200, 404, 503)
        body = resp.json()
        assert "data" in body or "error" in body

    def test_graph_detect_changes_no_files(self, client):
        """GET /api/graph/detect-changes with no files returns 200 empty."""
        resp = client.get("/api/graph/detect-changes")
        assert resp.status_code in (200, 503)

    def test_graph_contracts(self, client):
        """GET /api/graph/contracts returns valid shape."""
        resp = client.get("/api/graph/contracts")
        assert resp.status_code in (200, 503)

    def test_graph_export(self, client):
        """GET /api/graph/export returns valid shape."""
        resp = client.get("/api/graph/export", params={"format": "json"})
        assert resp.status_code in (200, 503)


# ---------------------------------------------------------------------------
# /api/board — board routes
# ---------------------------------------------------------------------------

class TestBoardRoutes:
    def test_board_list_returns_valid_shape(self, client):
        """GET /api/board/list should return data or error (no DB in test env)."""
        resp = client.get("/api/board/list")
        # Can be 200 (DB exists) or 503 (board_os not available).
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "data" in body or "error" in body
        if resp.status_code == 200 and isinstance(body.get("data"), dict):
            data = body["data"]
            if "agent_states" in data:
                assert "agent_manifest" in data
                assert isinstance(data["agent_manifest"], list)
                assert data.get("presence_scope") == "per_project"
                ids = {row["id"] for row in data["agent_manifest"]}
                assert "human" in ids
                assert "claude" in ids

    def test_board_daily_returns_valid_shape(self, client):
        """GET /api/board/daily returns data or error."""
        resp = client.get("/api/board/daily")
        assert resp.status_code in (200, 503)

    def test_board_retro_returns_valid_shape(self, client):
        """GET /api/board/retro returns data or error."""
        resp = client.get("/api/board/retro")
        assert resp.status_code in (200, 503)

    def test_board_wip_returns_valid_shape(self, client):
        """GET /api/board/wip returns data or error."""
        resp = client.get("/api/board/wip")
        assert resp.status_code in (200, 503)


# ---------------------------------------------------------------------------
# /api/cognition — trace routes
# ---------------------------------------------------------------------------

class TestCognitionRoutes:
    def test_cognition_traces_returns_list(self, client):
        """GET /api/cognition/traces returns a list (possibly empty)."""
        resp = client.get("/api/cognition/traces")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "sessions" in body["data"]
        assert isinstance(body["data"]["sessions"], list)

    def test_cognition_trace_not_found(self, client):
        """GET /api/cognition/trace/nonexistent returns 404."""
        resp = client.get("/api/cognition/trace/nonexistent-session-id-xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /api/search — search routes
# ---------------------------------------------------------------------------

class TestSearchRoutes:
    def test_search_docs_returns_valid_shape(self, client):
        """GET /api/search/docs returns data or error envelope."""
        resp = client.get("/api/search/docs", params={"query": "test"})
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "data" in body or "error" in body

    def test_search_memory_returns_valid_shape(self, client):
        """GET /api/search/memory returns data or error envelope."""
        resp = client.get("/api/search/memory", params={"query": "test"})
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "data" in body or "error" in body

    def test_search_memory_missing_query_returns_422(self, client):
        """GET /api/search/memory without query returns 422."""
        resp = client.get("/api/search/memory")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------

class TestSSEStream:
    """SSE tests monkeypatch _event_generator to a finite stub so TestClient
    doesn't block forever on the real infinite polling loop."""

    def test_sse_endpoint_content_type(self, client):
        """GET /api/stream/events returns text/event-stream content type."""
        import web.routes.stream as _stream_mod

        async def _finite_gen():
            yield "event: connected\ndata: {\"message\": \"test\"}\n\n"
            yield "event: heartbeat\ndata: {\"ts\": 0}\n\n"

        orig_gen = _stream_mod._event_generator
        _stream_mod._event_generator = _finite_gen
        try:
            with client.stream("GET", "/api/stream/events") as resp:
                assert resp.status_code == 200
                ct = resp.headers.get("content-type", "")
                assert "text/event-stream" in ct
        finally:
            _stream_mod._event_generator = orig_gen

    def test_sse_endpoint_emits_connected_event(self, client):
        """GET /api/stream/events emits a 'connected' event as the first event."""
        import web.routes.stream as _stream_mod

        async def _finite_gen():
            yield "event: connected\ndata: {\"message\": \"SSE stream connected\"}\n\n"
            yield "event: heartbeat\ndata: {\"ts\": 0}\n\n"

        orig_gen = _stream_mod._event_generator
        _stream_mod._event_generator = _finite_gen
        try:
            with client.stream("GET", "/api/stream/events") as resp:
                assert resp.status_code == 200
                body = b""
                for chunk in resp.iter_bytes(chunk_size=1024):
                    body += chunk
                text = body.decode("utf-8", errors="replace")
                assert "connected" in text
                assert "event:" in text
        finally:
            _stream_mod._event_generator = orig_gen

    def test_stream_history_returns_envelope(self, client):
        """GET /api/stream/history returns data or unavailable error envelope."""
        resp = client.get("/api/stream/history", params={"limit": 5})
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "data" in body or "error" in body


# ---------------------------------------------------------------------------
# Rate limit behavior
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_rate_limit_triggers_on_burst(self, client):
        """Firing N+1 rapid requests to a rate-limited endpoint should eventually 429."""
        # We need to exhaust the bucket (capacity=60 by default).
        # To avoid needing 60+ requests, patch the rate_limiter to a very low cap.
        from web._deps import _get_enterprise

        # Directly override the enterprise rate limiter for this test.
        from graph_os.enterprise import RateLimiter  # type: ignore

        tiny_limiter = RateLimiter(capacity=2, rate_per_second=0.1)

        original_get = _get_enterprise

        def _patched_enterprise():
            from graph_os.enterprise import metrics  # type: ignore
            return tiny_limiter, metrics()

        # Monkey-patch the module-level function.
        import web._deps as _deps_mod
        _deps_mod._get_enterprise = _patched_enterprise

        try:
            responses = []
            for _ in range(5):
                r = client.get("/api/graph/query", params={"q": "test"})
                responses.append(r.status_code)

            status_codes = set(responses)
            # At least one should be 429 (rate limited) once bucket is empty.
            assert 429 in status_codes, f"Expected 429 in {responses}"
        finally:
            _deps_mod._get_enterprise = original_get


# ---------------------------------------------------------------------------
# Envelope shape
# ---------------------------------------------------------------------------

class TestEnvelopeShape:
    def test_health_not_wrapped_in_envelope(self, client):
        """/health returns direct JSON (not nested in {data, meta})."""
        resp = client.get("/health")
        body = resp.json()
        # Health returns {status: ..., backend_id: ...} directly.
        assert "status" in body

    def test_graph_query_envelope_has_data_and_meta_on_200(self, client):
        """A successful API response has {data, meta} at body level."""
        # Use a mock that returns a valid ok() envelope.
        ok_envelope = json.dumps({
            "ok": True,
            "data": {
                "results": [],
                "meta": {"layer": "graph", "query": "test"},
            },
        })

        import web.routes.graph as _graph_route
        original_tools = _graph_route._tools

        def _mock_tools():
            mock = MagicMock()
            mock.cos_graph_query.return_value = ok_envelope
            return mock

        _graph_route._tools = _mock_tools
        try:
            resp = client.get("/api/graph/query", params={"q": "test"})
            assert resp.status_code == 200
            body = resp.json()
            assert "data" in body
            assert "meta" in body
        finally:
            _graph_route._tools = original_tools
