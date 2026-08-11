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
