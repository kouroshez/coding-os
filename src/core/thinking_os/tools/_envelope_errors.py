"""MCP envelope — the failure side: `fail()` and the standard rejections.

`fail()` builds the one error shape every `cos_*` tool returns, and the
`validate_*` helpers are its standard producers: each answers "is this
argument acceptable?" with either `None` or a ready-made validation envelope,
so the caller pattern stays `err = validate_x(...); if err: return err`
instead of a hand-built dict per tool (Critical Rule 13).

They live beside `fail` rather than in the facade because they *are* callers
of it — keeping them here is what lets `_shared` import this leaf without a
cycle. Contract SSOT: docs/engineering/mcp-error-envelope.md.
"""

from __future__ import annotations

import json
from typing import Any, Literal

ErrorCategory = Literal[
    "transient",
    "validation",
    "permission",
    "not_found",
    "unavailable",
    "internal",
    "module_disabled",
]

_RETRYABLE_BY_DEFAULT: frozenset[str] = frozenset({"transient", "unavailable"})


def fail(
    category: ErrorCategory,
    message: str,
    *,
    retryable: bool | None = None,
) -> str:
    """Wrap an error in the canonical envelope.

    If `retryable` is not given it is inferred from the category:
    `transient` and `unavailable` default to True; everything else to False.
    Override when a specific call has better information.
    """
    if retryable is None:
        retryable = category in _RETRYABLE_BY_DEFAULT
    return json.dumps(
        {
            "ok": False,
            "error": {
                "category": category,
                "retryable": retryable,
                "message": message,
            },
        },
        indent=2,
        default=str,
    )


# ---------------------------------------------------------------------------
# G36: SSOT validation helpers — uniform shape across all cos_* tools.
# Return None when valid, a fail-envelope string when invalid. Caller
# pattern is `err = validate_X(...); if err: return err`.
# ---------------------------------------------------------------------------


def validate_enum(value: Any, allowed: tuple[str, ...], field: str) -> str | None:
    # None when valid; fail envelope when value not in allowed.
    if value not in allowed:
        return fail(
            "validation",
            f"{field} must be one of {allowed} (got {value!r})",
        )
    return None


def validate_positive_int(value: Any, field: str) -> str | None:
    # Reject non-int / <=0; otherwise None.
    if not isinstance(value, int) or value <= 0:
        return fail("validation", f"{field} must be a positive int (got {value!r})")
    return None


def validate_non_empty_str(value: Any, field: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return fail("validation", f"{field} must be a non-empty string")
    return None


def validate_min_chars(value: Any, field: str, *, min_chars: int = 2) -> str | None:
    # W7.1 / R4-09: parity between cos_graph_query (already enforces 2)
    # and cos_graph_resolve (silently accepted single-char fuzzy).
    if not isinstance(value, str):
        return fail("validation", f"{field} must be a string (got {type(value).__name__})")
    if len(value.strip()) < min_chars:
        return fail("validation", f"{field} must be at least {min_chars} chars (got {value!r})")
    return None


def validate_confidence(value: Any, field: str) -> str | None:
    # W7.1 / R4-19/R4-26: confidence scores live in [0.0, 1.0]; the
    # cos_graph_impact / cos_graph_query tools silently accepted 999
    # and filtered everything.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return fail("validation", f"{field} must be a number (got {type(value).__name__})")
    if value < 0.0 or value > 1.0:
        return fail("validation", f"{field} must be in [0.0, 1.0] (got {value})")
    return None


def clamp_int(value: int, *, min_v: int, max_v: int) -> tuple[int, bool]:
    # Return (clamped, was_clamped). Caller surfaces was_clamped in meta.
    clamped = max(min_v, min(value, max_v))
    return clamped, clamped != value
