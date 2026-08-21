"""Coding OS — Dispatcher shared helpers."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("coding_os.dispatcher.helpers")

_CORE_TOS = Path(__file__).resolve().parent

_FENCED_JSON = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})", re.DOTALL)


def load_agent_prompt(agent_file: str) -> tuple[str, dict[str, Any]]:
    path = Path(agent_file)
    if not path.is_absolute():
        path = _CORE_TOS / agent_file.lstrip("/")
    if not path.exists():
        raise FileNotFoundError(f"agent file not found: {agent_file}")

    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                import yaml  # local import — pyaml is a soft dep here

                meta = yaml.safe_load(parts[1]) or {}
            except ImportError:
                meta = {}
            return parts[2].strip(), meta
    return text.strip(), {}


def extract_json_block(transcript: str) -> dict[str, Any]:
    m = _FENCED_JSON.search(transcript) or _BARE_JSON.search(transcript)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logger.debug("dispatcher JSON parse failed: %s", exc)
        return {}


def render_shared_context(shared_context: dict[str, Any] | None) -> str:
    """Render DispatchRequest.shared_context as a prompt block, or '' when empty."""
    if not shared_context:
        return ""
    lines = [
        "## Work Context (the task this dispatch serves)",
        f"- Task: {shared_context.get('task_id') or 'none'}"
        f" — {shared_context.get('title') or 'untitled'}"
        f" [{shared_context.get('status') or 'unknown'}]",
    ]
    work_log = shared_context.get("recent_work_log") or []
    if isinstance(work_log, list) and work_log:
        lines.append("- Recent work log (newest first):")
        lines.extend(f"  - {entry}" for entry in work_log[:5])
    lines.append(
        "\nYou inherit no prior conversation. If this context does not cover what "
        "you need, say so in your output rather than assuming."
    )
    return "\n".join(lines)


def resolve_model_alias(
    model: str | None, model_ids: list[str], default_id: str | None
) -> str | None:
    """Resolve a tier alias ('sonnet') to a concrete model id declared by an adapter.

    The kernel router and role `model_pref` blocks speak in tiers while adapter
    descriptors declare concrete ids, so validating a routed tier against the id
    list rejects it as undeclared. Descriptor-driven, so core stays adapter-
    agnostic (P8): the caller supplies the ids it already holds.
    """
    if not model:
        return model
    alias = model.strip().lower()
    if not alias:
        return model
    if model in model_ids:
        return model
    match = next((mid for mid in model_ids if alias in mid.lower()), None)
    return match or default_id or model


_INPUT_BUCKETS = ("input", "cached_input", "cache_write")


def price_tokens(buckets: dict[str, Any], pricing: dict[str, Any] | None) -> float | None:
    """Convert token buckets to USD with an adapter's declared per-Mtok table.

    Buckets are keyed by rate name (`input` = uncached, `cached_input`,
    `cache_write`, `output`) so the arithmetic stays provider-neutral: mapping a
    runtime's own field names onto them is the adapter's job, and the tier is
    chosen from the input total because that is what the published tables meter.
    Returns None when no table is declared — a missing price is reported as
    unknown, never as zero, which would read as "this adapter is free".
    """
    if not isinstance(pricing, dict) or str(pricing.get("unit") or "") != "usd_per_mtok":
        return None
    rates = pricing.get("rates")
    if not isinstance(rates, dict):
        return None
    counts = {
        key: float(value)
        for key, value in buckets.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    }
    threshold = pricing.get("long_context_input_tokens")
    total_input = sum(counts.get(key, 0.0) for key in _INPUT_BUCKETS)
    tier = "short"
    if isinstance(threshold, (int, float)) and total_input > threshold and "long" in rates:
        tier = "long"
    table = rates.get(tier) or rates.get("short")
    if not isinstance(table, dict):
        return None
    total = sum(
        count * float(table[key])
        for key, count in counts.items()
        if isinstance(table.get(key), (int, float))
    )
    return round(total / 1_000_000, 6)
