"""Language-table + regex symbol extraction for the doc-sync staleness scanner.

Pure text in, `{name: (param_count, param_shape)}` out — no filesystem, no DB.
Kept apart from doc_sync_check.py so adding a language is a one-file change
that cannot touch the candidate-discovery or reporting paths.
"""

from __future__ import annotations

import re

CODE_EXT_TO_LANG = {
    ".py": "python",
    ".ts": "ts",
    ".tsx": "ts",
    ".js": "ts",
    ".jsx": "ts",
    ".go": "go",
    ".rs": "rust",
}

DOC_EXTENSIONS = {".md", ".mdx"}

# ── Symbol extraction ────────────────────────────────────────────────────
# We capture the name AND a representation of the parameter list so a
# pure-rename, a pure-signature-change, and a deletion all surface
# distinct signals.

_PY_FN_RX = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)")
_PY_CLASS_RX = re.compile(r"^\s*class\s+([A-Z][A-Za-z0-9_]*)\b")
_TS_FN_RX = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)"
)
_TS_CLASS_RX = re.compile(r"^\s*(?:export\s+)?class\s+([A-Z][A-Za-z0-9_]*)\b")
_TS_CONST_FN_RX = re.compile(
    r"^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*"
    r"(?:async\s+)?\(([^)]*)\)\s*(?::[^=]+)?=>"
)


def _is_public(name: str) -> bool:
    """Skip dunders, private (underscore-prefix), CamelCase one-shots that
    look like type aliases. We only care about names a doc would mention."""
    if not name:
        return False
    if name.startswith("__") and name.endswith("__"):
        return False
    return not (name.startswith("_") and not name.startswith("__"))


def _normalise_params(params: str) -> tuple[int, str]:
    """Return (param_count, normalised_signature_string).

    Crude — strips type annotations and defaults, splits on top-level
    commas. Fine for the drift signal we want; not a full parser."""
    if not params or not params.strip():
        return 0, ""
    # Strip annotations / defaults to get bare param names.
    raw_parts: list[str] = []
    depth = 0
    cur = []
    for ch in params:
        if ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            raw_parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    raw_parts.append("".join(cur).strip())

    names: list[str] = []
    for p in raw_parts:
        if not p:
            continue
        # Drop default value ("x: int = 0" → "x: int")
        p = p.split("=", 1)[0]
        # Drop annotation ("x: int" → "x")
        name = p.split(":", 1)[0].strip()
        # Drop *, **, ... markers ("**kwargs" → "kwargs")
        name = name.lstrip("*")
        if name and name not in ("self", "cls", "/", "*"):
            names.append(name)
    return len(names), ",".join(names)


def _extract_symbols(text: str, lang: str) -> dict[str, tuple[int, str]]:
    """name → (param_count, normalised_signature). Class names get
    placeholder (-1, "") since we don't extract class signatures.
    Public names only."""
    out: dict[str, tuple[int, str]] = {}
    if lang == "python":
        fn_rxs, class_rx = [_PY_FN_RX], _PY_CLASS_RX
    elif lang == "ts":
        fn_rxs, class_rx = [_TS_FN_RX, _TS_CONST_FN_RX], _TS_CLASS_RX
    else:
        return out

    for line in text.splitlines():
        for rx in fn_rxs:
            m = rx.match(line)
            if m:
                name = m.group(1)
                if _is_public(name):
                    out[name] = _normalise_params(m.group(2))
                break
        else:
            m = class_rx.match(line)
            if m and _is_public(m.group(1)):
                out.setdefault(m.group(1), (-1, ""))
    return out


# ── Doc candidate enumeration ────────────────────────────────────────────
