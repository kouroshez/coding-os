"""
Coding OS — Document RAG search tool (Phase B.4).

Provides `doc_search` — semantic search over the `document_chunks` table
populated by `doc_indexer`. Returns chunk-level results (300-500 tokens each)
with heading_path metadata so the agent can fetch only the relevant slice
of a doc instead of full-reading it.

Public API:
    doc_search(conn, query, source_types, limit, threshold, dedupe_per_source)
        -> list[dict]
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("coding_os.tools.docs")

# Default cap on results before dedupe + final limit. Pulling 3x the requested
# limit gives the dedupe step room to work without losing too much recall.
_OVERFETCH_MULTIPLIER = 3

# Default per-source dedupe cap when dedupe_per_source=True. Two chunks per
# source file is the sweet spot — enough for a section + neighbor without
# crowding the result list.
_MAX_PER_SOURCE = 2

# G.7.3 — identifier-looking query detection. Heuristic is deliberately
# permissive: if the user typed something code-shaped we route to FTS first
# because cosine similarity is weak on short literal tokens.
_IDENTIFIER_RE = re.compile(
    r"("
    r"[A-Za-z_][A-Za-z0-9_]*\(\)"     # function call syntax
    r"|[a-z]+(?:_[a-z0-9]+)+"          # snake_case (2+ segments)
    r"|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+"  # CamelCase (2+ segments)
    r"|TASK-\d+"                       # task id
    r"|`[^`]+`"                        # explicit backtick identifier
    r"|[a-zA-Z_][a-zA-Z0-9_]*\.py|\.ts|\.tsx|\.md"  # file with known ext
    r")"
)


def looks_like_identifier(query: str) -> bool:
    """Return True when `query` contains a code-shaped token."""
    if not query or not query.strip():
        return False
    return bool(_IDENTIFIER_RE.search(query))


SearchMode = Literal["auto", "semantic", "lexical"]


# ---------------------------------------------------------------------------
# Stage-1 metadata heuristics — query-time hint extraction + active-task context
# ---------------------------------------------------------------------------

# Domain hints — keyword → canonical domain. Conservative: only fire on
# unambiguous tokens. Extending: keep mapping data-driven (no logic in
# the regex), agents can override by passing domain= explicitly.
_DOMAIN_HINTS: dict[str, str] = {
    r"\bbackend\b|\bapi\b|\bhandler\b|\bendpoint\b|\bdjango\b|\bfastapi\b|\bfiber\b": "BACKEND",
    r"\bfrontend\b|\breact\b|\bnext\.?js\b|\bcomponent\b|\bpage\b|\bjsx\b|\btsx\b": "FRONTEND",
    r"\bauth\b|\boauth\b|\bjwt\b|\bsecret\b|\bsecurity\b|\bcsrf\b|\bxss\b": "SECURITY",
    r"\bdeploy\b|\bci/cd\b|\bdocker\b|\bk8s\b|\bkubernetes\b|\binfra\b|\brunbook\b": "OPS",
    r"\bllm\b|\bprompt\b|\bembedding\b|\brag\b|\bmodel\b|\btoken\b": "AI",
    r"\bmigration\b|\bsqlite\b|\bschema\b|\bdb\b|\bsql\b|\bquery\b|\bindex\b": "CORE",
    r"\bgraph\b|\bnode\b|\bedge\b|\bkuzu\b": "CORE",
    r"\bhook\b|\bregistry\b|\badapter\b|\bskill\b": "CORE",
}

# Layer hints — phrasing patterns → frontmatter layer value.
_LAYER_HINTS: dict[str, str] = {
    r"\b(?:adr|architecture decision)\b": "adr",
    r"\bplaybook\b|\bhow to\b|\bworkflow\b|\bprocedure\b": "playbook",
    r"\brunbook\b|\bincident\b|\balert\b|\bon[- ]call\b": "runbook",
    r"\bpost[- ]?mortem\b|\bretrospective\b|\bpostmortem\b": "postmortem",
    r"\bspec\b|\bcontract\b|\bschema\b|\bapi contract\b": "spec",
    r"\bpolicy\b|\brule\b|\bstandard\b": "policy",
}

# Recency hints — phrasing → days lookback. "Recent" is the loosest;
# explicit quarter / month is tightest.
_RECENCY_HINTS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"\bthis week\b|\btoday\b|\byesterday\b", re.I),    7),
    (re.compile(r"\bthis month\b|\bthis sprint\b",        re.I),   30),
    (re.compile(r"\bthis quarter\b|\bQ[1-4]\b",           re.I),   90),
    (re.compile(r"\brecent\b|\blatest\b|\bcurrent\b|\bnow\b", re.I), 90),
]

# Explicit ISO year / date hints — "since 2026", "2025 Q4 …", "after 2024-06".
_YEAR_RE = re.compile(r"\b(?:since|after|from)\s+(20\d{2})(?:-(\d{2}))?(?:-(\d{2}))?\b", re.I)
_BARE_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _suggest_filters_from_query(query: str) -> dict[str, Any]:
    """Heuristic query-time metadata extraction (non-binding hints)."""
    if not query:
        return {}
    text = query.lower()
    out: dict[str, Any] = {}

    # Domain hint — first match wins.
    for pat, dom in _DOMAIN_HINTS.items():
        if re.search(pat, text):
            out["suggested_domain"] = dom
            break

    # Layer hint — first match wins.
    for pat, layer in _LAYER_HINTS.items():
        if re.search(pat, text):
            out["suggested_layer"] = layer
            break

    # Recency: explicit "since YYYY[-MM[-DD]]" wins over phrasing.
    yr_match = _YEAR_RE.search(query)
    if yr_match:
        y, m, d = yr_match.group(1), yr_match.group(2) or "01", yr_match.group(3) or "01"
        out["suggested_since_iso"] = f"{y}-{m}-{d}"
    else:
        for rx, days in _RECENCY_HINTS:
            if rx.search(query):
                cutoff = datetime.utcnow().date() - timedelta(days=days)
                out["suggested_since_iso"] = cutoff.isoformat()
                break
        # Bare 4-digit year — only if no recency phrasing already won.
        if "suggested_since_iso" not in out:
            bare = _BARE_YEAR_RE.search(query)
            if bare:
                out["suggested_since_iso"] = f"{bare.group(1)}-01-01"

    return out


# Swimlane → frontmatter domain. Coarse mapping; agent can override with
# explicit domain=. Missing swimlanes leave domain unset.
_SWIMLANE_DOMAIN: dict[str, str] = {
    "core":    "CORE",
    "backend": "BACKEND",
    "be":      "BACKEND",
    "frontend": "FRONTEND",
    "fe":      "FRONTEND",
    "ai":      "AI",
    "ops":     "OPS",
    "infra":   "OPS",
    "security": "SECURITY",
    "docs":    "DOCS",
}


def _active_task_context() -> dict[str, str]:
    """Read the active task's swimlane / kind from $COS_AGENT_DIR."""
    agent_dir_str = os.environ.get("COS_AGENT_DIR", "")
    if not agent_dir_str:
        return {}
    agent_dir = Path(agent_dir_str)
    out: dict[str, str] = {}
    swim_path = agent_dir / ".swimlane"
    if swim_path.exists():
        try:
            swim = swim_path.read_text(encoding="utf-8").strip().lower()
            if swim and swim in _SWIMLANE_DOMAIN:
                out["domain"] = _SWIMLANE_DOMAIN[swim]
        except OSError as exc:
            logger.debug("active-task swimlane read failed: %s", exc)
    return out


