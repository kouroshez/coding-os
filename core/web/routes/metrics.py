"""core.web.routes.metrics — /metrics Prometheus text format endpoint.

PURPOSE: Expose graph_os.enterprise.metrics().render() at /metrics so
         Prometheus scrapers and `curl` can get counters + timings.
INPUT:   HTTP GET (no params).
OUTPUT:  200 text/plain Prometheus exposition format.
DEPENDENCIES: fastapi, graph_os.enterprise.metrics.
NOTES:  Returns an empty Prometheus response if enterprise is unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Render collected metrics in Prometheus text format.

    PURPOSE: Expose in-process metrics counters and timings for scraping.
    INPUT:   none.
    OUTPUT:  text/plain Prometheus exposition format string.
    DEPENDENCIES: graph_os.enterprise.metrics().render().
    NOTES:   Returns minimal stub metrics when enterprise is unavailable.
    """
    try:
        from graph_os.enterprise import metrics  # type: ignore
        return PlainTextResponse(content=metrics().render(), media_type="text/plain")
    except ImportError:
        # Enterprise not available — return a stub with a note.
        stub = (
            "# TYPE cos_web_available gauge\n"
            "cos_web_available 1\n"
            "# TYPE cos_enterprise_available gauge\n"
            "cos_enterprise_available 0\n"
        )
        return PlainTextResponse(content=stub, media_type="text/plain")
