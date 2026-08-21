"""Turn a Codex usage report into US dollars.

Separate from the dispatcher because it answers a different question — what the
tokens cost, not how the turn ran — and because the mapping below is the one
place that has to know both this runtime's field names and the rate-bucket names
core prices against.

The Codex CLI reports tokens and no cost, so without this every codex dispatch
lands as a priceless row and the per-adapter rollup reads as if codex were free.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from thinking_os.dispatcher_helpers import price_tokens

logger = logging.getLogger("coding_os.dispatcher.codex_pricing")

_DESCRIPTOR = Path(__file__).resolve().parent / "adapter.yaml"


def _models() -> list[dict[str, Any]]:
    try:
        manifest = yaml.safe_load(_DESCRIPTOR.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.debug("codex descriptor unreadable: %s", exc)
        return []
    models = manifest.get("models")
    return (
        [entry for entry in models if isinstance(entry, dict)] if isinstance(models, list) else []
    )


def pricing_for(model: str | None) -> dict[str, Any] | None:
    models = _models()
    wanted = str(model or "").strip()
    # No model named means the runtime picks its default, so the default's table
    # is the right one. A model named but absent from the catalog gets nothing:
    # pricing it off a neighbour's table would report a confident wrong number,
    # which is worse than the empty cell an unpriced row leaves.
    if wanted:
        match = next((entry for entry in models if str(entry.get("id")) == wanted), None)
    else:
        match = next((entry for entry in models if entry.get("default")), None)
    pricing = (match or {}).get("pricing")
    return pricing if isinstance(pricing, dict) else None


def _count(usage: dict[str, Any], *names: str) -> float:
    for name in names:
        value = usage.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return 0.0


def cost_usd(usage: dict[str, Any] | None, model: str | None) -> float | None:
    """Price one turn's usage, or None when the token counts or the table are missing."""
    if not isinstance(usage, dict):
        return None
    cached = _count(usage, "cached_input_tokens", "cached_tokens")
    written = _count(usage, "cache_write_input_tokens", "cache_write_tokens")
    # `input_tokens` is the whole prompt, with the cached and written parts
    # counted inside it, so they are subtracted out to leave what is billed at
    # the full rate. Floored at zero: if a future field ever stops being a
    # subset, the result understates rather than double-charging the same token.
    billed_input = max(0.0, _count(usage, "input_tokens", "prompt_tokens") - cached - written)
    buckets = {
        "input": billed_input,
        "cached_input": cached,
        "cache_write": written,
        # Reasoning tokens are already inside output_tokens and bill at the
        # output rate, so adding them separately would charge them twice.
        "output": _count(usage, "output_tokens", "completion_tokens"),
    }
    return price_tokens(buckets, pricing_for(model))
