"""Tests for the Phase I.14 enterprise hardening layer."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from graph_os.enterprise import (
    PrometheusSnapshot,
    RateLimiter,
    _percentile,
    write_backend_probe,
)


class TestRateLimiter:
    def test_allows_within_capacity(self):
        limiter = RateLimiter(capacity=5, rate_per_second=1.0)
        assert all(limiter.acquire("tool-a") for _ in range(5))

    def test_refuses_over_capacity(self):
        limiter = RateLimiter(capacity=3, rate_per_second=0.0001)
        for _ in range(3):
            assert limiter.acquire("tool-a")
        assert limiter.acquire("tool-a") is False

    def test_refills_over_time(self):
        limiter = RateLimiter(capacity=1, rate_per_second=100.0)
        assert limiter.acquire("tool-a")
        assert limiter.acquire("tool-a") is False
        time.sleep(0.05)
        assert limiter.acquire("tool-a") is True

    def test_per_key_buckets_independent(self):
        limiter = RateLimiter(capacity=1, rate_per_second=0.001)
        assert limiter.acquire("a")
        assert limiter.acquire("b")
        assert limiter.acquire("a") is False
        assert limiter.acquire("b") is False

    def test_snapshot_reports_buckets(self):
        limiter = RateLimiter(capacity=2, rate_per_second=1.0)
        limiter.acquire("x")
        snap = limiter.snapshot()
        assert "x" in snap
        assert snap["x"]["capacity"] == 2.0


class TestPrometheusSnapshot:
    def test_counter_increments(self):
        m = PrometheusSnapshot()
        m.inc_counter("edges_written")
        m.inc_counter("edges_written", 3)
        rendered = m.render()
        assert "edges_written 4" in rendered or "edges_written 4.0" in rendered

    def test_gauge_overrides(self):
        m = PrometheusSnapshot()
        m.set_gauge("queue_depth", 10)
        m.set_gauge("queue_depth", 2)
        rendered = m.render()
        assert "queue_depth 2" in rendered

    def test_timing_summary(self):
        m = PrometheusSnapshot()
        for v in (0.01, 0.02, 0.03, 0.04, 0.05):
            m.record_timing("resolve_ms", v)
        rendered = m.render()
        assert "resolve_ms_count 5" in rendered
        assert 'quantile="0.95"' in rendered

    def test_timing_cap_bounds_memory(self):
        m = PrometheusSnapshot()
        for i in range(m._timing_cap + 50):
            m.record_timing("x", 0.001)
        assert len(m._timings["x"]) == m._timing_cap

    def test_percentile_helper(self):
        assert _percentile([], 0.5) == 0.0
        assert _percentile([1.0, 2.0, 3.0], 0.5) == 2.0
        assert _percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0


class TestBackendProbe:
    def test_writes_payload(self, tmp_path):
        path = write_backend_probe(tmp_path, backend="sqlite", sqlite_schema_version=13)
        assert path.exists()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["backend"] == "sqlite"
        assert payload["sqlite_schema_version"] == 13
        assert "last_ok_at" in payload

    def test_idempotent_overwrite(self, tmp_path):
        write_backend_probe(tmp_path, backend="sqlite", sqlite_schema_version=1)
        time.sleep(0.01)
        path = write_backend_probe(tmp_path, backend="sqlite", sqlite_schema_version=2)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["backend"] == "sqlite"
        assert payload["sqlite_schema_version"] == 2


class TestBackendProbeIntegration:
    def test_get_backend_writes_probe(self, migrated_conn, tmp_path, monkeypatch):
        from graph_os.backend import get_backend

        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        backend = get_backend(backend="sqlite", sqlite_conn=migrated_conn)
        try:
            probe = tmp_path / ".graph-backend.json"
            assert probe.exists()
            payload = json.loads(probe.read_text(encoding="utf-8"))
            assert payload["backend"] == "sqlite"
        finally:
            backend.close()
