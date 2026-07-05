"""Friction-cluster distillation via the adapter dispatcher (P8-safe)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from cognition_schemas import DistilledLesson, SessionEnrichment
from dispatcher import DispatchRequest, get_dispatcher
from sanitizer import redact_secrets, scrub_username

logger = logging.getLogger("coding_os.distill")

_AGENT_FILE = Path(__file__).resolve().parent / "agents" / "distiller.md"
# Under agents/internal/ so the non-recursive agents/*.md globs (formula
# registry, /role-* command generation, composer) never pick it up — this card
# is dispatched only by explicit path from observe_session, never composed.
_OBSERVER_FILE = Path(__file__).resolve().parent / "agents" / "internal" / "session_observer.md"
_MAX_SAMPLE_CHARS = 300
_MAX_SAMPLES = 3
_CALL_TIMEOUT_S = 60.0


def _call_budget_usd() -> float:
    # A dispatched sub-session pays a base system-prompt cost, so the floor is
    # higher than a raw completion; still cents per cluster, capped per run.
    try:
        return float(os.environ.get("COS_DISTILL_BUDGET_USD", "0.25"))
    except ValueError:
        return 0.25


def cluster_fingerprint(kind: str, signature: str) -> str:
    return hashlib.sha256(f"{kind}:{signature}".encode()).hexdigest()[:16]


def enabled() -> bool:
    return os.environ.get("COS_DISTILL_LLM", "1") != "0"


def enrich_enabled() -> bool:
    # Default OFF — per-session semantic enrichment costs a dispatch per session,
    # so the owner opts in with a token budget (unlike friction distillation,
    # which is on by default because it fires only on recurring friction).
    return os.environ.get("COS_ENRICH_LLM", "0") == "1"


def sanitize_samples(samples: list[str]) -> list[str]:
    clean: list[str] = []
    for sample in samples[:_MAX_SAMPLES]:
        text, _ = redact_secrets(str(sample))
        text = scrub_username(text)
        clean.append(text[:_MAX_SAMPLE_CHARS])
    return clean


def _adapter_scan() -> Any:
    # Headless runs (nightly launchd) detect no session agent, so the factory
    # returns the LLM-less default dispatcher. Probe installed adapters instead
    # of giving up — sleep-time distillation is this module's primary caller.
    try:
        from dispatcher import _known_agents, _try_load_adapter_dispatcher

        for agent in sorted(_known_agents()):
            candidate = _try_load_adapter_dispatcher(agent)
            if candidate is not None and candidate.available():
                return candidate
    except Exception as exc:
        logger.debug("adapter scan failed: %s", exc)
    return None


def _resolve_dispatcher() -> Any:
    dispatcher = get_dispatcher()
    if getattr(dispatcher, "name", "") != "default" and dispatcher.available():
        return dispatcher
    return _adapter_scan()


def _run_dispatch(request: DispatchRequest) -> Any:
    dispatcher = _resolve_dispatcher()
    if dispatcher is None:
        return None

    async def _go() -> Any:
        return await dispatcher.dispatch(request)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_go())

    result: list[Any] = [None]

    def _in_thread() -> None:
        result[0] = asyncio.run(_go())

    thread = threading.Thread(target=_in_thread, daemon=True)
    thread.start()
    thread.join(timeout=_CALL_TIMEOUT_S + 10)
    return result[0]


def distill_cluster(
    *,
    kind: str,
    signature: str,
    count: int,
    hook: str = "",
    rule: str = "",
    samples: list[str] | None = None,
) -> dict[str, str] | None:
    """Return {situation, action, why} for one friction cluster, or None."""
    if not enabled():
        return None

    evidence = {
        "friction_kind": kind,
        "recurrences": count,
        "enforcing_hook": hook,
        "blocked_rule": rule,
        "signature": signature[:200],
        "sample_messages": sanitize_samples(samples or []),
    }
    request = DispatchRequest(
        formula_id="distiller",
        agent_file=str(_AGENT_FILE),
        prompt=json.dumps(evidence, ensure_ascii=False),
        timeout_s=_CALL_TIMEOUT_S,
        max_budget_usd=_call_budget_usd(),
        # max_turns stays unset: the adapter default (3 with an output schema)
        # covers the structured-output retry loop; 1 kills the first retry.
        model=os.environ.get("COS_DISTILL_MODEL") or None,
    )

    try:
        result = _run_dispatch(request)
    except Exception as exc:
        logger.debug("distill dispatch failed: %s", exc)
        return None
    if result is None or result.status != "ok" or not result.output_json:
        return None

    try:
        lesson = DistilledLesson.model_validate(result.output_json)
    except Exception as exc:
        logger.debug("distill output rejected by schema: %s", exc)
        return None

    situation, _ = redact_secrets(lesson.situation.strip())
    action, _ = redact_secrets(lesson.action.strip())
    why, _ = redact_secrets(lesson.why.strip())
    return {"situation": situation, "action": action, "why": why}


def lesson_text(distilled: dict[str, str]) -> str:
    return f"{distilled['situation']} → {distilled['action']} — {distilled['why']}"


def observe_session(evidence: dict[str, Any]) -> SessionEnrichment | None:
    """Distill one session's mechanical changelog rows into a SessionEnrichment, or None."""
    if not enrich_enabled():
        return None

    request = DispatchRequest(
        formula_id="session_observer",
        agent_file=str(_OBSERVER_FILE),
        prompt=json.dumps(evidence, ensure_ascii=False),
        timeout_s=_CALL_TIMEOUT_S,
        max_budget_usd=_call_budget_usd(),
        model=os.environ.get("COS_ENRICH_MODEL") or os.environ.get("COS_DISTILL_MODEL") or None,
    )

    try:
        result = _run_dispatch(request)
    except Exception as exc:
        logger.debug("observe_session dispatch failed: %s", exc)
        return None
    if result is None or result.status != "ok" or not result.output_json:
        return None

    try:
        return SessionEnrichment.model_validate(result.output_json)
    except Exception as exc:
        logger.debug("session enrichment rejected by schema: %s", exc)
        return None