def _build_metadata_filter(
    *,
    source_types: list[str] | None,
    domain: str | None,
    layer: str | None,
    since_iso: str | None,
    include_inactive: bool,
    table_alias: str = "",
) -> tuple[str, list[Any]]:
    """Stage-1 RAG pre-filter SQL fragment + params."""
    p = table_alias if table_alias.endswith(".") or not table_alias else f"{table_alias}."
    if table_alias and not p.endswith("."):
        p = f"{table_alias}."
    parts: list[str] = []
    params: list[Any] = []
    if source_types:
        parts.append(f"{p}source_type IN ({','.join('?' * len(source_types))})")
        params.extend(source_types)
    if domain is not None:
        parts.append(f"{p}domain = ?")
        params.append(domain)
    if layer is not None:
        parts.append(f"{p}layer = ?")
        params.append(layer)
    if since_iso is not None:
        parts.append(f"{p}updated_iso >= ?")
        params.append(since_iso)
    if not include_inactive:
        parts.append(f"({p}is_active = 1 OR {p}is_active IS NULL)")
    if not parts:
        return "", []
    return " AND " + " AND ".join(parts), params


def doc_search(
    conn: sqlite3.Connection,
    query: str,
    source_types: list[str] | None = None,
    limit: int = 5,
    threshold: float = 0.05,
    dedupe_per_source: bool = True,
    mode: SearchMode = "auto",
    *,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
    auto_context: bool = False,
    return_meta: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Semantic + lexical search over project documentation chunks.

    Stage-1 metadata pre-filter (since migration v22): the optional
    `domain`, `layer`, `since_iso`, and `include_inactive` arguments
    narrow the chunk universe BEFORE vector / FTS ranking. This is the
    "metadata enforces reality" half of production RAG — vector finds
    meaning, metadata decides which docs are even allowed to compete.

    Args:
        conn: Open SQLite connection (must include migration v5+; v9 adds
            the document_chunks_fts table; v22 adds frontmatter columns).
        query: Natural language query (e.g. "commission rate calculation").
        source_types: Optional filter — only return chunks whose source_type
            matches one of these values (e.g. ["prd", "architecture"]).
        limit: Maximum results to return (1-50).
        threshold: Minimum cosine similarity (default 0.05 — tuned for
            all-MiniLM-L6-v2 on short queries).
        dedupe_per_source: When True, return at most _MAX_PER_SOURCE chunks
            per source_path so a single dominant file doesn't crowd out others.
        mode: Retrieval mode (Phase G.7.3):
            - "auto"     → identifier-looking query → FTS first, else semantic;
                           fall back to the other on empty.
            - "semantic" → embeddings-only (legacy behavior).
            - "lexical"  → FTS5 match only (no embedding even if available).
        domain: Pre-filter on docs/governance/docs-system.md frontmatter
            domain field (BACKEND, FRONTEND, OPS, DOCS, …). None = any.
        layer: Pre-filter on frontmatter layer (adr, playbook, spec,
            policy, reference, runbook, postmortem, task). None = any.
        since_iso: Lower bound on frontmatter `updated:` (YYYY-MM-DD).
            Useful when an agent asks about "recent" / "current" state and
            stale older docs would be a wrong answer. None = any age.
        include_inactive: When False (default), hide chunks whose row was
            marked is_active=0 by cos_audit_log_record (action='deleted'
            or 'reverted'). Set True for forensic / audit retrieval.
        auto_context: When True AND `domain` was not passed explicitly,
            read the active task's swimlane from $COS_AGENT_DIR/.swimlane
            and apply it as the default domain filter. Soft default —
            never overrides an explicit `domain=` argument. Off by
            default to keep search behavior predictable in tests.
        return_meta: When True, returns (results, meta) tuple where meta
            carries `filter_hints` (heuristic suggestions extracted from
            the query) and `applied` (which filters actually ran). Keeps
            the legacy list-only return shape when False (default).

    Returns:
        List of result dicts (or `(results, meta)` when `return_meta=True`).
        Each result carries a `retrieval_source` field so callers / audit
        can tell whether the row came from semantic or lexical.
    """
    if not query or not query.strip():
        return ([], {"filter_hints": {}, "applied": {}}) if return_meta else []

    # Cap inputs to defensive limits
    limit = max(1, min(int(limit), 50))

    # Soft defaults from active task context. Explicit kwargs always win.
    applied_domain = domain
    if auto_context and applied_domain is None:
        ctx = _active_task_context()
        applied_domain = ctx.get("domain")

    results: list[dict] = []

    md_kwargs = dict(
        source_types=source_types, domain=applied_domain, layer=layer,
        since_iso=since_iso, include_inactive=include_inactive,
    )

    if mode == "lexical":
        results = _lexical_search(conn, query, limit, **md_kwargs)
    elif mode == "semantic":
        results = _semantic_search(conn, query, limit, threshold, **md_kwargs)
    else:  # auto
        # Identifier-looking → FTS first; else semantic first.
        identifier_first = looks_like_identifier(query)
        if identifier_first:
            results = _lexical_search(conn, query, limit, **md_kwargs)
            if not results:
                results = _semantic_search(conn, query, limit, threshold, **md_kwargs)
        else:
            results = _semantic_search(conn, query, limit, threshold, **md_kwargs)
            if not results:
                results = _lexical_search(conn, query, limit, **md_kwargs)

    if dedupe_per_source:
        per_source_count: dict[str, int] = {}
        deduped: list[dict] = []
        for item in results:
            count = per_source_count.get(item["source_path"], 0)
            if count >= _MAX_PER_SOURCE:
                continue
            per_source_count[item["source_path"]] = count + 1
            deduped.append(item)
        results = deduped

    final = results[:limit]
    if not return_meta:
        return final

    applied = {
        k: v for k, v in {
            "source_types": source_types,
            "domain": applied_domain,
            "layer": layer,
            "since_iso": since_iso,
            "include_inactive": include_inactive or None,
            "auto_context": auto_context or None,
        }.items() if v is not None
    }
    meta = {
        "filter_hints": _suggest_filters_from_query(query),
        "applied": applied,
    }
    return final, meta


def _semantic_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    threshold: float,
    *,
    source_types: list[str] | None = None,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    """Embedding-based similarity search (previous default path).

    Returns an empty list when embeddings are unavailable or nothing crosses
    the threshold — callers route to lexical fallback on empty.
    """
    try:
        from embeddings import is_available, search_similar
    except ImportError as exc:
        logger.debug("_semantic_search unavailable (module): %s", exc)
        return []

    if not is_available():
        return []

    overfetch = limit * _OVERFETCH_MULTIPLIER
    raw_results = search_similar(
        conn,
        query=query,
        source_tables=["document_chunks"],
        limit=overfetch,
        threshold=threshold,
    )
    if not raw_results:
        return []

    chunk_ids = [r["source_id"] for r in raw_results]
    score_by_id = {r["source_id"]: r["score"] for r in raw_results}

    placeholders = ",".join("?" * len(chunk_ids))
    sql = (
        "SELECT id, source_path, source_type, chunk_index, heading_path, "
        "content, priority, mtime FROM document_chunks "
        f"WHERE id IN ({placeholders})"
    )
    params: list[Any] = list(chunk_ids)
    md_clause, md_params = _build_metadata_filter(
        source_types=source_types, domain=domain, layer=layer,
        since_iso=since_iso, include_inactive=include_inactive,
    )
    sql += md_clause
    params.extend(md_params)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("_semantic_search query failed: %s", exc)
        return []

    hydrated: list[dict] = []
    for row in rows:
        chunk_id = row["id"]
        cosine_score = score_by_id.get(chunk_id, 0.0)
        priority = row["priority"] if row["priority"] is not None else 0.5
        final_score = cosine_score * (0.85 + 0.3 * priority)
        hydrated.append({
            "id": chunk_id,
            "source_path": row["source_path"],
            "source_type": row["source_type"],
            "heading_path": row["heading_path"],
            "content": row["content"],
            "score": final_score,
            "cosine": cosine_score,
            "priority": priority,
            "mtime": row["mtime"],
            "chunk_index": row["chunk_index"],
            "retrieval_source": "semantic",
        })
    hydrated.sort(key=lambda d: d["score"], reverse=True)
    return hydrated


def _lexical_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    source_types: list[str] | None = None,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    """FTS5 lexical search over document_chunks_fts (v9+).

    Falls back to a LIKE query when the FTS virtual table is absent
    (FTS5 unavailable or pre-v9). The LIKE path is intentionally scan-heavy
    — acceptable because it is only a last-resort fallback.
    """
    from db import has_document_chunks_fts  # avoid circular at module top

    overfetch = limit * _OVERFETCH_MULTIPLIER
    md_kwargs = dict(
        source_types=source_types, domain=domain, layer=layer,
        since_iso=since_iso, include_inactive=include_inactive,
    )

    if has_document_chunks_fts(conn):
        try:
            return _fts_hydrate(conn, query, overfetch, **md_kwargs)
        except sqlite3.OperationalError as exc:
            # FTS5 query syntax errors (special chars) — fall through to LIKE.
            logger.debug("_lexical_search FTS failed, falling back to LIKE: %s", exc)

    return _like_hydrate(conn, query, overfetch, **md_kwargs)


def _fts_hydrate(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    source_types: list[str] | None = None,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    """FTS5 MATCH join back to document_chunks with priority boost."""
    md_clause, md_params = _build_metadata_filter(
        source_types=source_types, domain=domain, layer=layer,
        since_iso=since_iso, include_inactive=include_inactive,
        table_alias="dc",
    )
    sql = (
        "SELECT dc.id, dc.source_path, dc.source_type, dc.chunk_index, "
        "dc.heading_path, dc.content, dc.priority, dc.mtime, f.rank AS fts_rank "
        "FROM document_chunks_fts f "
        "JOIN document_chunks dc ON dc.id = f.rowid "
        "WHERE document_chunks_fts MATCH ?"
        + md_clause
        + " ORDER BY f.rank LIMIT ?"
    )
    params: list[Any] = [query, *md_params, limit]
    rows = conn.execute(sql, params).fetchall()

    hydrated: list[dict] = []
    for row in rows:
        # Normalize FTS5 rank (negative, closer to 0 = better) into [0, 1].
        raw_rank = abs(row["fts_rank"] or 0.0)
        lexical_score = 1.0 / (1.0 + raw_rank)
        priority = row["priority"] if row["priority"] is not None else 0.5
        final_score = lexical_score * (0.85 + 0.3 * priority)
        hydrated.append({
            "id": row["id"],
            "source_path": row["source_path"],
            "source_type": row["source_type"],
            "heading_path": row["heading_path"],
            "content": row["content"],
            "score": final_score,
            "cosine": 0.0,  # N/A on lexical path
            "priority": priority,
            "mtime": row["mtime"],
            "chunk_index": row["chunk_index"],
            "retrieval_source": "lexical",
        })
    return hydrated


def _like_hydrate(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    *,
    source_types: list[str] | None = None,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    """Final fallback: LIKE scan when neither embeddings nor FTS5 available."""
    like_pattern = f"%{query}%"
    params: list[Any] = [like_pattern, like_pattern]
    sql = (
        "SELECT id, source_path, source_type, chunk_index, heading_path, "
        "content, priority, mtime FROM document_chunks "
        "WHERE (content LIKE ? OR heading_path LIKE ?)"
    )
    md_clause, md_params = _build_metadata_filter(
        source_types=source_types, domain=domain, layer=layer,
        since_iso=since_iso, include_inactive=include_inactive,
    )
    sql += md_clause
    params.extend(md_params)
    sql += " ORDER BY priority DESC, mtime DESC LIMIT ?"
    params.append(limit)

    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("_like_hydrate failed: %s", exc)
        return []

    return [
        {
            "id": r["id"],
            "source_path": r["source_path"],
            "source_type": r["source_type"],
            "heading_path": r["heading_path"],
            "content": r["content"],
            "score": 0.4,  # fixed moderate score for LIKE hits
            "cosine": 0.0,
            "priority": r["priority"] if r["priority"] is not None else 0.5,
            "mtime": r["mtime"],
            "chunk_index": r["chunk_index"],
            "retrieval_source": "lexical-like",
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Header-only lazy load — Phase O.4
# ---------------------------------------------------------------------------
#
# Pattern mirrors how Anthropic skills surface (frontmatter loads, body lazy):
# the agent reads ONLY a doc's frontmatter + opening block (Purpose / Read
# when / Skip when / Read next) before deciding whether the body is worth
# spending tokens on. Saves ~70-90% on doc-decision loops where the agent is
# routing between candidate docs.
#
# Two surface tools (registered in server.py):
#   cos_doc_header(path)            — single doc header
#   cos_doc_headers_by(domain, …)   — bulk filter by frontmatter fields
#
# Both bypass the embeddings store entirely. Filesystem reads are bounded to
# the first ~3 KB of each candidate file — enough to cover the largest
# observed opening blocks with margin.

# Frontmatter HTML comment shape:
#   <!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-28 \
#        | tokens:1800 | reads:[a,b,c] -->
_FRONTMATTER_RE = re.compile(r"^\s*<!--\s*(.+?)\s*-->", re.DOTALL)

# Long-form opening block lines.
_LONG_OPENING_RE = {
    "purpose":   re.compile(r"^Purpose:\s*(.+?)\s*$", re.M),
    "read_when": re.compile(r"^Read when:\s*(.+?)\s*$", re.M),
    "skip_when": re.compile(r"^Skip when:\s*(.+?)\s*$", re.M),
    "read_next": re.compile(r"^Read next:\s*(.+?)\s*$", re.M),
}

# Short-form (TASK-158) — accept either form. Short form lives inside a
# blockquote: `> P: …` / `> R: …` / `> S: …` / `> N: …`.
_SHORT_OPENING_RE = {
    "purpose":   re.compile(r"^>\s*P:\s*(.+?)\s*$", re.M),
    "read_when": re.compile(r"^>\s*R:\s*(.+?)\s*$", re.M),
    "skip_when": re.compile(r"^>\s*S:\s*(.+?)\s*$", re.M),
    "read_next": re.compile(r"^>\s*N:\s*(.+?)\s*$", re.M),
}

# H1 detection — first level-1 heading wins.
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)

# Header read budget — first 3 KB of any doc covers all canonical openings
# observed in the scaffold + meta-repo. Cheap to read; never touches the body.
_HEADER_READ_BYTES = 3072

# Bulk scan budget — defensive cap to keep cos_doc_headers_by snappy.
_BULK_MAX_RESULTS = 50


def _parse_frontmatter_block(text: str) -> dict[str, Any]:
    """Parse the leading `<!-- key:value | … -->` block."""
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
    """Extract Purpose / Read when / Skip when / Read next (long OR short)."""
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
        if len(rows) >= limit:
            break

    def _sort_key(h: dict[str, Any]) -> tuple[float, str]:
        fm = h.get("frontmatter") or {}
        priority = fm.get("priority")
        try:
            priority_num = float(priority) if priority is not None else 0.5
        except (TypeError, ValueError):
            priority_num = 0.5
        updated = str(fm.get("updated") or "")
        return (-priority_num, updated)

    rows.sort(key=_sort_key)
    return rows


# ---------------------------------------------------------------------------
# Section index lookup (TASK-165 — intra-file navigation)
# ---------------------------------------------------------------------------

_SECTION_INDEX_ROW_RE = re.compile(
    r"^\|\s*H\d\s*\|\s*(?P<title>.+?)\s*\|\s*`(?P<slug>[^`]+)`\s*\|\s*"
    r"(?P<start>\d+)\s*\|\s*(?P<end>\d+)\s*\|\s*(?P<lines>\d+)\s*\|\s*"
    r"(?P<tokens>\d+)\s*\|\s*$"
)


def _index_path_for(source: Path) -> Path:
    """Return the sidecar `<source-stem>.INDEX.md` next to `source`."""
    return source.with_name(source.stem + ".INDEX.md")


def _parse_section_index(index_file: Path) -> list[dict[str, Any]]:
    """Parse the auto-generated table inside a `<file>.INDEX.md`."""
    if not index_file.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        text = index_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        m = _SECTION_INDEX_ROW_RE.match(line)
        if not m:
            continue
        try:
            rows.append({
                "title": m.group("title").strip(),
                "slug": m.group("slug").strip(),
                "start": int(m.group("start")),
                "end": int(m.group("end")),
                "lines": int(m.group("lines")),
                "tokens": int(m.group("tokens")),
            })
        except (TypeError, ValueError):
            continue
    return rows


def _match_section(
    rows: list[dict[str, Any]],
    *,
    slug: str = "",
    section: str = "",
) -> dict[str, Any] | None:
    """Pick a section row by slug (exact) or fuzzy title match.

    Resolution order:
        1. exact slug match
        2. case-insensitive slug match
        3. case-insensitive substring match on title
    Returns None when nothing matches.
    """
    if not rows:
        return None
    if slug:
        for r in rows:
            if r["slug"] == slug:
                return r
        slug_lc = slug.lower()
        for r in rows:
            if r["slug"].lower() == slug_lc:
                return r
    if section:
        sec_lc = section.lower()
        for r in rows:
            if sec_lc in r["title"].lower():
                return r
    return None


def doc_section(
    source: Path,
    *,
    slug: str = "",
    section: str = "",
    with_body: bool = True,
) -> dict[str, Any] | None:
    """Return one section of a fat doc by slug, sourced from the INDEX sidecar."""
    if not source.exists() or not source.is_file():
        return None
    index_file = _index_path_for(source)
    rows = _parse_section_index(index_file)
    if not rows:
        return None
    row = _match_section(rows, slug=slug, section=section)
    if row is None:
        return None
    payload: dict[str, Any] = {
        "path": str(source),
        "index_path": str(index_file),
        "slug": row["slug"],
        "title": row["title"],
        "start": row["start"],
        "end": row["end"],
        "lines": row["lines"],
        "token_estimate": row["tokens"],
    }
    if with_body:
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            payload["body"] = ""
            return payload
        all_lines = text.splitlines()
        start_idx = max(0, row["start"] - 1)
        end_idx = min(len(all_lines), row["end"])
        payload["body"] = "\n".join(all_lines[start_idx:end_idx])
    return payload
