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


def _init_job_funnel() -> str:
    """Init-job funnel counters (TASK-362); empty string when unavailable."""
    try:
        from web.init_jobs import render_counters  # type: ignore

        return render_counters()
    except Exception:
        return ""


@router.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics():
    """Render collected metrics in Prometheus text format."""
    try:
        from graph_os.enterprise import metrics  # type: ignore

        body = metrics().render()
    except ImportError:
        # Enterprise not available — return a stub with a note.
        body = (
            "# TYPE cos_web_available gauge\n"
            "cos_web_available 1\n"
            "# TYPE cos_enterprise_available gauge\n"
            "cos_enterprise_available 0\n"
        )
    return PlainTextResponse(content=body + _init_job_funnel(), media_type="text/plain")
