"""core.web._deps — FastAPI dependency factories."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path

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
    """Factory that returns a FastAPI dependency for a specific named route."""

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
    """Factory that returns a FastAPI dependency for recording per-route metrics."""

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
