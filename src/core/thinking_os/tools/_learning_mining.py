"""Mine lessons from friction signals: backtracks, hook blocks, fix commits.

One reason to change: which signals we read and how we turn them into a lesson.
The pattern store this writes into lives in learning.py; the narrative authoring
path lives in _learning_narrative.py.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3

logger = logging.getLogger("thinking_os.learning")

# tools/ is imported BOTH flat (`from tools.learning import …` — hooks, the MCP
# server) and as a package member (`thinking_os.tools.learning` — the Hub, CLI).
# A relative import breaks the first, a bare one the second, so try both.
try:  # package import
    from ._learning_store import (
        _adopt_legacy_template,
        _distill_safe,
        _upsert_pattern,
    )
except ImportError:  # flat import
    from _learning_store import (  # type: ignore[no-redef]
        _adopt_legacy_template,
        _distill_safe,
        _upsert_pattern,
    )


# stat threshold (3) because each failure is individually high-value, and never
# higher than the caller's floor.
_FRICTION_MIN_OCCURRENCES = 2
_LESSON_WINDOW_DAYS = 90

# Plain-language corrective hint per friction kind — kept beginner-readable.
_FRICTION_HINTS: dict[str, str] = {
    "hook_block": "satisfy the blocked rule before retrying the action",
    "schema_mismatch": "match the required output schema exactly before resubmitting",
    "error": "fix the failing precondition before retrying",
}

# Normalisers that turn a volatile failure message into a stable cluster key:
# absolute paths → basename, TASK ids and long hashes → placeholders.
_ABS_PATH_RE = re.compile(r"(?:/[^\s'\":,]+)+/([^\s'\":/,]+)")
_TASKID_RE = re.compile(r"TASK-\d+", re.IGNORECASE)
_LONGHEX_RE = re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE)
_NONWORD_RE = re.compile(r"[^a-z0-9<>_.-]+")


def _friction_kind(title: str, narrative: str, memory_type: str) -> str:
    # Most-specific signal first. hook_block is detected by the capture's
    # memory_type or a leading "BLOCKED" — NOT a loose "blocked" substring,
    # which appears in unrelated remediation text (e.g. "--to blocked").
    title_l = (title or "").lower()
    narr_l = (narrative or "").lower()
    if "does not match required schema" in narr_l or ("schema" in narr_l and "property" in narr_l):
        return "schema_mismatch"
    if memory_type == "hook_block" or narr_l.startswith("blocked") or "[blocked]" in title_l:
        return "hook_block"
    return "error"


def _clean_failure_text(text: str) -> str:
    line = (text or "").strip().split("\n", 1)[0]
    line = _ABS_PATH_RE.sub(r"\1", line)
    line = _TASKID_RE.sub("TASK-N", line)
    line = _LONGHEX_RE.sub("<hash>", line)
    return " ".join(line.split())[:200]


def _failure_cluster_key(display: str) -> str:
    norm = re.sub(r"\d+", "N", display.lower())
    words = [w for w in _NONWORD_RE.split(norm) if w]
    return " ".join(words[:8])


# Substrings that mark an `error` observation as a tool-fumble or expected
# refusal — the agent tripping over its own tooling, never an engineering lesson.
# See learning-extraction.md § Noise filter.
_NOISE_FAILURE_MARKERS: tuple[str, ...] = (
    "eisdir",
    "illegal operation on a directory",
    "file does not exist",
    "no such file or directory",
    "refusing to write through symlink",
    "structuredoutput",  # workflow-internal schema fumble, not a code lesson
    "validation error for cos_",  # agent mis-called an MCP tool schema — fumble
    "validation errors for cos_",
    "exceeds maximum allowed",  # oversized Read/tool payload — operational refusal
    "scrape aborted",  # external scraping engine refusal — environment, not code
    "scraping engines failed",
    "mcp error -",  # raw MCP transport error — infrastructure, not a lesson
)


def _is_noise_failure(display: str) -> bool:
    low = display.lower()
    return any(marker in low for marker in _NOISE_FAILURE_MARKERS)


# Known internal/model jargon → plain language, so a lesson reads for a novice
# (XAI/PAIR: speak the user's language, not the model's). Applied longest-first.
_JARGON_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    (
        "predicates_unsatisfied: no evidencebundle for predicates ['coverage_100']",
        "ended a 'fix everything' task without recording proof every case was handled",
    ),
    ("predicates_unsatisfied", "ended the task without the required proof-of-completion"),
    ("no evidencebundle", "no proof-of-completion was recorded"),
    ("task_not_closed", "left a task open"),
    ("does not match required schema", "the output's shape did not match what was required"),
)


def _is_noise_failure(display: str) -> bool:
    low = display.lower()
    return any(marker in low for marker in _NOISE_FAILURE_MARKERS)


def _humanize_signature(display: str) -> str:
    out = display
    low = out.lower()
    for jargon, plain in _JARGON_TRANSLATIONS:
        idx = low.find(jargon)
        if idx != -1:
            out = out[:idx] + plain + out[idx + len(jargon) :]
            low = out.lower()
    return out


def _normalize_full(text: str) -> str:
    # Lowercase, digits->N, non-word->space — the same rules as the friction
    # cluster key but KEEPING every word, so a failure key stays a contiguous
    # substring of a lesson's full display text.
    return " ".join(_NONWORD_RE.split(re.sub(r"\d+", "N", (text or "").lower())))


def _mint_friction_lesson(
    conn: sqlite3.Connection,
    *,
    kind: str,
    cluster_key: str,
    count: int,
    template_text: str,
    concepts: str,
    hook: str = "",
    rule: str = "",
    samples: list[str] | None = None,
    distill_state: dict | None = None,
) -> dict:
    # One write path for both friction miners: refresh an already-distilled
    # cluster for free, distill a new one under the per-run budget, or fall
    # back to the deterministic template.
    fingerprint = None
    try:
        import distill

        fingerprint = distill.cluster_fingerprint(kind, cluster_key)
    except Exception as exc:
        logger.debug("fingerprint unavailable: %s", exc)

    if fingerprint:
        try:
            row = conn.execute(
                "SELECT id, pattern FROM learned_patterns WHERE distill_fingerprint = ?",
                (fingerprint,),
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row:
            return _upsert_pattern(
                conn,
                pattern=row["pattern"],
                memory_type="lesson",
                domain=None,
                source="friction",
                confidence=0.5,
                concepts=concepts,
                provenance="llm_distilled",
                distill_fingerprint=fingerprint,
            )

    budget_left = bool(distill_state) and distill_state.get("remaining", 0) > 0
    if fingerprint and budget_left:
        distill_state["remaining"] -= 1
        distilled = _distill_safe(
            kind=kind, signature=cluster_key, count=count, hook=hook, rule=rule, samples=samples
        )
        if distilled:
            import distill

            result = _upsert_pattern(
                conn,
                pattern=distill.lesson_text(distilled),
                memory_type="lesson",
                domain=None,
                source="friction",
                confidence=0.5,
                concepts=concepts,
                provenance="llm_distilled",
                distill_fingerprint=fingerprint,
                evidence_json=json.dumps(
                    {"samples": distill.sanitize_samples(samples or []), "recurrences": count}
                ),
            )
            if result.get("id"):
                _adopt_legacy_template(conn, template_text, result["id"])
            return result

    return _upsert_pattern(
        conn,
        pattern=template_text,
        memory_type="lesson",
        domain=None,
        source="friction",
        confidence=min(0.85, 0.4 + count / 10.0),
        concepts=concepts,
    )


def _mine_friction_lessons(
    conn: sqlite3.Connection,
    *,
    min_occurrences: int = 3,
    distill_state: dict | None = None,
) -> list[dict]:
    # Fire-and-forget: a missing observations table/column never breaks extraction.
    floor = max(1, min(min_occurrences, _FRICTION_MIN_OCCURRENCES))
    try:
        rows = conn.execute(
            "SELECT title, narrative, memory_type, files_modified FROM observations "
            "WHERE memory_type IN ('hook_block', 'error') AND COALESCE(narrative, '') != '' "
            "  AND created_at >= datetime('now', '-' || ? || ' days')",
            (_LESSON_WINDOW_DAYS,),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.debug("friction mining skipped: %s", exc)
        return []

    clusters: dict[str, dict] = {}
    for row in rows:
        d = dict(row)
        # Screen title AND narrative: a StructuredOutput fumble carries the marker
        # in the title while the narrative reads like a generic schema error.
        if _is_noise_failure(f"{d['title'] or ''} {d['narrative'] or ''}"):
            continue  # tool-fumble / expected refusal — never a lesson
        display = _clean_failure_text(d["narrative"] or d["title"] or "")
        key = _failure_cluster_key(display)
        if not key:
            continue
        cluster = clusters.setdefault(
            key,
            {
                "count": 0,
                # store the humanized signature so the minted lesson reads plainly
                "display": _humanize_signature(display),
                "kind": _friction_kind(d["title"], d["narrative"], d["memory_type"]),
                "files": set(),  # source-file basenames → concepts, for JIT recall
                "samples": [],
            },
        )
        cluster["count"] += 1
        if len(cluster["samples"]) < 3:
            cluster["samples"].append(display)
        fm = d.get("files_modified") or ""
        if fm:
            cluster["files"].add(fm.rsplit("/", 1)[-1])

    lessons: list[dict] = []
    for key, cluster in clusters.items():
        if cluster["count"] < floor:
            continue
        hint = _FRICTION_HINTS.get(cluster["kind"], _FRICTION_HINTS["error"])
        # Count rendered as "(N occurrences)" so _pattern_identity strips it and
        # a re-mined cluster UPDATES its row instead of inserting a snapshot.
        pattern_text = (
            f"Recurring {cluster['kind'].replace('_', ' ')} "
            f"({cluster['count']} occurrences): {cluster['display']} → {hint}"
        )
        lessons.append(
            _mint_friction_lesson(
                conn,
                kind=cluster["kind"],
                cluster_key=key,
                count=cluster["count"],
                template_text=pattern_text,
                samples=cluster["samples"],
                distill_state=distill_state,
                # file:<basename> tokens key JIT recall on the friction's source
                # file (not basename-in-humanized-text, which never matched).
                concepts=json.dumps(
                    ["lesson", cluster["kind"], "friction"]
                    + [f"file:{b}" for b in sorted(cluster["files"])[:5] if b]
                ),
            )
        )
    return lessons
