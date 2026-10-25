"""
Coding OS — secret and username scrubbing for text that is stored durably.

`redact_secrets` replaces token, key and password shapes with a labelled
placeholder; `scrub_username` replaces the operator's home directory and login
name. Both are pure stdlib regex, deterministic, and never reject the text.
Callers: the tool-failure capture hook, supervision dispatch records, and the
v36/v37 migrations.
"""

from __future__ import annotations

import os
import re

# Secret / PII redaction — high-precision patterns so legitimate narrative text
# is never mangled. Redaction REPLACES the match (it does NOT reject the write).
# Order matters: multi-line private keys first, then specific token shapes, then
# a conservative key=value form gated on a digit (entropy) to avoid false hits.
_SECRET_SPECS: list[tuple[str, str, str]] = [
    (
        r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----",
        "<redacted-private-key>",
        "private_key",
    ),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<redacted-email>", "email"),
    (r"\bBearer\s+[A-Za-z0-9._\-]{8,}", "Bearer <redacted-token>", "bearer_token"),
    (r"\bAKIA[0-9A-Z]{16}\b", "<redacted-aws-key>", "aws_key"),
    (r"\bgh[pousr]_[A-Za-z0-9]{20,}\b", "<redacted-token>", "github_token"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "<redacted-token>", "slack_token"),
    (r"\b(?:sk|pk|rk)_(?:live|test|prod)_[A-Za-z0-9]{12,}\b", "<redacted-key>", "stripe_key"),
    (r"\bsk-[A-Za-z0-9]{20,}\b", "<redacted-key>", "sk_key"),
    (
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|access[_-]?key)\b(\s*[=:]\s*)(?=\S*\d)\S{8,}",
        r"\1\2<redacted-secret>",
        "secret_assignment",
    ),
]
_SECRET_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(pattern), repl, label) for pattern, repl, label in _SECRET_SPECS
]


def redact_secrets(text: str) -> tuple[str, list[str]]:
    """Replace emails/API-keys/tokens/private-keys in `text`.

    Returns (redacted_text, labels_of_what_was_redacted). Never raises; never
    rejects — memory must not silently lose a write because it had a secret,
    but it MUST NOT persist the secret. The labels feed the audit log (NOT the
    secret value itself).
    """
    if not text:
        return text, []
    labels: list[str] = []
    for compiled, repl, label in _SECRET_PATTERNS:
        new_text, count = compiled.subn(repl, text)
        if count:
            labels.append(label)
            text = new_text
    return text, labels


def scrub_username(text: str, home: str | None = None) -> str:
    """Strip the local OS username from `text` — the $HOME prefix (→ `~/`) and
    the dash-encoded $HOME used in agent project-dir slugs
    (`~/.claude/projects/-Users-<name>-…` → `~/.claude/projects/-~-…`). The OS
    username is a customer-identifying string, so every durable write runs this."""
    if not text:
        return text
    h = home if home is not None else os.path.expanduser("~")
    if h and h != "~":
        text = text.replace(h + "/", "~/")
        # Bare home with no trailing slash (path ends at $HOME, or is followed by
        # a non-path char). The negative lookahead `(?![\w/])` avoids mangling a
        # different user whose name extends this one (/Users/alice vs /Users/alice2).
        text = re.sub(re.escape(h) + r"(?![\w/])", "~", text)
        dash = h.replace("/", "-")
        if dash and dash != "-":
            text = text.replace(dash, "-~")
    return text


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------
