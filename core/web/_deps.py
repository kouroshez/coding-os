"""core.web._deps — FastAPI dependency factories.

PURPOSE: Wire graph_os.enterprise singletons (RateLimiter, PrometheusSnapshot)
         into FastAPI as injectable dependencies.  Called per-route via
         Depends(rate_limit_dep) and Depends(metrics_dep).
INPUT:   FastAPI Request (injected by the framework).
OUTPUT:  None (raises HTTP 429 if throttled; side-effects metrics counters).
DEPENDENCIES: fastapi, graph_os.enterprise, time.
NOTES:  Rate-limit key = (route name, client IP) so two different routes
        have independent buckets. The global RateLimiter singleton is
        shared across all worker coroutines — thread-safe per enterprise.py.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, Request

# Ensure core/ is on sys.path when this module is imported directly.
_CORE_DIR = Path(__file__).resolve().parent.parent
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))


def _get_enterprise():
    """Lazy import to avoid circular deps at package load time."""
    from graph_os.enterprise import metrics, rate_limiter  # type: ignore
    return rate_limiter(), metrics()


def make_rate_limit_dep(route_name: str) -> Callable:
    """Factory that returns a FastAPI dependency for a specific named route.

    PURPOSE: Create a per-route rate-limit dependency using the enterprise
             RateLimiter singleton, keyed by (route_name, client_ip).
    INPUT:   route_name — the logical name of the route (e.g. "graph.query").
    OUTPUT:  A FastAPI dependency callable; raises HTTP 429 when throttled.
    DEPENDENCIES: graph_os.enterprise.rate_limiter().
    NOTES:   Uses Retry-After: 2 header as a simple hint. Real retry math
             would require exposing refill_rate from the bucket, which is
             out of scope for S4.
    """
    async def _dep(request: Request) -> None:
        limiter, _ = _get_enterprise()
        client_ip = request.client.host if request.client else "unknown"
        key = f"{route_name}:{client_ip}"
        if not limiter.acquire(key):
            raise HTTPException(
                status_code=429,
                detail={"error": "rate_limited", "route": route_name},
                headers={"Retry-After": "2"},
            )

    return _dep


def make_metrics_dep(route_name: str) -> Callable:
    """Factory that returns a FastAPI dependency for recording per-route metrics.

    PURPOSE: Increment cos_web_requests_total and record
             cos_web_request_duration_seconds for each request.
    INPUT:   route_name — the logical name of the route.
    OUTPUT:  A FastAPI dependency callable; records to PrometheusSnapshot.
    DEPENDENCIES: graph_os.enterprise.metrics().
    NOTES:   Uses request.state to stash the start time so the response can
             be measured. FastAPI does not support post-response hooks in
             simple dependencies; timing here captures until yield returns
             (i.e. response sent), which is sufficient for p50/p95 shapes.
    """
    async def _dep(request: Request) -> None:
        _, prom = _get_enterprise()
        prom.inc_counter(f"cos_web_requests_total{{route={route_name!r}}}")
        start = time.monotonic()
        yield
        duration = time.monotonic() - start
        prom.record_timing(
            f"cos_web_request_duration_seconds{{route={route_name!r}}}",
            duration,
        )

    return _dep
