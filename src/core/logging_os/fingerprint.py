from __future__ import annotations

import hashlib
import re

# Order matters: collapse paths first (before hex/digit rules mangle their
# segments), then hex/uuid runs, then bare digits. Keeps identical errors that
# differ only in ids/paths/counts on a single stable fingerprint.
_PATHS = re.compile(r"(?:/[^\s:/]+){2,}")
_HEX = re.compile(r"\b[0-9a-f]{8,}\b")
_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")


def normalize_msg(msg: str) -> str:
    text = msg.lower()
    text = _PATHS.sub("<path>", text)
    text = _HEX.sub("<id>", text)
    text = _DIGITS.sub("#", text)
    return _WS.sub(" ", text).strip()


def fingerprint(scope: str, exc_type: str | None, msg: str) -> str:
    basis = f"{scope}|{exc_type or ''}|{normalize_msg(msg)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
