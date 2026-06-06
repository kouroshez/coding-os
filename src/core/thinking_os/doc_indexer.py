"""
Coding OS — Document indexer for RAG retrieval.

Walks the project's `docs/` tree, chunks markdown by H2/H3 headings, and
stores chunks in the `document_chunks` table with embeddings in the
`embeddings` table. Designed for incremental updates: only files whose
mtime changed since the last index are re-chunked.

Configuration lives in `.coding-os/rag-config.yaml`. The indexer reads
the source list, walks each path, applies excludes, chunks each markdown
file, and writes chunks + embeddings.

Public API:
    chunk_markdown(content, max_chars, overlap_chars) -> list[dict]
    load_rag_config(path) -> dict
    walk_sources(sources, project_root, global_excludes) -> list[(Path, source_config)]
    index_docs(conn, config_path, project_root, force) -> dict

CLI entry point:
    python -m doc_indexer --config .coding-os/rag-config.yaml [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sqlite3
import sys
from collections.abc import Iterable
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Markdown chunking
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Config loader + source walker
# ---------------------------------------------------------------------------


def load_rag_config(config_path: Path) -> dict:
    """Load and validate the RAG indexer config.

    Defers yaml import so the indexer module is importable in environments
    without pyyaml (e.g. minimal hook environments).

    Args:
        config_path: Path to rag-config.yaml.

    Returns:
        Parsed config dict with `sources` and `exclude` keys.

    Raises:
        FileNotFoundError: if config file missing.
        ValueError: if config schema is invalid.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"RAG config not found: {config_path}")
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "pyyaml is required to load rag-config.yaml — install via pip install pyyaml"
        ) from exc

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    sources = config.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError(f"rag-config sources must be a list, got {type(sources).__name__}")

    excludes = config.get("exclude", [])
    if not isinstance(excludes, list):
        raise ValueError(f"rag-config exclude must be a list, got {type(excludes).__name__}")

    return {"sources": sources, "exclude": excludes}


def walk_sources(
    sources: list[dict],
    project_root: Path,
    global_excludes: list[str],
) -> list[tuple[Path, dict]]:
    """Walk the configured source paths and return all markdown files with metadata.

    Args:
        sources: List of source config dicts (each with `path`, `type`, optional
                 `exclude`, `priority`, `chunk_size`).
        project_root: Project root the paths are relative to.
        global_excludes: Project-level exclude paths from config.

    Returns:
        List of (file_path, source_config) tuples for every markdown file
        matched by a source and not blocked by an exclude.
    """
    results: list[tuple[Path, dict]] = []
    global_exclude_paths = {(project_root / e).resolve() for e in global_excludes}

    for source in sources:
        rel_path = source.get("path")
        if not rel_path:
            continue
        source_root = (project_root / rel_path).resolve()
        if not source_root.exists():
            logger.debug("Source path missing, skipping: %s", source_root)
            continue

        local_excludes = source.get("exclude", []) or []
        local_exclude_paths = {(source_root / e).resolve() for e in local_excludes}

        if source_root.is_file():
            candidates = [source_root]
        else:
            candidates = sorted(source_root.rglob("*.md"))

        for candidate in candidates:
            if not candidate.is_file() or candidate.suffix != ".md":
                continue
            # Skip if matched by any exclude
            if _is_excluded(candidate, global_exclude_paths | local_exclude_paths):
                continue
            results.append((candidate, source))

    return results


def _is_excluded(file_path: Path, exclude_paths: set[Path]) -> bool:
    """Check whether file_path is inside any of the excluded paths."""
    resolved = file_path.resolve()
    for excluded in exclude_paths:
        try:
            resolved.relative_to(excluded)
            return True
        except ValueError:
            continue
        if resolved == excluded:
            return True
    return False


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------


