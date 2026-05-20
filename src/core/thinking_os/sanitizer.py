"""
Coding OS — Memory write sanitizer (Phase G.2 brain hardening).

Guards every user/agent-originated text before it reaches learned_patterns,
observations, or outcome_history. Two defenses:

  1. Injection-pattern rejection — regex list of known prompt-injection
     phrasings ("ignore previous instructions", "from now on you are ...").
     Match => reject with a structured reason, log to memory_audit.
  2. Length capping — each field has a hard cap. Over-cap text is truncated
     with a visible marker, and the truncation is logged to memory_audit.

Design notes:
  - SINGLE chokepoint: callers invoke `sanitize_write()` once per write
    and receive a `SanitizeResult` with either cleaned text or a reject.
  - FAIL-CLOSED: when a reject fires, the caller MUST NOT insert the row.
    The MCP layer turns this into `fail("validation", ...)`.
  - FIRE-AND-FORGET AUDIT: audit logging never raises — if the DB is
    pre-v7, the helper silently no-ops. Sanitization itself still runs.
  - NO TRAINING DATA LEAK: sanitizer does not call embeddings or any
    external model. Pure stdlib regex — deterministic, fast (~200µs per
    field on typical text).

Public API:
    sanitize_write(field, text, *, actor, source_table, conn=None) -> SanitizeResult
    FIELD_CAPS                — dict of per-field char limits
    INJECTION_PATTERNS        — list of compiled regex patterns (read-only)
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from database import record_audit

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Per-field character caps. Chosen to fit comfortably within one embedding
# chunk (all-MiniLM-L6-v2 ~512 token limit) while still preserving meaning.
FIELD_CAPS: dict[str, int] = {
    "title": 200,
    "narrative": 4000,
    "pattern": 500,
    "key_insight": 500,
    "what_failed": 2000,
    "what_worked": 2000,
    "concepts": 800,
}

# Prompt-injection phrasings — compiled once at module load.
# Each entry is (compiled_regex, short_label).
# Labels are stable so audit log reasons survive pattern reordering.
_INJECTION_SPECS: list[tuple[str, str]] = [
    # "ignore (all) previous/above/prior instructions/directives/prompts"
    (
        r"\bignore\s+(?:all\s+)?(?:previous|above|prior)\s+(?:instructions?|directives?|prompts?|rules?|guidelines?)\b",
        "ignore_previous_instructions",
    ),
    # "disregard the above/prior/previous/system ..."
    (
        r"\bdisregard\s+(?:the\s+)?(?:above|prior|previous|system|all)\b",
        "disregard_directive",
    ),
    # "from now on you/i/we (will|must|are|shall) ..."
    (
        r"\bfrom\s+now\s+on\s+(?:you|i|we)\s+(?:will|must|are|shall|should)\b",
        "from_now_on_directive",
    ),
    # "you are (now) (a) different/new/unrestricted/DAN/jailbroken/etc."
    (
        r"\byou\s+are\s+(?:now\s+)?(?:a\s+)?(?:different|new|unrestricted|uncensored|jailbroken|DAN|developer\s+mode)\b",
        "role_hijack",
    ),
    # "system prompt" as a phrase
    (
        r"\bsystem\s+prompt\b",
        "system_prompt_reference",
    ),
    # "override the (default|system|safety|previous) ..."
    (
        r"\boverride\s+(?:the\s+)?(?:default|system|safety|previous|above)\b",
        "override_directive",
    ),
    # "pretend (you are|to be)" coercive framing
    (
        r"\bpretend\s+(?:you\s+are|to\s+be)\b",
        "pretend_directive",
    ),
    # "new instructions:" style handoffs
    (
        r"\bnew\s+instructions\s*:\s*",
        "new_instructions_handoff",
    ),
]

INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), label) for pattern, label in _INJECTION_SPECS
]

_TRUNCATION_MARKER = "\n\n…[truncated]"


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SanitizeResult:
    """Outcome of a sanitize_write call.

    Attributes:
        ok:          True when write should proceed; False when rejected.
        cleaned:     The text to persist (possibly truncated). None on reject.
        reason:      Stable short code for audit/response ('injection:<label>',
                     'truncated:<field>', 'ok').
        original_len: len(text) before sanitization — for audit/metrics.
        cleaned_len: len(cleaned) after sanitization, or 0 on reject.
    """

    ok: bool
    cleaned: str | None
    reason: str
    original_len: int
    cleaned_len: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_injection(text: str) -> str | None:
    """Return the label of the first injection pattern matched, or None."""
    if not text:
        return None
    for compiled, label in INJECTION_PATTERNS:
        if compiled.search(text):
            return label
    return None


def _truncate(text: str, cap: int) -> str:
    """Return text truncated to `cap` chars with a visible marker appended.

    Cap is applied to the ORIGINAL text length; the marker is added on top,
    so the return value is slightly longer than `cap` by the marker length.
    This keeps the "cap" semantic tied to the user-visible content, not the
    storage byte count.
    """
    if len(text) <= cap:
        return text
    return text[:cap].rstrip() + _TRUNCATION_MARKER


def sanitize_write(
    field: str,
    text: str | None,
    *,
    actor: str,
    source_table: str,
    source_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> SanitizeResult:
    """Validate and clean text before it is written into memory storage."""
    if text is None:
        return SanitizeResult(ok=True, cleaned="", reason="ok", original_len=0, cleaned_len=0)

    original = text
    original_len = len(original)

    injection_label = detect_injection(original)
    if injection_label is not None:
        reason = f"injection:{injection_label}"
        if conn is not None:
            record_audit(
                conn,
                actor=actor,
                action="reject",
                source_table=source_table,
                source_id=source_id,
                new_value=_preview(original),
                reason=reason,
            )
        return SanitizeResult(
            ok=False,
            cleaned=None,
            reason=reason,
            original_len=original_len,
            cleaned_len=0,
        )

    cap = FIELD_CAPS.get(field)
    cleaned = original if cap is None else _truncate(original, cap)
    was_truncated = cleaned is not original

    if was_truncated and conn is not None:
        record_audit(
            conn,
            actor=actor,
            action="truncate",
            source_table=source_table,
            source_id=source_id,
            old_value=str(original_len),
            new_value=str(len(cleaned)),
            reason=f"truncated:{field}:cap={cap}",
        )

    return SanitizeResult(
        ok=True,
        cleaned=cleaned,
        reason="truncated" if was_truncated else "ok",
        original_len=original_len,
        cleaned_len=len(cleaned),
    )


def _preview(text: str, max_len: int = 200) -> str:
    """Return a short excerpt of `text` for storage in an audit row."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
