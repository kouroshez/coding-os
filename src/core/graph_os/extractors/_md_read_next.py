"""Opening-block `Read next:` / `> N:` scanning → read_next edges.

The convention is a doc-authoring one, not a markdown one: a doc names what to
read after it, in the body opening block or in frontmatter `reads:[…]`. Both
forms funnel through the same emitter so the graph stays symmetric.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..types import GraphEdge
from ._extract_base import EXTRACTOR_ID, ExtractionResult, _normalize_path
from ._md_resolve import _resolve_link, _resolve_through_symlink
from ._md_uids import file_uid

# Opening-block "Read next:" lines. Long form lives plain in the
# body; short form lives inside a blockquote (`> N: …`). Both produce
# read_next edges to every comma-separated target.
_OPENING_READ_NEXT_RE = re.compile(
    r"^(?:Read next:|>\s*N:)\s*(?P<targets>.+?)\s*$",
    re.MULTILINE,
)

# Strip markdown link wrapper `[label](href)` to keep only the href.
_LINK_HREF_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

# W6.5 (X7): valid path target must match this — no spaces, must look like
# a path / URL / fragment. Rejects garbage prose fragments captured by
# the previous lenient `_split_read_targets` (Round 3 root cause of 386
# stale_paths + ranking pollution from doc:file:"…prose…" uids).
_PATH_LIKE_RE = re.compile(r"^[\w./\-:#?&=%~+]+$")


def _split_read_targets(raw: str) -> list[str]:
    """Split a comma-or-bracket list of read_next targets into clean paths."""
    text = raw.strip()
    # Only collapse the wrapping brackets when the whole value is `[…]` —
    # short-form `reads:[a, b]`. Markdown links like `[a](a.md), [b](b.md)`
    # must keep their `[`/`]` so the link regex can still match.
    if text.startswith("[") and text.endswith("]") and "](" not in text:
        text = text[1:-1]
    if not text:
        return []
    fragments = [frag.strip() for frag in text.split(",") if frag.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for frag in fragments:
        match = _LINK_HREF_RE.search(frag)
        href = (match.group(1) if match else frag).strip()
        href = href.strip("`").strip()
        if not href or href in seen:
            continue
        # W6.5 (X7): reject prose fragments — only accept path-like strings.
        # Prevents `Relevant ADR in ../architecture/adr/ or the domain doc.`
        # from becoming a doc:file: uid.
        if not _PATH_LIKE_RE.match(href):
            continue
        seen.add(href)
        out.append(href)
    return out


# Repo-root prefixes — a read_next target starting with one of these is
# already repo-rooted and used verbatim; anything else (bare filename or
# `./`/`../`) is resolved against the source doc's directory.
_REPO_ROOT_PREFIXES = ("docs/", "src/", "tests/", "infrastructure/", "scripts/")


def _resolve_read_target(path: str, target_path: str) -> str | None:
    """Resolve a read_next / opening-block target to a clean uid.

    Bare filenames + `./`/`../` paths anchor against the source doc dir
    (R4 follow-up: a bare `accessibility-checklist.md` used to mint a
    repo-root `doc:file:accessibility-checklist.md` stub that never
    existed). Repo-rooted `docs/...`/`src/...` targets pass through.
    """
    if target_path.startswith(("http://", "https://")):
        return f"doc:external:{target_path}"
    if target_path.startswith(("../", "./")):
        resolved = _resolve_link(path, target_path)
        return resolved or None
    if target_path.startswith(_REPO_ROOT_PREFIXES):
        normalised = _normalize_path(target_path)
        if normalised.endswith((".md", ".mdx")) and not Path(normalised).is_file():
            # Same existence gate as _resolve_link (roadmap §6) — a
            # repo-rooted read_next target that is gone mints a stale stub.
            return None
        normalised = _resolve_through_symlink(normalised)
        if not normalised:
            return None
        return f"doc:file:{normalised}"
    # Bare relative name — anchor against the source doc's directory.
    resolved = _resolve_link(path, target_path)
    return resolved or None


def _emit_read_next_targets(
    path: str,
    raw_value: str,
    result: ExtractionResult,
    *,
    source: str,
) -> None:
    """Emit one ``read_next`` edge per parsed target in ``raw_value``."""
    for target_path in _split_read_targets(raw_value):
        target_uid = _resolve_read_target(path, target_path)
        if not target_uid:
            continue
        result.edges.append(
            GraphEdge(
                source_uid=file_uid(path),
                target_uid=target_uid,
                edge_type="read_next",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                source_span=f"{_normalize_path(path)}:{source}",
            )
        )


def _extract_opening_block_reads(path: str, content: str, result: ExtractionResult) -> None:
    """Parse opening-block ``Read next:`` (long) and ``> N:`` (short)."""
    seen_targets: set[str] = set()
    for match in _OPENING_READ_NEXT_RE.finditer(content):
        for target_path in _split_read_targets(match.group("targets")):
            if target_path in seen_targets:
                continue
            seen_targets.add(target_path)
            target_uid = _resolve_read_target(path, target_path)
            if not target_uid:
                continue
            result.edges.append(
                GraphEdge(
                    source_uid=file_uid(path),
                    target_uid=target_uid,
                    edge_type="read_next",
                    extractor=EXTRACTOR_ID,
                    confidence=0.9,
                    source_span=f"{_normalize_path(path)}:opening-block",
                )
            )