def index_docs(
    conn: sqlite3.Connection,
    config_path: Path,
    project_root: Path,
    force: bool = False,
) -> dict:
    """Index every markdown file in `docs/` per the RAG config.

    For each file:
      1. Compare mtime with the max stored mtime for that source_path.
      2. If unchanged and not force → skip.
      3. Otherwise: delete existing chunks for that path, re-chunk, insert,
         and embed each new chunk.

    Args:
        conn: Migrated SQLite connection (must include v5).
        config_path: Path to rag-config.yaml.
        project_root: Project root (for resolving relative source paths).
        force: When True, re-index every file regardless of mtime.

    Returns:
        Stats dict: {processed, skipped, new_chunks, updated_files, deleted_files, errors}.
    """
    config = load_rag_config(config_path)
    # Resolve project_root to match the resolved paths returned by walk_sources.
    # On macOS /tmp → /private/tmp symlink, so the raw argument and the walked
    # paths can differ even though they point at the same directory. Always
    # compare resolved-to-resolved to avoid ValueError in relative_to().
    project_root_resolved = project_root.resolve()
    files = walk_sources(config["sources"], project_root_resolved, config["exclude"])

    stats = {
        "processed": 0,
        "skipped": 0,
        "new_chunks": 0,
        "updated_files": 0,
        "deleted_files": 0,
        "errors": 0,
        "missing_frontmatter": 0,
    }

    seen_paths: set[str] = set()

    for file_path, source_config in files:
        rel_path = str(file_path.resolve().relative_to(project_root_resolved))
        seen_paths.add(rel_path)
        stats["processed"] += 1

        try:
            file_mtime = int(file_path.stat().st_mtime)
        except OSError as exc:
            logger.warning("Cannot stat %s: %s", rel_path, exc)
            stats["errors"] += 1
            continue

        if not force:
            existing_mtime = _get_max_mtime(conn, rel_path)
            if existing_mtime is not None and existing_mtime >= file_mtime:
                stats["skipped"] += 1
                continue

        # File is new or modified — replace its chunks
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", rel_path, exc)
            stats["errors"] += 1
            continue

        max_chars = int(source_config.get("chunk_size", DEFAULT_MAX_CHARS))
        overlap = int(source_config.get("chunk_overlap", DEFAULT_OVERLAP_CHARS))
        chunks = chunk_markdown(content, max_chars=max_chars, overlap_chars=overlap)

        # Stage-1 RAG metadata — frontmatter parsed BEFORE the chunker
        # strips it. Written to columns added in migration v22 so
        # cos_doc_search can pre-filter by domain/layer/updated.
        fm = _parse_front_matter(content)
        # D3-F7 (TASK-124): surface files with a body but no parseable
        # frontmatter — previously a silent logger.debug, invisible in the
        # index summary. A leading `<!--` that simply didn't match is a
        # malformed header, not a missing one; both count as a Stage-1 gap.
        if not fm:
            _stripped = content.lstrip()
            if _stripped:
                stats["missing_frontmatter"] += 1

        # Delete previous chunks (and their embeddings)
        _delete_chunks_for_path(conn, rel_path)

        if not chunks:
            stats["updated_files"] += 1
            continue

        source_type = source_config.get("type", "doc")
        priority = float(source_config.get("priority", 0.5))

        for chunk in chunks:
            cursor = conn.execute(
                "INSERT INTO document_chunks "
                "(source_path, source_type, chunk_index, heading_path, content, content_hash, priority, mtime, "
                " domain, layer, ssot, updated_iso, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    rel_path,
                    source_type,
                    chunk["chunk_index"],
                    chunk["heading_path"],
                    chunk["content"],
                    chunk["content_hash"],
                    priority,
                    file_mtime,
                    fm.get("domain"),
                    fm.get("layer"),
                    fm.get("ssot"),
                    fm.get("updated_iso"),
                ),
            )
            stats["new_chunks"] += 1
            chunk_db_id = cursor.lastrowid
            _embed_chunk_safe(conn, chunk_db_id, chunk["heading_path"], chunk["content"])

        conn.commit()
        stats["updated_files"] += 1

    # Cleanup chunks for files no longer present
    stats["deleted_files"] = _delete_orphaned_chunks(conn, seen_paths)
    conn.commit()

    return stats


