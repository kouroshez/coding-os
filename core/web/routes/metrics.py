"""core.web.routes.metrics — /metrics Prometheus text format endpoint."""

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
    """Render collected metrics in Prometheus text format."""
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
