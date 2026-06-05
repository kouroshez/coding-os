"""Tests for the redis analyze_info.py INFO summarizer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "core" / "skills" / "redis" / "scripts"))

import analyze_info as ai  # noqa: E402


def test_parse_skips_comments_and_blanks() -> None:
    fields = ai.parse_info("# Server\r\nredis_version:8.8.0\n\nused_memory_human:1.2M\n")
    assert fields["redis_version"] == "8.8.0"
    assert fields["used_memory_human"] == "1.2M"
    assert "# Server" not in fields


def test_healthy_cache_is_clean() -> None:
    fields = {"keyspace_hits": "9000", "keyspace_misses": "1000",
              "maxmemory_policy": "allkeys-lru", "evicted_keys": "0"}
    _metrics, flags = ai.analyze(fields, 0.80)
    assert flags == []


def test_low_hit_rate_flagged() -> None:
    fields = {"keyspace_hits": "500", "keyspace_misses": "9500",
              "maxmemory_policy": "allkeys-lru", "evicted_keys": "0"}
    metrics, flags = ai.analyze(fields, 0.80)
    assert metrics["hit_rate"] is not None and metrics["hit_rate"] < 0.8
    assert any("low hit rate" in f for f in flags)


def test_evictions_under_noeviction_flagged() -> None:
    fields = {"keyspace_hits": "1", "keyspace_misses": "0",
              "maxmemory_policy": "noeviction", "evicted_keys": "42"}
    _metrics, flags = ai.analyze(fields, 0.80)
    assert any("noeviction" in f for f in flags)


def test_hit_rate_none_when_no_traffic() -> None:
    fields = {"keyspace_hits": "0", "keyspace_misses": "0",
              "maxmemory_policy": "allkeys-lru", "evicted_keys": "0"}
    metrics, flags = ai.analyze(fields, 0.80)
    assert metrics["hit_rate"] is None
    assert flags == []