def _match_source_config(
    file_path: Path,
    sources: list[dict],
    project_root: Path,
    global_excludes: list[str],
) -> dict | None:
    """Return the source_config dict whose scope covers `file_path`, or None."""
    if not file_path.exists():
        return None
    resolved = file_path.resolve()
    project_root_resolved = project_root.resolve()

    try:
        resolved.relative_to(project_root_resolved)
    except ValueError:
        return None

    global_exclude_paths = {(project_root_resolved / e).resolve() for e in global_excludes}
    if _is_excluded(resolved, global_exclude_paths):
        return None

    # Pick the most-specific source (longest matching path) so e.g.
    # docs/architecture/adr/*.md wins over docs/architecture/*.md.
    best: tuple[int, dict] | None = None
    for source in sources:
        rel_path = source.get("path")
        if not rel_path:
            continue
        source_root = (project_root_resolved / rel_path).resolve()
        try:
            resolved.relative_to(source_root)
        except ValueError:
            continue
        local_excludes = source.get("exclude", []) or []
        local_exclude_paths = {(source_root / e).resolve() for e in local_excludes}
        if _is_excluded(resolved, local_exclude_paths):
            continue
        specificity = len(source_root.parts)
        if best is None or specificity > best[0]:
            best = (specificity, source)
    return best[1] if best else None


