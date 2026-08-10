"""Breakthrough narratives: mint the lesson, embed it, file the insight doc.

Separate from pattern mining because a narrative changes for authoring reasons
(what a good insight reads like, where the file lands) while mining changes for
signal reasons (which logs we scan). Neither should force the other to move.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("thinking_os.learning")

# tools/ is imported BOTH flat (`from tools.learning import …` — hooks, the MCP
# server) and as a package member (`thinking_os.tools.learning` — the Hub, CLI).
# A relative import breaks the first, a bare one the second, so try both.
try:  # package import
    from ._learning_store import _derive_project_root
except ImportError:  # flat import
    from _learning_store import _derive_project_root


# Breakthrough narrative capture
# ---------------------------------------------------------------------------


_GENERIC_INSIGHT_RE = re.compile(
    r"\b(be careful|be more careful|double[- ]check|pay attention|take care|"
    r"more thorough|review carefully|test more|don'?t forget)\b",
    re.IGNORECASE,
)


def _is_low_quality_insight(text: str) -> bool:
    # Reject ultra-terse / generic "be careful" slop with no transferable rule;
    # specific-but-short insights like "Money must use Decimal" still pass.
    t = (text or "").strip()
    if len(t) < 8:
        return True
    return bool(_GENERIC_INSIGHT_RE.search(t))


def learn_narrative(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    what_failed: str = "",
    what_worked: str = "",
    key_insight: str = "",
) -> dict:
    """Record a breakthrough narrative and create a high-impact learned pattern.

    Called by the agent after a rework→success breakthrough. Updates the
    outcome_history narrative fields and creates a learned_pattern with
    memory_type='error' and high confidence.

    Args:
        conn: SQLite connection.
        task_id: Task identifier (e.g. "TASK-100").
        what_failed: Approaches that didn't work.
        what_worked: The solution that resolved the issue.
        key_insight: Reusable lesson learned.

    Returns:
        Dict with status, history_id, pattern_id.
    """
    if not task_id:
        return {"error": "task_id is required"}
    if not key_insight:
        return {"error": "key_insight is required — what did you learn?"}

    # sanitize all narrative fields before they enter memory.
    # Reject on injection patterns; truncate over-length text.
    # Single-pass: compute cleaned values once so audit log records each
    # truncation/reject exactly once.
    from sanitizer import sanitize_write

    _sanitized: dict[str, str] = {}
    for _field, _value in (
        ("key_insight", key_insight),
        ("what_failed", what_failed),
        ("what_worked", what_worked),
    ):
        _sr = sanitize_write(
            _field,
            _value,
            actor="learn_narrative",
            source_table="outcome_history",
            conn=conn,
        )
        if not _sr.ok:
            return {"error": f"rejected {_field}: {_sr.reason}"}
        _sanitized[_field] = _sr.cleaned or ""

    key_insight = _sanitized["key_insight"]
    what_failed = _sanitized["what_failed"]
    what_worked = _sanitized["what_worked"]

    # Quality bar: a narrative is only worth storing if the insight is specific.
    # Blocks "be careful"-class slop the nudge could otherwise elicit.
    if _is_low_quality_insight(key_insight):
        return {
            "error": "key_insight too generic — state the specific situation, why the "
            "naive approach failed, and the rule to apply (not 'be careful')."
        }

    # Find the most recent breakthrough for this task
    row = conn.execute(
        "SELECT id, outcome, previous_outcome FROM outcome_history "
        "WHERE task_id = ? AND is_breakthrough = 1 "
        "ORDER BY created_at DESC LIMIT 1",
        (task_id,),
    ).fetchone()

    if row is None:
        # No breakthrough found — create a general narrative entry anyway
        cursor = conn.execute(
            "INSERT INTO outcome_history "
            "(task_id, outcome, previous_outcome, is_breakthrough, "
            "narrative_what_failed, narrative_what_worked, narrative_key_insight, triggered_by) "
            "VALUES (?, 'success', NULL, 0, ?, ?, ?, 'learn_narrative')",
            (task_id, what_failed, what_worked, key_insight),
        )
        history_id = cursor.lastrowid
    else:
        history_id = row["id"]
        conn.execute(
            "UPDATE outcome_history SET "
            "narrative_what_failed = ?, narrative_what_worked = ?, narrative_key_insight = ? "
            "WHERE id = ?",
            (what_failed, what_worked, key_insight, history_id),
        )

    # Get task domain for the pattern; a still-open task has no outcome row
    # yet, so fall back to the board's tasks table before giving up.
    task_row = conn.execute(
        "SELECT domain, complexity FROM task_outcomes WHERE task_id = ?", (task_id,)
    ).fetchone()
    domain = task_row["domain"] if task_row else None
    if not domain:
        try:
            board_row = conn.execute(
                "SELECT domain FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            domain = board_row[0] if board_row and board_row[0] else None
        except sqlite3.Error as exc:
            logger.debug("narrative domain fallback lookup failed: %s", exc)

    # Build concepts from narrative text
    words = set()
    for text in (what_failed, what_worked, key_insight):
        words.update(w.lower() for w in text.split() if len(w) > 3)
    # Keep only meaningful concept words (no stop words)
    stop = {"that", "this", "with", "from", "have", "been", "were", "will", "didn't", "wasn't"}
    concept_list = sorted(words - stop)[:7]
    if domain:
        concept_list.insert(0, domain.lower())

    # Create a high-impact learned pattern
    pattern_text = f"[Breakthrough] {key_insight}"
    if what_failed:
        pattern_text += f" (failed: {what_failed[:80]})"

    # evidence-based auto-promote.
    # Previously this inserted with confidence=0.7 / impact=0.85 /
    # no provenance, letting the agent self-certify a "breakthrough"
    # at high trust after a single call (audit finding A7). Now the
    # row is explicitly volatile/agent_self at moderate confidence;
    # promotion to `validated` requires external evidence (outcome
    # history or explicit `cos_promote`), handled elsewhere.
    # Stamp last_validated/last_accessed_at so a fresh breakthrough has age 0.
    # Otherwise run_decay reads _days_since(NULL)->999d and archives it on the
    # FIRST run (the same fix learn_extract's _upsert_pattern already carries).
    cursor = conn.execute(
        "INSERT INTO learned_patterns "
        "(pattern, memory_type, domain, source, confidence, impact_score, "
        "concepts, trust_tier, provenance, last_validated, last_accessed_at) "
        "VALUES (?, 'error', ?, 'breakthrough', 0.3, 0.5, ?, "
        "'volatile', 'agent_self', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (pattern_text, domain, json.dumps(concept_list)),
    )
    pattern_id = cursor.lastrowid

    conn.commit()

    # RAG: embed both the breakthrough narrative (outcome_history)
    # and the high-impact learned pattern. Errors are intentionally suppressed
    # because embeddings are an optional enrichment — never fail the narrative
    # recording itself if rag extras are not installed or v5 not yet applied.
    _embed_narrative_and_pattern(
        conn=conn,
        history_id=history_id,
        pattern_id=pattern_id,
        pattern_text=pattern_text,
        concept_list=concept_list,
        key_insight=key_insight,
        what_failed=what_failed,
        what_worked=what_worked,
    )

    # Filing-back: write a human-readable markdown file to docs/insights/.
    # Fire-and-forget — filing failure must never break narrative recording.
    filed_path = _file_back_narrative_safe(
        conn=conn,
        task_id=task_id,
        domain=domain,
        key_insight=key_insight,
        what_failed=what_failed,
        what_worked=what_worked,
        history_id=history_id,
        pattern_id=pattern_id,
    )

    return {
        "status": "narrative_recorded",
        "history_id": history_id,
        "pattern_id": pattern_id,
        "task_id": task_id,
        "domain": domain,
        "filed_path": str(filed_path) if filed_path else None,
    }


def _embed_narrative_and_pattern(
    *,
    conn: sqlite3.Connection,
    history_id: int,
    pattern_id: int,
    pattern_text: str,
    concept_list: list,
    key_insight: str,
    what_failed: str,
    what_worked: str,
) -> None:
    # Fire-and-forget: embeddings are optional enrichment — never fail the
    # narrative recording (missing module/table/model load all swallowed).
    try:
        from embeddings import upsert_embedding
    except ImportError as exc:
        logger.debug("Skipping embedding (module unavailable): %s", exc)
        return

    try:
        narrative_text = " ".join(filter(None, [key_insight, what_failed, what_worked]))
        upsert_embedding(conn, "outcome_history", history_id, narrative_text)
        pattern_concepts_str = " ".join(concept_list)
        upsert_embedding(
            conn,
            "learned_patterns",
            pattern_id,
            f"{pattern_text} {pattern_concepts_str}".strip(),
        )
    except sqlite3.OperationalError as exc:
        logger.debug("Skipping embedding (table missing — pre-v5 DB): %s", exc)
    except Exception as exc:  # pragma: no cover - defensive against model load errors
        logger.debug("Skipping embedding (unexpected): %s", exc)


# ---------------------------------------------------------------------------
# Breakthrough narrative filing-back (human-readable markdown artifact)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 50) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    if not slug:
        return "untitled"
    return slug[:max_len].rstrip("-") or "untitled"


def _format_narrative_markdown(
    *,
    task_id: str,
    domain: str | None,
    key_insight: str,
    what_failed: str,
    what_worked: str,
    history_id: int,
    pattern_id: int,
    task_file_name: str | None = None,
) -> str:
    date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # The docs-lint hard gate requires `domain:[A-Z_]+` in the header; XXX is
    # the canonical unknown-placeholder in its enum ("n/a" fails the regex).
    # The body's **Domain:** line stays human-readable.
    domain_header = (domain or "").strip().upper().replace("-", "_")
    if not re.fullmatch(r"[A-Z_]+", domain_header):
        domain_header = "XXX"
    domain_line = domain or "n/a"
    failed_block = what_failed.strip() or "_(not recorded)_"
    worked_block = what_worked.strip() or "_(not recorded)_"
    # Task files are slugged (TASK-NNN-<slug>.md) — a guessed TASK-NNN.md link
    # is always dead and trips the docs-lint hard gate; plain text when unknown.
    source_line = (
        f"**Source task:** [{task_id}](../tasks/{task_file_name})\n\n"
        if task_file_name
        else f"**Source task:** {task_id}\n\n"
    )
    return (
        f"<!-- domain:{domain_header} | layer:reference | ssot:false | "
        f"source:outcome_history#{history_id} | updated:{date_iso} -->\n"
        f"# {task_id}: {key_insight}\n\n"
        f"**Date:** {date_iso}  \n"
        f"**Domain:** {domain_line}  \n"
        f"{source_line}"
        f"## Key Insight\n\n{key_insight}\n\n"
        f"## What Failed\n\n{failed_block}\n\n"
        f"## What Worked\n\n{worked_block}\n\n"
        f"## Links\n\n"
        f"- Pattern: `learned_patterns#{pattern_id}` — retrievable via `cos_details`\n"
        f"- History: `outcome_history#{history_id}`\n"
    )


def _file_back_narrative_safe(
    *,
    conn: sqlite3.Connection,
    task_id: str,
    domain: str | None,
    key_insight: str,
    what_failed: str,
    what_worked: str,
    history_id: int,
    pattern_id: int,
) -> Path | None:
    # Fire-and-forget write to <root>/docs/insights/; returns None (skipped)
    # for in-memory DBs or when <root>/docs/ is absent. Never breaks recording.
    try:
        project_root = _derive_project_root(conn)
        if project_root is None:
            logger.debug("Skipping narrative filing (project root not derivable)")
            return None
        docs_root = project_root / "docs"
        if not docs_root.exists():
            logger.debug("Skipping narrative filing (no docs/ at %s)", project_root)
            return None

        target_dir = docs_root / "insights"
        target_dir.mkdir(parents=True, exist_ok=True)

        slug = _slugify(f"{task_id}-{key_insight}")
        target_path = target_dir / f"{slug}.md"
        task_file_name: str | None = None
        try:
            row = conn.execute(
                "SELECT file_path FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row and row[0] and (project_root / str(row[0])).exists():
                task_file_name = Path(str(row[0])).name
        except sqlite3.Error as exc:
            logger.debug("narrative task-file lookup failed: %s", exc)
        content = _format_narrative_markdown(
            task_id=task_id,
            domain=domain,
            key_insight=key_insight,
            what_failed=what_failed,
            what_worked=what_worked,
            history_id=history_id,
            pattern_id=pattern_id,
            task_file_name=task_file_name,
        )
        target_path.write_text(content, encoding="utf-8")
        return target_path
    except OSError as exc:
        logger.debug("Skipping narrative filing (OS error): %s", exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Skipping narrative filing (unexpected): %s", exc)
        return None
