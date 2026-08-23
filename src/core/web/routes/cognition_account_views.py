"""Provider quota view on /api/cognition.

The companion to the cost view, and on a subscription the more useful half: the
dollar figure there is notional, while the percentages here are the budget the
operator actually spends. Read-only, and every number comes from the provider's
own on-disk state through the adapter that owns it — this module normalizes and
reports, and reports nothing when a provider has said nothing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import Depends

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from ._cognition_base import router

logger = logging.getLogger(__name__)


def _collect() -> list[dict]:
    from thinking_os.account_status import collect_account_status
    from web._project_context import current_project_root

    return collect_account_status(current_project_root())


@router.get("/quota")
def provider_quota(
    _rl=Depends(make_rate_limit_dep("cognition.quota")),
    _m=Depends(make_metrics_dep("cognition.quota")),
):
    """Report each configured provider's plan, auth mode and rate-limit windows."""
    try:
        adapters = _collect()
    except Exception as exc:
        logger.warning("quota collection failed: %s", exc)
        adapters = []
    # `tightest` is what an operator scans for: the single window closest to
    # cutting them off, across providers. Computing it here keeps every consumer
    # from re-deriving it and disagreeing about what "closest" means.
    live = [
        (window, entry)
        for entry in adapters
        if entry.get("status") == "ok"
        for window in entry.get("windows") or []
    ]
    tightest = max(live, key=lambda pair: pair[0].get("percent") or 0, default=None)
    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "adapters": adapters,
                    "tightest": (
                        {**tightest[0], "adapter": tightest[1]["adapter"]} if tightest else None
                    ),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                },
                "meta": {"layer": "routing"},
            }
        )
    )
