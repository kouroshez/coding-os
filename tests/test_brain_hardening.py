"""Regression coverage for the R1-R22 brain pipeline hardening.

Scope (each test maps to the risk register in docs/engineering/brain-hardening.md):
  - R1:  MultiEdit is captured like Edit.
  - R2:  cos_observation_record MCP tool exists and writes a row.
  - R3:  cos-env.sh resolves COS_AGENT_MODEL from env + .model file.
  - R4:  brain-decay CLI command is registered.
  - R7:  session_summary fills duration_minutes from canonical session ids.
  - R9/R10:  gc_memory removes orphan embeddings and trash concept edges.
  - R11: retrieve._normalize_task_id extracts TASK-NNN from composite markers.
  - R14: impact.calculate_impact boosts core/ kernel paths.
  - R17: session-context.sh rewrites .agent marker on Claude startup.
  - R22: cos_learn_suggest persists .learn-suggestions for the validate reminder.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BRAIN = REPO / "src" / "core" / "thinking_os"
HOOKS = REPO / "src" / "core" / "hooks"


def _seed_db(tmp: Path) -> Path:
    """Initialise a fresh schema-v18 DB for isolation."""
    sys.path.insert(0, str(BRAIN))
    import database as _db  # type: ignore

    path = tmp / "coding-os.db"
    conn = _db.init_db(str(path))
    conn.close()
    return path


# --------------------------------------------------------------------------
# R1 — MultiEdit capture
# --------------------------------------------------------------------------


def test_capture_accepts_multiedit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sys.path.insert(0, str(BRAIN))
    from capture import CAPTURE_TOOLS, capture_observation  # type: ignore

    assert "MultiEdit" in CAPTURE_TOOLS, "MultiEdit must be in CAPTURE_TOOLS"
    db = _seed_db(tmp_path)
    agent_dir = tmp_path / "claude"
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("COS_AGENT", "claude")
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "session-id").write_text("ses-claude-20260424-120000-abcd")
    result = capture_observation(
        {"tool_name": "MultiEdit", "tool_input": {"file_path": "backend/apps/foo/models.py"}},
        db_path=db,
    )
    assert result["status"] == "captured", result


# --------------------------------------------------------------------------
# R2 — cos_observation_record MCP tool
# --------------------------------------------------------------------------


def test_server_exports_observation_record_tool() -> None:
    # Asserted against the live registration, not server.py's source text: the
    # tool bodies moved into the _tools_* siblings when server.py was split, and
    # a grep-the-file test would have passed for the wrong reason (or failed for
    # a purely cosmetic one).
    sys.path.insert(0, str(BRAIN))
    import server  # type: ignore

    assert callable(server.cos_observation_record)
    registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    assert "cos_observation_record" in registered


# --------------------------------------------------------------------------
# R3 — cos-env.sh model resolution
# --------------------------------------------------------------------------


def test_cos_env_exports_model_from_file(tmp_path: Path) -> None:
    (tmp_path / "claude").mkdir()
    (tmp_path / "claude" / ".model").write_text("claude-opus-4-7")
    proc = subprocess.run(
        ["bash", "-c", f"source {HOOKS / 'cos-env.sh'}; echo ${{COS_AGENT_MODEL:-missing}}"],
        env={
            **os.environ,
            "COS_STATE_DIR": str(tmp_path),
            "COS_AGENT": "claude",
            "COS_AGENT_DIR": str(tmp_path / "claude"),
            "COS_AGENT_MODEL": "",
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert "claude-opus-4-7" in proc.stdout, proc.stdout + "\n" + proc.stderr


# --------------------------------------------------------------------------
# R4 — brain-decay + brain-gc CLI
# --------------------------------------------------------------------------


def test_brain_decay_cli_registered() -> None:
    src = (REPO / "src" / "cli" / "main.py").read_text()
    assert "brain_decay_cmd" in src
    assert "brain_gc_cmd" in src
    assert "brain_sweep_changelog_cmd" in src


def test_brain_commands_module_has_decay_and_gc() -> None:
    src = (REPO / "src" / "cli" / "brain_commands.py").read_text()
    assert "def brain_decay(" in src
    assert "def brain_gc(" in src
    assert "def brain_sweep_changelog(" in src


def test_sweep_changelog_dry_run_confirm_undo(tmp_path: Path) -> None:
    sys.path.insert(0, str(BRAIN))
    import memory_gc  # type: ignore

    db = _seed_db(tmp_path)
    conn = sqlite3.connect(str(db))
    rows = [
        (1, "edit", "changelog", "-40 days"),  # legacy → swept
        (2, "write", "changelog", "-40 days"),  # legacy → swept
        (3, "edit", "changelog", "-1 days"),  # within grace → protected
        (4, "tool_failure", "changelog", "-40 days"),  # mining fuel → protected
    ]
    for oid, otype, mtype, age in rows:
        conn.execute(
            "INSERT INTO observations (id, session_id, observation_type, memory_type, title, created_at) "
            "VALUES (?, 's', ?, ?, 'row', datetime('now', ?))",
            (oid, otype, mtype, age),
        )
    conn.commit()
    conn.close()

    dry = memory_gc.sweep_changelog(str(db), dry_run=True, grace_days=14)
    assert dry["matched"] == 2 and dry["deleted"] == 0  # reports only, no write

    done = memory_gc.sweep_changelog(
        str(db), dry_run=False, grace_days=14, archive_dir=tmp_path / "arch"
    )
    assert done["deleted"] == 2 and Path(done["archive_path"]).exists()
    conn = sqlite3.connect(str(db))
    survivors = {r[0] for r in conn.execute("SELECT id FROM observations")}
    conn.close()
    assert survivors == {3, 4}  # recent + tool_failure survive

    undone = memory_gc.undo_sweep(str(db), done["archive_path"])
    assert undone["restored"] == 2
    conn = sqlite3.connect(str(db))
    restored = {r[0] for r in conn.execute("SELECT id FROM observations")}
    conn.close()
    assert restored == {1, 2, 3, 4}  # byte-for-byte restore


# --------------------------------------------------------------------------
# R7 — duration_minutes
# --------------------------------------------------------------------------


def test_duration_minutes_from_canonical_session_id(tmp_path: Path) -> None:
    sys.path.insert(0, str(BRAIN))
    from session_summary import _compute_session_duration  # type: ignore

    db = _seed_db(tmp_path)
    conn = sqlite3.connect(str(db))
    # Stamp matches 2026-04-24 12:00:00 UTC — always in the past for tests.
    minutes = _compute_session_duration(conn, "ses-claude-20260424-120000-abcd")
    conn.close()
    assert minutes is not None and minutes >= 0


def test_duration_minutes_none_for_legacy_id(tmp_path: Path) -> None:
    sys.path.insert(0, str(BRAIN))
    from session_summary import _compute_session_duration  # type: ignore

    db = _seed_db(tmp_path)
    conn = sqlite3.connect(str(db))
    # Pre-canonical id + no observations in session → None.
    out = _compute_session_duration(conn, "legacy-no-timestamp")
    conn.close()
    assert out is None


# --------------------------------------------------------------------------
# R9 / R10 — gc_memory
# --------------------------------------------------------------------------


def test_gc_memory_removes_orphans_and_trash(tmp_path: Path) -> None:
    sys.path.insert(0, str(BRAIN))
    from memory_gc import gc_memory  # type: ignore

    db = _seed_db(tmp_path)
    conn = sqlite3.connect(str(db))
    # Seed: one real observation, one trash observation, one orphan embedding,
    # one trash concept_graph edge.
    conn.execute(
        "INSERT INTO observations (session_id, tool_name, title, narrative, "
        "files_modified, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
        ("ses-test", "Edit", "Real", "Real work", "backend/models.py", "aa"),
    )
    conn.execute(
        "INSERT INTO observations (session_id, tool_name, title, narrative, "
        "files_modified, content_hash) VALUES (?, ?, ?, ?, ?, ?)",
        ("ses-test", "Edit", "Trash", "Temp", "/tmp/trash.py", "bb"),
    )
    conn.execute(
        "INSERT INTO embeddings (source_table, source_id, text_hash, embedding) "
        "VALUES ('observations', 999, 'orphan', x'00')",
    )
    conn.execute(
        "INSERT INTO concept_graph (source, target, edge_type) "
        "VALUES ('/tmp/a.py', '/tmp/b.py', 'co_edit')",
    )
    conn.commit()
    conn.close()

    stats = gc_memory(db_path=db)
    assert stats["orphan_embeddings_observations"] == 1
    assert stats["orphan_concept_graph_edges"] == 1
    assert stats["trash_observations"] == 1

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM concept_graph").fetchone()[0] == 0
        assert (
            conn.execute("SELECT COUNT(*) FROM embeddings WHERE source_id=999").fetchone()[0] == 0
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------
# R11 — retrieve._normalize_task_id
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,want",
    [
        ("ses-claude-20260424-abc TASK-058-brain-hardening", "TASK-058"),
        ("ses-codex-20260424-abc exploratory-foo", "exploratory-foo"),
        ("TASK-019", "TASK-019"),
        ("plain-slug", "plain-slug"),
        ("", ""),
    ],
)
def test_normalize_task_id(raw: str, want: str) -> None:
    sys.path.insert(0, str(BRAIN))
    from tools.retrieve import _normalize_task_id  # type: ignore

    assert _normalize_task_id(raw) == want


# --------------------------------------------------------------------------
# R14 — impact heuristic
# --------------------------------------------------------------------------


def test_impact_boosts_core_kernel_paths() -> None:
    sys.path.insert(0, str(BRAIN))
    from impact import calculate_impact  # type: ignore

    low = calculate_impact(file_path="docs/notes.md")
    high = calculate_impact(file_path="src/core/thinking_os/server.py")
    assert high > low, (high, low)


def test_impact_penalises_test_and_cache_paths() -> None:
    sys.path.insert(0, str(BRAIN))
    from impact import calculate_impact  # type: ignore

    baseline = calculate_impact(file_path="backend/core/views.py")
    cached = calculate_impact(file_path="backend/core/__pycache__/views.cpython.pyc")
    assert cached < baseline


# --------------------------------------------------------------------------
# R17 — .agent marker refresh on session-context.sh
# --------------------------------------------------------------------------


def test_session_context_refreshes_agent_marker(tmp_path: Path) -> None:
    (tmp_path / ".agent").write_text("codex")
    (tmp_path / "claude").mkdir()
    env = {
        **os.environ,
        "COS_STATE_DIR": str(tmp_path),
        "COS_AGENT": "claude",
        "COS_AGENT_DIR": str(tmp_path / "claude"),
        "CLAUDECODE": "1",
        "COS_DB_PATH": str(tmp_path / "no-such.db"),
    }
    subprocess.run(
        ["bash", str(HOOKS / "session-context.sh")],
        input=json.dumps({"source": "startup", "model": "claude-opus-4-7"}),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (tmp_path / ".agent").read_text() == "claude"


# --------------------------------------------------------------------------
# R22 — learn_suggest persists .learn-suggestions
# --------------------------------------------------------------------------


def test_persist_learn_suggestions_writes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sys.path.insert(0, str(BRAIN))
    agent_dir = tmp_path / "claude"
    agent_dir.mkdir()
    monkeypatch.setenv("COS_AGENT_DIR", str(agent_dir))
    import server  # type: ignore

    server._persist_learn_suggestions_safe(
        {
            "suggestions": [
                {"id": 1, "pattern": "always run migrations before deploy"},
                {"id": 7, "pattern": "prefer services over serializers for\tbiz logic"},
            ],
        }
    )
    target = agent_dir / ".learn-suggestions"
    assert target.exists()
    lines = target.read_text().strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("1\t")
    # Tab in source should be scrubbed so the hook's id<TAB>text split stays clean.
    assert lines[1].count("\t") == 1
