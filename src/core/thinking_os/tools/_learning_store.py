"""Leaf: how a learned pattern is identified, written, and tiered.

Every producer — extraction, friction mining, narratives — funnels through
`_upsert_pattern` here, so dedup identity and provenance have one definition and
no producer imports another producer.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger("thinking_os.learning")


def _derive_project_root(conn: sqlite3.Connection) -> Path | None:
    # Root = parent of the .coding-os/ dir holding the DB. None for in-memory
    # DBs or any DB outside the expected <root>/.coding-os/coding-os.db layout.
    rows = conn.execute("PRAGMA database_list").fetchall()
    for row in rows:
        db_path_str = row[2] if len(row) > 2 else None
        if not db_path_str:
            continue
        if db_path_str in ("", ":memory:"):
            continue
        db_path = Path(db_path_str).resolve()
        if db_path.parent.name == ".coding-os":
            return db_path.parent.parent
    return None


_SOURCE_TO_PROVENANCE: dict[str, str] = {
    "learn_extract": "extracted_from_outcome",
    "friction": "extracted_from_observation",
    "commit": "extracted_from_commit",
    "breakthrough": "agent_self",
    "manual": "user_directive",
    "import": "imported",
}


# Volatile counters embedded in mined pattern text — the running task
# count grows every extraction run, so it must NOT be part of a pattern's
# identity or each run mints a new snapshot row instead of updating one.
_IDENTITY_COUNT_RE = re.compile(r"\(\d+(?:/\d+)?\s*(?:tasks?|occurrences?)[^)]*\)", re.IGNORECASE)
_IDENTITY_RATIO_RE = re.compile(r"\(\d+/\d+\)")
_IDENTITY_PCT_RE = re.compile(r"\d+(?:\.\d+)?%")


def _pattern_identity(text: str) -> str:
    # Count-agnostic dedup key: strip the running counts / percentages so a
    # re-mined fact ("INFRA succeeds … (40/40)" → "(83/83)") maps to the
    # SAME row. The displayed `pattern` keeps the live numbers; only the
    # identity ignores them.
    t = _IDENTITY_COUNT_RE.sub("", text)
    t = _IDENTITY_RATIO_RE.sub("", t)
    t = _IDENTITY_PCT_RE.sub("", t)
    return " ".join(t.split()).lower()


def _upsert_pattern(
    conn: sqlite3.Connection,
    *,
    pattern: str,
    memory_type: str,
    domain: str | None,
    source: str,
    confidence: float,
    concepts: str,
    provenance: str | None = None,
    distill_fingerprint: str | None = None,
    evidence_json: str | None = None,
) -> dict:
    # Sanitizer runs before any DB write; a rejected pattern returns
    # {"action": "rejected", ...} with no row touched. provenance keeps
    # agent_self writes distinguishable from mined data for sycophancy analysis.
    if provenance is None:
        provenance = _SOURCE_TO_PROVENANCE.get(source, "agent_self")
    from sanitizer import sanitize_write

    p_sr = sanitize_write(
        "pattern",
        pattern,
        actor="learning._upsert_pattern",
        source_table="learned_patterns",
        conn=conn,
    )
    if not p_sr.ok:
        return {
            "id": None,
            "pattern": (pattern or "")[:60],
            "confidence": 0.0,
            "action": "rejected",
            "reason": p_sr.reason,
        }
    pattern = p_sr.cleaned

    # Match on a count-agnostic identity, not exact text: a re-mined fact
    # whose running count grew ("(40/40)" → "(83/83)") is the SAME pattern
    # and must update its row, not insert a snapshot. The table is small, so
    # canonicalise candidate rows in the same domain.
    identity = _pattern_identity(pattern)
    existing = None
    if distill_fingerprint:
        try:
            existing = conn.execute(
                "SELECT id, pattern, confidence, times_validated FROM learned_patterns "
                "WHERE distill_fingerprint = ?",
                (distill_fingerprint,),
            ).fetchone()
        except sqlite3.OperationalError:
            existing = None
    if existing is None:
        for cand in conn.execute(
            "SELECT id, pattern, confidence, times_validated FROM learned_patterns WHERE domain IS ?",
            (domain,),
        ):
            if _pattern_identity(cand["pattern"]) == identity:
                existing = cand
                break

    if existing:
        # Confidence is owned by validation (LTP/LTD), not re-extraction: a
        # re-mine bumps times_seen (the occurrence count) and refreshes the text,
        # but must NOT raise confidence — otherwise re-mining resurrects a belief
        # that learn_validate penalized, and LTD could never lower a bad pattern.
        # First-insert seeds the prior; validation moves it from there.
        new_conf = existing["confidence"]
        # Re-extraction is a positive signal: refresh recency AND revive a row a
        # prior decay run archived. A REAL promotion (promoted_to='rule:…' /
        # 'feedback:…') survives the re-mine — the knowledge now lives in the
        # rule layer, and un-promoting it would put the same fact in two places.
        conn.execute(
            # Refresh memory_type too: a re-mine reclassifies a row whose class
            # changed (e.g. a legacy success baseline minted as 'pattern' becomes
            # 'stat'), so old garbage reclassifies on the next loop run.
            "UPDATE learned_patterns SET pattern = ?, memory_type = ?, confidence = ?, "
            "times_seen = COALESCE(times_seen, 0) + 1, last_validated = CURRENT_TIMESTAMP, "
            "last_accessed_at = CURRENT_TIMESTAMP, "
            "promoted_to = CASE WHEN COALESCE(promoted_to, '') IN ('', 'archived') "
            "  THEN NULL ELSE promoted_to END, "
            "archived_at = CASE WHEN COALESCE(promoted_to, '') IN ('', 'archived') "
            "  THEN NULL ELSE archived_at END, "
            "distill_fingerprint = COALESCE(?, distill_fingerprint), "
            "evidence_json = COALESCE(?, evidence_json) "
            "WHERE id = ?",
            (pattern, memory_type, new_conf, distill_fingerprint, evidence_json, existing["id"]),
        )
        pattern_id = existing["id"]
        result = {"id": pattern_id, "pattern": pattern, "confidence": new_conf, "action": "updated"}
    else:
        # Stamp last_validated/last_accessed_at at creation so a fresh pattern's age is 0.
        # Otherwise run_decay reads _days_since(NULL)→999d and archives it on the FIRST run.
        cursor = conn.execute(
            "INSERT INTO learned_patterns "
            "(pattern, memory_type, domain, source, confidence, concepts, provenance, "
            "distill_fingerprint, evidence_json, last_validated, last_accessed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                pattern,
                memory_type,
                domain,
                source,
                confidence,
                concepts,
                provenance,
                distill_fingerprint,
                evidence_json,
            ),
        )
        pattern_id = cursor.lastrowid
        result = {
            "id": pattern_id,
            "pattern": pattern,
            "confidence": confidence,
            "action": "created",
        }

    # RAG: embed the pattern for semantic search.
    # Suppressed because embeddings are optional enrichment — the upsert
    # itself must succeed even when rag extras / v5 schema are unavailable.
    _embed_pattern_safe(conn, pattern_id, pattern, concepts)

    return result


def _embed_pattern_safe(
    conn: sqlite3.Connection,
    pattern_id: int,
    pattern: str,
    concepts: str,
) -> None:
    # Fire-and-forget: embeddings are optional enrichment — never fail the upsert.
    try:
        from embeddings import upsert_embedding
    except ImportError as exc:
        logger.debug("Skipping pattern embedding (module unavailable): %s", exc)
        return
    try:
        text_to_embed = " ".join(filter(None, [pattern, concepts]))
        upsert_embedding(conn, "learned_patterns", pattern_id, text_to_embed)
    except sqlite3.OperationalError as exc:
        logger.debug("Skipping pattern embedding (table missing): %s", exc)
    except Exception as exc:  # pragma: no cover
        logger.debug("Skipping pattern embedding (unexpected): %s", exc)


def _distill_fingerprint_safe(kind: str, cluster_key: str) -> str:
    try:
        import distill

        return distill.cluster_fingerprint(kind, cluster_key)
    except Exception as exc:
        logger.debug("fingerprint skipped: %s", exc)
        return ""


def pattern_tier(confidence: float, times_validated: int) -> str:
    """Confidence tier for a learned pattern — the single mapping used by the UI
    and digest. SSOT: learning-extraction.md § Confidence tier mapping.

    Trusted = confirmed repeatedly · Fading = decaying, up for re-validation ·
    Forming = seen, not yet confirmed.
    """
    conf = confidence or 0.0
    tv = times_validated or 0
    if conf >= 0.7 and tv >= 3:
        return "Trusted"
    if 0.2 <= conf <= 0.4 and tv >= 1:
        return "Fading"
    return "Forming"


def _distill_safe(**kwargs) -> dict | None:
    # Fire-and-forget: the distiller is optional enrichment — any failure
    # (module missing, dispatcher down, headless without auth) falls back to
    # the template producer.
    try:
        import distill

        if not distill.enabled():
            return None
        return distill.distill_cluster(**kwargs)
    except Exception as exc:
        logger.debug("distillation skipped: %s", exc)
        return None


def _adopt_legacy_template(conn: sqlite3.Connection, template_text: str, new_id: int) -> None:
    # A distilled lesson supersedes the template row for the same cluster:
    # fold the old counters in, then invalidate (archive), never delete.
    identity = _pattern_identity(template_text)
    for cand in conn.execute(
        "SELECT id, pattern, times_seen, times_validated, access_count FROM learned_patterns "
        "WHERE domain IS NULL AND COALESCE(promoted_to, '') != 'archived'",
    ):
        if cand["id"] == new_id or _pattern_identity(cand["pattern"]) != identity:
            continue
        conn.execute(
            "UPDATE learned_patterns SET times_seen = COALESCE(times_seen, 0) + ?, "
            "times_validated = times_validated + ?, access_count = access_count + ? "
            "WHERE id = ?",
            (
                cand["times_seen"] or 0,
                cand["times_validated"] or 0,
                cand["access_count"] or 0,
                new_id,
            ),
        )
        conn.execute(
            "UPDATE learned_patterns SET promoted_to = 'archived', "
            "archived_at = CURRENT_TIMESTAMP WHERE id = ?",
            (cand["id"],),
        )
        break
