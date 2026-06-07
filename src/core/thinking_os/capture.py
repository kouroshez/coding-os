#!/usr/bin/env python3
"""
Thinking OS — Observation capture (TASK-151).

Reads tool call JSON from stdin, extracts structured fields,
writes observation to SQLite. Runs as background process (fire-and-forget).

Exits silently if DB absent or input invalid.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from concepts import extract_concepts
from database import DEFAULT_DB_PATH, get_connection
from impact import calculate_impact

# Tools worth capturing (all others are filtered out).  MultiEdit is the
# batched variant emitted by Claude Code / Cursor when an agent edits
# multiple hunks in one turn — filtering it out meant most real agent
# edits produced zero observations.  We treat MultiEdit semantically as
# an Edit (single file_path per invocation; the multi-hunk payload lives
# in tool_input.edits[]).
CAPTURE_TOOLS = {"Write", "Edit", "MultiEdit"}

# Static memory-type rules. Per-agent prefixes (.claude/, .codex/, ...) are
# resolved dynamically from adapter manifests so core/ stays agent-agnostic.
_STATIC_MEMORY_TYPE_MAP = [
    ("backend/", "pattern"),
    ("frontend/", "pattern"),
    ("docs/", "config"),
    (".coding-os/", "config"),
    ("infrastructure/", "workflow"),
    ("tests/", "pattern"),
]

DEFAULT_MEMORY_TYPE = "discovery"


def _detect_memory_type(file_path: str) -> str:
    """Auto-detect memory type from file path."""
    from _agent_markers import agent_state_prefixes

    for prefix, mtype in _STATIC_MEMORY_TYPE_MAP:
        if prefix in file_path:
            return mtype
    for prefix in agent_state_prefixes():
        if prefix in file_path:
            return "config"
    return DEFAULT_MEMORY_TYPE


def _estimate_impact(file_path: str) -> float:
    """Estimate impact score from file path (0.0-1.0)."""
    score = 0.5
    # High-impact file patterns
    high_impact = ["models.py", "schema", "migration", "settings", "auth", "payment", "security"]
    low_impact = ["test_", "README", ".md", "__pycache__"]

    path_lower = file_path.lower()
    for pattern in high_impact:
        if pattern in path_lower:
            score = min(1.0, score + 0.2)
    for pattern in low_impact:
        if pattern in path_lower:
            score = max(0.1, score - 0.1)

    return round(score, 2)


def _build_narrative(tool_name: str, file_path: str) -> str:
    """Build a rule-based narrative from file path (free, instant, no API).

    Examples:
        backend/apps/commerce/models/order.py → "Modified commerce order model"
        frontend/src/app/products/page.tsx   → "Created products page component"
    """
    action = "Modified" if tool_name in ("Edit", "MultiEdit") else "Created"
    parts = Path(file_path).parts
    path_lower = file_path.lower()

    # Detect domain
    domain = ""
    if "backend/" in file_path:
        domain = "backend"
        for i, p in enumerate(parts):
            if p == "apps" and i + 1 < len(parts):
                domain = parts[i + 1]
                break
    elif "frontend/" in file_path:
        domain = "frontend"
        for i, p in enumerate(parts):
            if p in ("app", "components", "lib") and i + 1 < len(parts):
                domain = f"frontend {parts[i + 1]}"
                break
    elif "docs/" in file_path:
        domain = "docs"
    elif ".coding-os/" in file_path or any(
        p in file_path for p in __import__("_agent_markers").agent_state_prefixes()
    ):
        domain = "config"

    # Detect component type
    component = ""
    stem = Path(file_path).stem
    if "/models/" in path_lower or stem == "models":
        component = "model"
    elif "/views/" in path_lower or stem == "views":
        component = "view"
    elif "/serializers/" in path_lower or stem == "serializers":
        component = "serializer"
    elif "/services/" in path_lower:
        component = "service"
    elif "/tests/" in path_lower or stem.startswith("test_"):
        component = "test"
    elif "/migrations/" in path_lower:
        component = "migration"
    elif path_lower.endswith((".tsx", ".jsx")):
        component = "component"
    elif path_lower.endswith(".ts"):
        component = "module"
    elif path_lower.endswith(".md"):
        component = "doc"
    elif path_lower.endswith(".sh"):
        component = "script"

    # Detect impact qualifier
    qualifier = ""
    if any(k in path_lower for k in ("models", "schema", "migration")):
        qualifier = " (schema change)"
    elif any(k in path_lower for k in ("auth", "security", "payment")):
        qualifier = " (security-sensitive)"
    elif any(k in path_lower for k in ("settings", "config")):
        qualifier = " (configuration)"

    parts_str = " ".join(filter(None, [domain, stem, component]))
    return f"{action} {parts_str}{qualifier}" if parts_str else f"{action} {Path(file_path).name}"


def _read_session_id() -> str:
    """Read session ID from the agent-private state dir.

    Resolution order (matches the shell cos-env.sh priority so capture.py
    and hooks agree on which session they belong to):
      1. $COS_AGENT_DIR/session-id            — explicit override (used by
                                                session-context.sh and tests)
      2. $COS_STATE_DIR/<agent>/session-id    — where <agent> comes from
                                                $COS_AGENT or the .agent marker
      3. $COS_STATE_DIR/session-id            — pre-Phase-I flat layout
                                                (only used if still present)
      4. ses-anonymous-<pid>                  — last-resort sentinel; shows
                                                up in the DB as a red flag
                                                that the hook fired without
                                                a session context
    """
    state_dir = Path(os.environ.get("COS_STATE_DIR", ".coding-os"))

    # Priority 1 — explicit COS_AGENT_DIR (shell hook passes this via env).
    agent_dir_env = os.environ.get("COS_AGENT_DIR")
    if agent_dir_env:
        session_file = Path(agent_dir_env) / "session-id"
        if session_file.exists():
            sid = session_file.read_text().strip()
            if sid:
                return sid

    # Priority 2 — agent-private dir derived from $COS_AGENT or the .agent marker.
    agent = os.environ.get("COS_AGENT", "")
    if not agent:
        marker = state_dir / ".agent"
        if marker.exists():
            agent = marker.read_text().strip()
    if agent:
        session_file = state_dir / agent / "session-id"
        if session_file.exists():
            sid = session_file.read_text().strip()
            if sid:
                return sid

    # Priority 3 — pre-refactor flat layout, kept for first-run migration only.
    flat_file = state_dir / "session-id"
    if flat_file.exists():
        sid = flat_file.read_text().strip()
        if sid:
            return sid

    # Priority 4 — anonymous sentinel. Logged so downstream analysis can
    # detect hooks firing without a session context.
    suffix = hashlib.md5(str(os.getpid()).encode()).hexdigest()[:4]
    return f"ses-anonymous-{suffix}"


def _compute_content_hash(tool_name: str, file_path: str) -> str:
    """SHA256 hash of tool_name + file_path for dedup (TASK-153)."""
    content = f"{tool_name}:{file_path}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _estimate_tokens(input_data: dict) -> int:
    """Rough token estimate from input size (4 chars ≈ 1 token)."""
    text = json.dumps(input_data)
    return len(text) // 4


def _display_path(file_path: str, db_path: str | Path) -> str:
    """Repo-relative display path — never leak the absolute project root (and
    thus the local username) into long-lived memory titles.

    In-repo absolute path → relative to the project root (parent of the
    `.coding-os/` dir holding the DB). Absolute path under $HOME but outside
    the repo → `~/…`. Absolute elsewhere → basename. Already-relative → as-is.
    """
    try:
        p = Path(file_path)
        dbp = Path(db_path).resolve()
        if dbp.parent.name == ".coding-os":
            root = dbp.parent.parent
            rp = p.resolve()
            if rp == root or root in rp.parents:
                return str(rp.relative_to(root))
        if p.is_absolute():
            home = Path.home()
            if home in p.parents:
                return "~/" + str(p.relative_to(home))
            return p.name
    except (ValueError, OSError, RuntimeError):
        return Path(file_path).name
    return file_path


def capture_observation(input_data: dict, db_path: str | Path | None = None) -> dict:
    """Process a tool call and write an observation to the DB.

    Args:
        input_data: Parsed JSON from PostToolUse hook stdin.
        db_path: Path to DB. Defaults to DEFAULT_DB_PATH.

    Returns:
        Dict with status.
    """
    path = Path(db_path or DEFAULT_DB_PATH)

    if not path.exists():
        return {"status": "skipped", "reason": "db_absent"}

    tool_name = input_data.get("tool_name", "")
    if tool_name not in CAPTURE_TOOLS:
        return {"status": "filtered", "reason": f"tool '{tool_name}' not in capture list"}

    tool_input = input_data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        return {"status": "skipped", "reason": "no file_path in tool_input"}

    # Generate structured fields. MultiEdit always targets an existing
    # file (single file_path with multiple hunks) so we treat it as an
    # Edit for narrative purposes — the hunk count lives in edits[].
    display_path = _display_path(file_path, path)
    title = (
        f"Modified {display_path}"
        if tool_name in ("Edit", "MultiEdit")
        else f"Created {display_path}"
    )
    narrative = _build_narrative(tool_name, file_path)
    memory_type = _detect_memory_type(file_path)
    impact_score = calculate_impact(file_path=file_path, tool_name=tool_name)
    session_id = _read_session_id()
    cost_tokens = _estimate_tokens(input_data)
    concepts = json.dumps(extract_concepts(file_path=file_path))

    # Content hash dedup: skip duplicate observations within 30s window
    content_hash = _compute_content_hash(tool_name, file_path)

    conn = get_connection(path)
    try:
        # Check for duplicate within 30s window
        existing = conn.execute(
            "SELECT id FROM observations "
            "WHERE content_hash = ? AND created_at >= datetime('now', '-30 seconds')",
            (content_hash,),
        ).fetchone()
        if existing:
            return {"status": "deduped", "existing_id": existing[0]}

        # Sanitize user-visible text before it enters memory.
        # Rejects on injection patterns; truncates over-length. Audit is
        # fire-and-forget via the conn — pre-v7 DBs silently no-op.
        from sanitizer import sanitize_write

        title_sr = sanitize_write(
            "title",
            title,
            actor="capture.py",
            source_table="observations",
            conn=conn,
        )
        if not title_sr.ok:
            return {"status": "rejected", "field": "title", "reason": title_sr.reason}

        narr_sr = sanitize_write(
            "narrative",
            narrative,
            actor="capture.py",
            source_table="observations",
            conn=conn,
        )
        if not narr_sr.ok:
            return {"status": "rejected", "field": "narrative", "reason": narr_sr.reason}

        title = title_sr.cleaned
        narrative = narr_sr.cleaned

        cursor = conn.execute(
            "INSERT INTO observations "
            "(session_id, tool_name, observation_type, memory_type, impact_score, "
            "title, narrative, files_modified, cost_tokens, content_hash, concepts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                tool_name,
                tool_name.lower(),
                memory_type,
                impact_score,
                title,
                narrative,
                file_path,
                cost_tokens,
                content_hash,
                concepts,
            ),
        )
        conn.commit()

        # Record co-edit edges in concept graph (fire-and-forget)
        try:
            from graph import record_co_edit

            record_co_edit(conn, session_id=session_id, file_path=file_path)
        except Exception:
            pass  # graph table may not exist (pre-v4 DB)

        # Embed for semantic search (fire-and-forget). Skipped on
        # the synchronous hook hot-path (COS_CAPTURE_SKIP_EMBED) so the model
        # load never blocks an Edit; the FTS5 trigger already indexes the row
        # on INSERT, so keyword recall works without the embedding.
        if os.environ.get("COS_CAPTURE_SKIP_EMBED", "") not in ("1", "true"):
            try:
                from embeddings import upsert_embedding

                text_to_embed = " ".join(filter(None, [title, narrative, concepts]))
                upsert_embedding(conn, "observations", cursor.lastrowid, text_to_embed)
            except Exception:
                pass  # embeddings module / table may not exist (pre-v5 or no rag extras)

        return {"status": "captured", "id": cursor.lastrowid}
    finally:
        conn.close()


def main() -> None:
    """Read JSON from stdin, capture observation."""
    try:
        raw = sys.stdin.read()
    except (EOFError, OSError, UnicodeDecodeError):
        sys.exit(0)  # benign stdin-acquisition failures — nothing to capture
    if not raw.strip():
        sys.exit(0)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)  # malformed stdin is benign — nothing to capture
    try:
        capture_observation(data)
    except Exception:
        # Surface the failure instead of swallowing it: the PostToolUse hook
        # redirects our stderr to .capture-errors.log so check-capture-worked.sh
        # can report a silent capture death. Still exit 0 — capture is
        # fire-and-forget and must never fail the agent's tool call.
        traceback.print_exc(file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
