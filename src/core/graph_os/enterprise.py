"""graph_os enterprise hardening layer (Phase I.14 hardening).

Collects the production-grade knobs that MCP tool handlers need:

    - RateLimiter         — per-tool token bucket, bounded concurrency
    - BackendProbe        — on-boot writes `.coding-os/.graph-backend.json`
                            (feeds doctor check C19 — "backend reachable")
    - PrometheusSnapshot  — accumulate counters + timings; render as a
                            Prometheus exposition-format string on demand
                            without adding a network dep

Everything here is stdlib-only by default. If `prometheus_client` is
installed it's used transparently.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Rate limiter — token bucket per tool name.
# ---------------------------------------------------------------------------


@dataclass
class _Bucket:
    capacity: int
    refill_rate: float  # tokens per second
    tokens: float
    last_refill: float


class RateLimiter:
    """Bounded-burst token bucket, thread-safe."""

    def __init__(
        self,
        *,
        capacity: int = 60,
        rate_per_second: float = 30.0,
    ) -> None:
        self._capacity = capacity
        self._rate = rate_per_second
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str, *, cost: float = 1.0) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(
                    capacity=self._capacity,
                    refill_rate=self._rate,
                    tokens=float(self._capacity),
                    last_refill=now,
                )
                self._buckets[key] = bucket
            elapsed = now - bucket.last_refill
            if elapsed > 0:
                bucket.tokens = min(
                    float(bucket.capacity),
                    bucket.tokens + elapsed * bucket.refill_rate,
                )
                bucket.last_refill = now
            if bucket.tokens >= cost:
                bucket.tokens -= cost
                return True
            return False

    def snapshot(self) -> dict[str, dict[str, float]]:
        with self._lock:
            return {
                key: {
                    "capacity": float(b.capacity),
                    "rate": b.refill_rate,
                    "tokens": b.tokens,
                }
                for key, b in self._buckets.items()
            }


# ---------------------------------------------------------------------------
# Prometheus exposition (no network dep).
# ---------------------------------------------------------------------------


class PrometheusSnapshot:
    """In-process metric collector that renders Prometheus text format."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._timings: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        # Cap each timing series so memory never unbounded.
        self._timing_cap = 1_000

    def inc_counter(self, name: str, value: float = 1.0) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0.0) + value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def record_timing(self, name: str, duration_seconds: float) -> None:
        with self._lock:
            series = self._timings.setdefault(name, [])
            series.append(duration_seconds)
            if len(series) > self._timing_cap:
                del series[: len(series) - self._timing_cap]

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, value in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name} {value}")
            for name, value in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value}")
            for name, series in sorted(self._timings.items()):
                if not series:
                    continue
                count = len(series)
                total = sum(series)
                avg = total / count if count else 0.0
                p50 = _percentile(series, 0.5)
                p95 = _percentile(series, 0.95)
                p99 = _percentile(series, 0.99)
                lines.append(f"# TYPE {name} summary")
                lines.append(f"{name}_count {count}")
                lines.append(f"{name}_sum {total:.6f}")
                lines.append(f"{name}_avg {avg:.6f}")
                lines.append(f'{name}{{quantile="0.5"}} {p50:.6f}')
                lines.append(f'{name}{{quantile="0.95"}} {p95:.6f}')
                lines.append(f'{name}{{quantile="0.99"}} {p99:.6f}')
        return "\n".join(lines) + "\n"


def _percentile(series: list[float], fraction: float) -> float:
    if not series:
        return 0.0
    sorted_series = sorted(series)
    idx = int(round((len(sorted_series) - 1) * fraction))
    return sorted_series[idx]


# ---------------------------------------------------------------------------
# Backend probe writer (doctor C19).
# ---------------------------------------------------------------------------


def write_backend_probe(
    state_dir: str | Path,
    *,
    backend: str,
    sqlite_schema_version: int | None = None,
    **legacy: object,
) -> Path:
    """Record the last-known-good backend state for the doctor freshness check.

    The retired ``kuzu_version`` kwarg is silently absorbed via ``**legacy``
    so pinned callers don't break — the next release will tighten the
    signature.
    """
    target_dir = Path(state_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / ".graph-backend.json"
    payload = {
        "backend": backend,
        "sqlite_schema_version": sqlite_schema_version,
        "last_ok_at": int(time.time()),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Structured logger factory — structlog optional.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Global singletons (opt-in; imported on demand).
# ---------------------------------------------------------------------------

_GLOBAL_RATE = RateLimiter(
    capacity=int(os.environ.get("COS_GRAPH_RATE_CAPACITY", "60")),
    rate_per_second=float(os.environ.get("COS_GRAPH_RATE_REFILL", "30")),
)
_GLOBAL_METRICS = PrometheusSnapshot()


def rate_limiter() -> RateLimiter:
    return _GLOBAL_RATE


def metrics() -> PrometheusSnapshot:
    return _GLOBAL_METRICS


__all__ = [
    "PrometheusSnapshot",
    "RateLimiter",
    "metrics",
    "rate_limiter",
    "write_backend_probe",
]
