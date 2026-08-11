"""Header-only doc reads — the lazy-load half of the docs layer.

Pattern mirrors how Anthropic skills surface (frontmatter loads, body lazy):
the agent reads ONLY a doc's frontmatter + opening block (Purpose / Read
when / Skip when / Read next) before deciding whether the body is worth
spending tokens on. Saves ~70-90% on doc-decision loops where the agent is
routing between candidate docs.

Two surface tools (registered in server.py):
  cos_doc_header(path)            — single doc header
  cos_doc_headers_by(domain, …)   — bulk filter by frontmatter fields

Both bypass the embeddings store entirely. Filesystem reads are bounded to
the first ~3 KB of each candidate file — enough to cover the largest
observed opening blocks with margin.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("coding_os.tools.docs")


# Frontmatter HTML comment shape:
#   <!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-28 \
#        | tokens:1800 | reads:[a,b,c] -->
_FRONTMATTER_RE = re.compile(r"^\s*<!--\s*(.+?)\s*-->", re.DOTALL)

# Long-form opening block lines.
_LONG_OPENING_RE = {
    "purpose": re.compile(r"^Purpose:\s*(.+?)\s*$", re.M),
    "read_when": re.compile(r"^Read when:\s*(.+?)\s*$", re.M),
    "skip_when": re.compile(r"^Skip when:\s*(.+?)\s*$", re.M),
    "read_next": re.compile(r"^Read next:\s*(.+?)\s*$", re.M),
}

# Short-form — accept either form. Short form lives inside a
# blockquote: `> P: …` / `> R: …` / `> S: …` / `> N: …`.
_SHORT_OPENING_RE = {
    "purpose": re.compile(r"^>\s*P:\s*(.+?)\s*$", re.M),
    "read_when": re.compile(r"^>\s*R:\s*(.+?)\s*$", re.M),
    "skip_when": re.compile(r"^>\s*S:\s*(.+?)\s*$", re.M),
    "read_next": re.compile(r"^>\s*N:\s*(.+?)\s*$", re.M),
}

# H1 detection — first level-1 heading wins.
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)

# Header read budget — first 8 KB covers all canonical openings observed in
# the scaffold + meta-repo, including docs with sizable `reads:[…]` lists or
# multi-line short-form opening blocks. Cheap to read; never touches the body.
_HEADER_READ_BYTES = 8192

# Bulk scan budget — defensive cap to keep cos_doc_headers_by snappy.
_BULK_MAX_RESULTS = 50


def _parse_frontmatter_block(text: str) -> dict[str, Any]:
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    body = match.group(1)
    out: dict[str, Any] = {}
    for fragment in body.split("|"):
        if ":" not in fragment:
            continue
        key, _, value = fragment.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if key == "reads":
            # `reads:[a, b, c]` or `reads:a,b,c`.
            stripped = value.strip("[]")
            items = [s.strip() for s in stripped.split(",") if s.strip()]
            out[key] = items
            continue
        if key == "tokens":
            try:
                out[key] = int(value)
            except ValueError:
                out[key] = value
            continue
        out[key] = value
    return out


def _parse_opening_block(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, regex in _SHORT_OPENING_RE.items():
        match = regex.search(text)
        if match:
            out[key] = match.group(1).strip()
    for key, regex in _LONG_OPENING_RE.items():
        match = regex.search(text)
        if match:
            out[key] = match.group(1).strip()
    return out


def parse_doc_header(path: Path) -> dict[str, Any] | None:
    """Read a doc's first 3 KB and extract header."""
    p = Path(path)
    try:
        if not p.is_file():
            return None
        with p.open("rb") as fp:
            chunk = fp.read(_HEADER_READ_BYTES)
        try:
            text = chunk.decode("utf-8", errors="replace")
        except (UnicodeDecodeError, AttributeError):
            return None
        stat = p.stat()
    except OSError as exc:
        logger.debug("parse_doc_header: cannot read %s: %s", p, exc)
        return None

    frontmatter = _parse_frontmatter_block(text)
    opening_block = _parse_opening_block(text)
    title_match = _H1_RE.search(text)
    title = title_match.group(1).strip() if title_match else ""

    # Cheap token estimate so the agent can budget multi-doc fan-out.
    header_text_len = (
        len(json.dumps(frontmatter, ensure_ascii=False))
        + len(json.dumps(opening_block, ensure_ascii=False))
        + len(title)
    )
    return {
        "path": str(p),
        "title": title,
        "frontmatter": frontmatter,
        "opening_block": opening_block,
        "mtime": int(stat.st_mtime),
        "size_bytes": stat.st_size,
        "header_token_estimate": max(1, header_text_len // 4),
    }


def list_doc_headers(
    root: Path,
    *,
    domain: str | None = None,
    layer: str | None = None,
    ssot: str | None = None,
    since_iso: str | None = None,
    limit: int = _BULK_MAX_RESULTS,
) -> list[dict[str, Any]]:
    """Walk a docs root and return matching headers."""
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in root_path.rglob("*.md"):
        # Resolve symlinks safely (Rule 5) before relative_to checks elsewhere.
        try:
            path = path.resolve()
        except OSError:
            continue
        header = parse_doc_header(path)
        if not header:
            continue
        fm = header["frontmatter"]
        if not fm:
            continue
        if domain and fm.get("domain") != domain:
            continue
        if layer and fm.get("layer") != layer:
            continue
        if ssot and fm.get("ssot") != ssot:
            continue
        if since_iso and (fm.get("updated") or "") < since_iso:
            continue
        rows.append(header)

    def _sort_key(h: dict[str, Any]) -> tuple[float, str]:
        fm = h.get("frontmatter") or {}
        priority = fm.get("priority")
        try:
            priority_num = float(priority) if priority is not None else 0.5
        except (TypeError, ValueError):
            priority_num = 0.5
        updated = str(fm.get("updated") or "")
        return (-priority_num, updated)

    # Sort the FULL match set before truncating — otherwise top-N is rglob
    # (filesystem) order, not priority/recency order.
    rows.sort(key=_sort_key)
    return rows[:limit]
