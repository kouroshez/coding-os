from __future__ import annotations

import re
from typing import Any

# High-precision secret shapes. Conservative by design — better to miss an
# exotic secret than to mangle ordinary error text. Runs before EVERY sink so
# nothing secret reaches the durable store (a secret there is permanent).
_PATTERNS = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{12,}"),  # Bearer tokens
    re.compile(r"\beyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}"),  # JWT
    re.compile(r"\b(?:sk|pk|rk|ghp|gho|ghs|xox[baprs])[-_][A-Za-z0-9]{16,}"),  # API key prefixes
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(
        r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|authorization)\s*[=:]\s*\S+"
    ),  # k=v secrets
]
_REDACTED = "<redacted>"

_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "key",
    "access_token",
    "refresh_token",
}


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _PATTERNS:
        out = pat.sub(_REDACTED, out)
    return out


def redact_kv(kv: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in kv.items():
        if key.lower() in _SENSITIVE_KEYS:
            out[key] = _REDACTED
        elif isinstance(value, str):
            out[key] = redact_text(value)
        else:
            out[key] = value
    return out