def index_single_file(
    conn: sqlite3.Connection,
    file_path: Path | str,
    *,
    project_root: Path | str,
    config_path: Path | str = ".coding-os/rag-config.yaml",
    force: bool = False,
) -> dict:
    """Incrementally re-index a single markdown file."""
    file_path = Path(file_path)
    project_root = Path(project_root)
    config_path = Path(config_path)

    config = load_rag_config(config_path)
    project_root_resolved = project_root.resolve()

    if file_path.is_absolute():
        abs_path = file_path
    else:
        abs_path = (project_root_resolved / file_path).resolve()
    try:
        rel_path = str(abs_path.resolve().relative_to(project_root_resolved))
    except ValueError:
        return {
            "status": "unscoped",
            "file": str(file_path),
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    # Missing on disk → treat as delete signal (cleanup ghost chunks).
    if not abs_path.exists():
        existed = (
            conn.execute(
                "SELECT 1 FROM document_chunks WHERE source_path = ? LIMIT 1",
                (rel_path,),
            ).fetchone()
            is not None
        )
        if existed:
            _delete_chunks_for_path(conn, rel_path)
            conn.commit()
            return {
                "status": "deleted",
                "file": rel_path,
                "new_chunks": 0,
                "deleted_chunks": 1,
                "source_type": None,
            }
        return {
            "status": "missing",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    source_config = _match_source_config(
        abs_path,
        config["sources"],
        project_root_resolved,
        config["exclude"],
    )
    if source_config is None:
        return {
            "status": "unscoped",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    if abs_path.suffix != ".md":
        return {
            "status": "unscoped",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    try:
        current_mtime = int(abs_path.stat().st_mtime)
    except OSError as exc:
        logger.debug("index_single_file stat failed for %s: %s", rel_path, exc)
        return {
            "status": "error",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    if not force:
        stored = _get_max_mtime(conn, rel_path)
        if stored is not None and stored >= current_mtime:
            return {
                "status": "unchanged",
                "file": rel_path,
                "new_chunks": 0,
                "deleted_chunks": 0,
                "source_type": source_config.get("type", "doc"),
            }

    try:
        content = abs_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.debug("index_single_file read failed for %s: %s", rel_path, exc)
        return {
            "status": "error",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": 0,
            "source_type": None,
        }

    max_chars = int(source_config.get("chunk_size", DEFAULT_MAX_CHARS))
    overlap = int(source_config.get("chunk_overlap", DEFAULT_OVERLAP_CHARS))
    chunks = chunk_markdown(content, max_chars=max_chars, overlap_chars=overlap)
    fm = _parse_front_matter(content)

    existing_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM document_chunks WHERE source_path = ?",
            (rel_path,),
        ).fetchall()
    ]
    _delete_chunks_for_path(conn, rel_path)

    if not chunks:
        conn.commit()
        return {
            "status": "reindexed",
            "file": rel_path,
            "new_chunks": 0,
            "deleted_chunks": len(existing_ids),
            "source_type": source_config.get("type", "doc"),
        }

    source_type = source_config.get("type", "doc")
    priority = float(source_config.get("priority", 0.5))
    new_chunk_count = 0

    for chunk in chunks:
        cursor = conn.execute(
            "INSERT INTO document_chunks "
            "(source_path, source_type, chunk_index, heading_path, content, "
            " content_hash, priority, mtime, "
            " domain, layer, ssot, updated_iso, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (
                rel_path,
                source_type,
                chunk["chunk_index"],
                chunk["heading_path"],
                chunk["content"],
                chunk["content_hash"],
                priority,
                current_mtime,
                fm.get("domain"),
                fm.get("layer"),
                fm.get("ssot"),
                fm.get("updated_iso"),
            ),
        )
        new_chunk_count += 1
        chunk_db_id = cursor.lastrowid
        _embed_chunk_safe(conn, chunk_db_id, chunk["heading_path"], chunk["content"])

    conn.commit()
    return {
        "status": "reindexed",
        "file": rel_path,
        "new_chunks": new_chunk_count,
        "deleted_chunks": len(existing_ids),
        "source_type": source_type,
    }


def _get_max_mtime(conn: sqlite3.Connection, source_path: str) -> int | None:
    """Return the maximum mtime stored for `source_path`, or None if no rows."""
    row = conn.execute(
        "SELECT MAX(mtime) FROM document_chunks WHERE source_path = ?",
        (source_path,),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _delete_chunks_for_path(conn: sqlite3.Connection, source_path: str) -> None:
    """Delete all chunks (and their embeddings) for the given source path."""
    chunk_ids = [
        r[0]
        for r in conn.execute(
            "SELECT id FROM document_chunks WHERE source_path = ?", (source_path,)
        ).fetchall()
    ]
    if not chunk_ids:
        return
    placeholders = ",".join("?" * len(chunk_ids))
    conn.execute(
        f"DELETE FROM embeddings WHERE source_table = 'document_chunks' AND source_id IN ({placeholders})",
        chunk_ids,
    )
    conn.execute("DELETE FROM document_chunks WHERE source_path = ?", (source_path,))


def _delete_orphaned_chunks(conn: sqlite3.Connection, seen_paths: set[str]) -> int:
    """Delete chunks for files that are no longer in the configured sources.

    Args:
        conn: SQLite connection.
        seen_paths: Set of source_path strings that ARE still present.

    Returns:
        Count of files whose chunks were deleted.
    """
    existing = {
        r[0] for r in conn.execute("SELECT DISTINCT source_path FROM document_chunks").fetchall()
    }
    orphaned = existing - seen_paths
    for path in orphaned:
        _delete_chunks_for_path(conn, path)
    return len(orphaned)


def _embed_chunk_safe(
    conn: sqlite3.Connection,
    chunk_id: int,
    heading_path: str,
    content: str,
) -> None:
    """Embed a document chunk. Errors logged at debug level only."""
    try:
        from embeddings import upsert_embedding
    except ImportError as exc:
        logger.debug("Skipping chunk embedding (module unavailable): %s", exc)
        return
    try:
        text_to_embed = " ".join(filter(None, [heading_path, content]))
        upsert_embedding(conn, "document_chunks", chunk_id, text_to_embed)
    except sqlite3.OperationalError as exc:
        logger.debug("Skipping chunk embedding (table missing): %s", exc)
    except Exception as exc:  # pragma: no cover
        logger.debug("Skipping chunk embedding (unexpected): %s", exc)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    parser = argparse.ArgumentParser(description="Index docs/ for RAG retrieval")
    parser.add_argument(
        "--config",
        type=str,
        default=".coding-os/rag-config.yaml",
        help="Path to rag-config.yaml (default: .coding-os/rag-config.yaml)",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=".",
        help="Project root (default: current directory)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-index every file regardless of mtime",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Override DB path (defaults to COS_DB_PATH)",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from database import init_db

    config_path = Path(args.config).resolve()
    project_root = Path(args.project_root).resolve()

    conn = init_db(args.db)
    try:
        stats = index_docs(conn, config_path, project_root, force=args.force)
    finally:
        conn.close()

    print(json.dumps({"status": "ok", "stats": stats}, indent=2))


if __name__ == "__main__":
    _main()
