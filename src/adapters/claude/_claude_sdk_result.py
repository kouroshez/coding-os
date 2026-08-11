"""Claude adapter — failure classification for a dispatch outcome.

Maps a raw SDK/CLI error string onto the taxonomy the kernel's capacity breaker
and retry policy read (`error_category`, `retryable`, `outcome`). Adapter-local
by design: only the adapter knows which provider strings mean "your quota" as
opposed to "the provider is overloaded", and the two route differently.
"""

from __future__ import annotations

import re
from typing import Any


def _failure_fields(status: str, error: str | None) -> dict[str, Any]:
    if status == "ok":
        return {}
    message = (error or "").lower()
    if status == "timeout":
        return {"error_category": "timeout", "retryable": True, "outcome": "unknown"}
    retry_after: int | None = None
    match = re.search(r"(?:retry after|try again in)\s+(\d+)\s*(?:seconds?|s)?", message)
    if match:
        retry_after = int(match.group(1))
    if any(
        token in message
        for token in ("rate limit", "usage limit", "quota", "too many requests", "429", "capacity")
    ):
        return {
            "error_category": "capacity",
            "retryable": True,
            "retry_after_s": retry_after,
            "outcome": "known_failed",
        }
    if any(
        token in message
        for token in ("unauthorized", "authentication", "not logged in", "401", "403")
    ):
        return {"error_category": "auth", "outcome": "known_failed"}
    # Provider-side overload (529) and internal errors (5xx) are NOT your quota,
    # so they must not open the capacity breaker — but they are the most
    # retryable class there is, and reporting them non-retryable is wrong.
    if any(token in message for token in ("overloaded", "529", "api_error", "500", "502", "503")):
        return {"error_category": "provider", "retryable": True, "outcome": "unknown"}
    if any(token in message for token in ("not importable", "not found")):
        return {"error_category": "unavailable", "outcome": "known_failed"}
    if any(token in message for token in ("must be absolute", "max_budget_usd", "max_turns")):
        return {"error_category": "invalid", "outcome": "known_failed"}
    return {"error_category": "provider", "outcome": "unknown"}


def _finalize_dispatch_result(
    request: Any,
    *,
    dispatcher_name: str,
    result_subtype: str | None,
    result_meta: dict[str, Any],
    structured_output: Any,
    transcript: str,
    latency_ms: int,
) -> Any:
    from thinking_os.dispatcher import DispatchResult
    from thinking_os.dispatcher_helpers import extract_json_block

    # Map SDK error subtypes to dispatcher status. Budget exhaustion
    # and retry exhaustion are operationally distinct from a generic
    # "error_during_execution" — keep the original subtype in the
    # error string so callers can pattern-match.
    if result_subtype == "error_max_budget_usd":
        return DispatchResult(
            formula_id=request.formula_id,
            status="error",
            error=(
                f"max_budget_usd={request.max_budget_usd} exhausted; "
                f"actual_cost_usd={result_meta.get('total_cost_usd')!r}"
            ),
            output_json={"_meta": dict(result_meta)},
            latency_ms=latency_ms,
            dispatcher_name=dispatcher_name,
            raw_transcript=transcript or None,
            **_failure_fields("error", f"max_budget_usd={request.max_budget_usd} exhausted"),
        )
    if result_subtype == "error_max_turns":
        return DispatchResult(
            formula_id=request.formula_id,
            status="error",
            error="max_turns exhausted",
            output_json={"_meta": dict(result_meta)},
            latency_ms=latency_ms,
            dispatcher_name=dispatcher_name,
            raw_transcript=transcript or None,
            **_failure_fields("error", "max_turns exhausted"),
        )
    if result_subtype == "error_max_structured_output_retries":
        # Schema enforcement gave up; fall through to regex extraction
        # so the dispatcher still surfaces partial work instead of an
        # opaque error. Caller sees the subtype via raw_transcript +
        # output_json._meta.subtype.
        result_meta["structured_output_retry_exhausted"] = True

    # Prefer SDK-enforced structured output. extract_json_block is the
    # 0.1.x fallback for roles that don't opt into structured output
    # AND for retry-exhausted runs (logged above).
    output_json: dict[str, Any]
    if isinstance(structured_output, dict):
        output_json = dict(structured_output)
    else:
        output_json = extract_json_block(transcript)

    if result_meta:
        output_json.setdefault("_meta", {}).update(result_meta)
    if result_subtype:
        output_json.setdefault("_meta", {})["subtype"] = result_subtype

    ok = bool(output_json) and any(k != "_meta" for k in output_json)
    # T1.5: surface the retry-exhausted subtype in the error field so callers
    # can route to a retry-with-relaxed-prompt path. Status stays "ok" when
    # regex fallback recovered usable JSON — the output bundle is still
    # populated. Callers that need strict schema compliance should check error.
    if not ok:
        error_str = "no usable JSON in dispatch output"
    elif result_subtype == "error_max_structured_output_retries":
        error_str = (
            "error_max_structured_output_retries: schema enforcement exhausted, "
            "fell back to regex extraction"
        )
    else:
        error_str = None
    return DispatchResult(
        formula_id=request.formula_id,
        status="ok" if ok else "error",
        output_json=output_json,
        latency_ms=latency_ms,
        dispatcher_name=dispatcher_name,
        error=error_str,
        raw_transcript=transcript,
        **_failure_fields("ok" if ok else "error", error_str),
    )
