"""Markdown chunking for the document RAG index.

Splits a document by H2/H3 heading, then windows any section that exceeds the
character budget, carrying an overlap so a fact spanning a window boundary is
still retrievable. Front-matter is parsed (not just stripped) because Stage-1
pre-filtering routes on domain / layer / ssot / updated.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable

logger = logging.getLogger("coding_os.doc_indexer")

# Default chunking budget (characters, not tokens — ~4 chars per token).
# 2000 chars ≈ 500 tokens, which fits comfortably under the embedding model's
# input limit and gives the agent useful chunk granularity.
DEFAULT_MAX_CHARS = 2000
DEFAULT_OVERLAP_CHARS = 200

# Regex for the standard front-matter header used by docs/governance/docs-system.md.
# Captured (NOT just stripped) so Stage-1 RAG pre-filtering can route on
# domain / layer / ssot / updated. The pipe-separated body is parsed by
# _parse_front_matter into the document_chunks metadata columns added in
# migration v22.
_FRONT_MATTER_RE = re.compile(r"^<!--\s*(domain:[^>]*?)\s*-->\s*\n?", re.MULTILINE)
_FRONT_MATTER_KV_RE = re.compile(r"([a-z_]+)\s*:\s*([^|]+?)(?=\s*\||$)")

# H1, H2, H3 detection
_H1_RE = re.compile(r"^# (.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_H3_RE = re.compile(r"^### (.+)$", re.MULTILINE)


def _parse_front_matter(content: str) -> dict[str, str]:
    """Extract `<!-- domain:X | layer:Y | ssot:Z | updated:DATE -->` keys."""
    match = _FRONT_MATTER_RE.search(content)
    if not match:
        # File has body but no parseable header → Stage-1 metadata filter is
        # off for this chunk. Log so the missing frontmatter surfaces in
        # `.coding-os/.reindex-errors.log` instead of silently degrading
        # cos_doc_search ranking.
        stripped = content.lstrip()
        if stripped and not stripped.startswith("<!--"):
            logger.debug(
                "doc_indexer: no parseable frontmatter (first line: %r)",
                stripped.splitlines()[0][:80] if stripped else "",
            )
        return {}
    body = match.group(1)
    pairs: dict[str, str] = {}
    for k, v in _FRONT_MATTER_KV_RE.findall(body):
        pairs[k.strip()] = v.strip()
    # Normalize: docs-system.md stores `updated:YYYY-MM-DD` — keep as-is
    # but expose under updated_iso for column clarity.
    if "updated" in pairs and "updated_iso" not in pairs:
        pairs["updated_iso"] = pairs.pop("updated")
    return pairs


def _strip_front_matter(content: str) -> str:
    """Remove the leading `<!-- domain:... -->` header before chunking."""
    return _FRONT_MATTER_RE.sub("", content, count=1)


def _extract_h1(content: str) -> str:
    """Return the first H1 line text, or 'Untitled' if no H1 found."""
    match = _H1_RE.search(content)
    return match.group(1).strip() if match else "Untitled"


def _split_by_pattern(content: str, pattern: re.Pattern) -> list[tuple[str, str]]:
    """Split content into (heading, body) sections at every match of pattern.

    Returns a list of (heading_text, body_text) tuples. Body of section N
    starts after its heading line and ends at the next heading or EOF.
    Content before the first match becomes the leading section with
    heading="" if non-empty.
    """
    matches = list(pattern.finditer(content))
    sections: list[tuple[str, str]] = []

    if not matches:
        if content.strip():
            sections.append(("", content.strip()))
        return sections

    # Leading content (before first heading)
    leading_end = matches[0].start()
    leading = content[:leading_end].strip()
    if leading:
        sections.append(("", leading))

    for i, match in enumerate(matches):
        heading_text = match.group(1).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()
        sections.append((heading_text, body))

    return sections


def _build_heading_path(h1: str, h2: str, h3: str = "") -> str:
    """Render a `H1 > H2 > H3` breadcrumb, omitting empty levels."""
    parts = [p for p in (h1, h2, h3) if p]
    return " > ".join(parts)


def chunk_markdown(
    content: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[dict]:
    """Split a markdown document into heading-aware chunks.

    Strategy:
      1. Strip leading `<!-- domain:... -->` front-matter.
      2. Extract H1 → use as the breadcrumb root.
      3. Strip H1 line + any preamble before the first H2 (already captured by H1 root).
      4. Split content at H2 boundaries. Each H2 becomes a candidate chunk.
      5. If an H2 chunk exceeds max_chars, split further at H3 boundaries.
      6. If still too large, fall back to paragraph-based windowing with overlap.

    Each returned chunk dict has:
      - chunk_index: 0-based ordinal within the document
      - heading_path: "H1 > H2 [> H3]" breadcrumb
      - content: raw text of the chunk (with H2/H3 prefix prepended for context)
      - content_hash: SHA256[:16] of the chunk content

    Args:
        content: Full markdown text.
        max_chars: Soft limit per chunk (default ~500 tokens).
        overlap_chars: Overlap between adjacent chunks at the leaf level.

    Returns:
        List of chunk dicts in document order. Empty list for empty input.
    """
    if not content or not content.strip():
        return []

    body = _strip_front_matter(content)
    h1 = _extract_h1(body)

    # Drop the H1 line itself from the body — it's captured as the breadcrumb
    # root, and including it as a separate "leading" chunk produces empty/duplicate
    # noise chunks. Keep any preamble *between* the H1 and the first H2 only when
    # the document has no H2 (i.e. flat docs).
    body_after_h1 = _H1_RE.sub("", body, count=1).lstrip()

    chunks: list[dict] = []
    chunk_idx = 0
    h2_sections = _split_by_pattern(body_after_h1, _H2_RE)

    # Detect whether the document has any real H2 headings. _split_by_pattern
    # always returns the leading content (if any) as ("", text); we need to
    # distinguish "no H2 at all" from "H2 with optional preamble".
    has_real_h2 = any(h2 != "" for h2, _ in h2_sections)

    if not h2_sections:
        # Empty body after H1 → nothing to chunk
        return []

    if not has_real_h2:
        # No H2 at all → whole doc is one chunk under the H1 root
        leading_body = h2_sections[0][1] if h2_sections else ""
        if leading_body:
            chunks.append(_build_chunk(0, _build_heading_path(h1, ""), leading_body))
        return chunks

    # We have at least one H2 — strip the leading "" preamble and attach it
    # to the first H2 chunk so we don't emit a noisy headerless chunk.
    if h2_sections[0][0] == "":
        preamble = h2_sections[0][1]
        h2_sections = h2_sections[1:]
        if h2_sections and preamble:
            first_h2, first_body = h2_sections[0]
            h2_sections[0] = (first_h2, f"{preamble}\n\n{first_body}")

    for h2, h2_body in h2_sections:
        if not h2_body:
            continue

        # If small enough, emit a single chunk
        if len(h2_body) <= max_chars:
            chunks.append(_build_chunk(chunk_idx, _build_heading_path(h1, h2), h2_body))
            chunk_idx += 1
            continue

        # Otherwise, try splitting by H3
        h3_sections = _split_by_pattern(h2_body, _H3_RE)
        # Use H3 splitting if there's at least one real H3 (heading != "")
        has_h3 = any(h3 != "" for h3, _ in h3_sections)
        if has_h3:
            for h3, h3_body in h3_sections:
                if not h3_body:
                    continue
                # Empty H3 means leading content before first H3 — keep
                # under the H2 heading path
                heading_path = (
                    _build_heading_path(h1, h2, h3) if h3 else _build_heading_path(h1, h2)
                )
                if len(h3_body) <= max_chars:
                    chunks.append(_build_chunk(chunk_idx, heading_path, h3_body))
                    chunk_idx += 1
                else:
                    # Still too big — paragraph-window
                    for window in _window_text(h3_body, max_chars, overlap_chars):
                        chunks.append(_build_chunk(chunk_idx, heading_path, window))
                        chunk_idx += 1
        else:
            # No H3 to split by — paragraph-window the H2 body
            for window in _window_text(h2_body, max_chars, overlap_chars):
                chunks.append(_build_chunk(chunk_idx, _build_heading_path(h1, h2), window))
                chunk_idx += 1

    return chunks


def _build_chunk(chunk_idx: int, heading_path: str, content: str) -> dict:
    """Construct a chunk dict with content_hash."""
    text = content.strip()
    return {
        "chunk_index": chunk_idx,
        "heading_path": heading_path,
        "content": text,
        "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
    }


def _window_text(text: str, max_chars: int, overlap: int) -> Iterable[str]:
    """Yield overlapping windows of `text`, each at most `max_chars` long.

    Tries to break on paragraph boundaries (double newline) when possible to
    avoid splitting mid-sentence. Falls back to hard char-based slicing when
    a single paragraph is larger than max_chars.
    """
    text = text.strip()
    if not text:
        return
    if len(text) <= max_chars:
        yield text
        return

    paragraphs = text.split("\n\n")
    buffer: list[str] = []
    buffer_len = 0
    overlap_text = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # If a single paragraph is larger than max_chars, hard-slice it.
        if len(para) > max_chars:
            if buffer:
                yield overlap_text + "\n\n".join(buffer)
                overlap_text = _take_tail(buffer, overlap)
                buffer = []
                buffer_len = 0
            for i in range(0, len(para), max_chars - overlap):
                window = para[i : i + max_chars]
                yield (overlap_text + window).strip() if overlap_text else window
                overlap_text = window[-overlap:] if overlap and len(window) >= overlap else ""
            continue

        if buffer_len + len(para) + 2 > max_chars and buffer:
            yield (overlap_text + "\n\n".join(buffer)).strip()
            overlap_text = _take_tail(buffer, overlap)
            buffer = [para]
            buffer_len = len(para)
        else:
            buffer.append(para)
            buffer_len += len(para) + 2

    if buffer:
        yield (overlap_text + "\n\n".join(buffer)).strip()


def _take_tail(buffer: list[str], overlap: int) -> str:
    """Return the last `overlap` chars of the buffered paragraphs as overlap context."""
    if overlap <= 0 or not buffer:
        return ""
    joined = "\n\n".join(buffer)
    if len(joined) <= overlap:
        return joined + "\n\n"
    return "..." + joined[-overlap:] + "\n\n"
