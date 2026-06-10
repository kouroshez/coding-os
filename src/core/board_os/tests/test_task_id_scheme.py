"""Task-id allocation schemes (TASK-298).

sequential (default) → TASK-NNN; namespaced → TASK-<NS>-NNN with a per-namespace
counter so un-synced contributors never collide at PR/merge.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from core.board_os import config as cfg_mod
from core.board_os import mcp_tools
from core.board_os import parser as board_parser
from core.thinking_os import database as db


def _write_config(root: Path, **extra) -> None:
    (root / ".coding-os").mkdir(exist_ok=True)
    data = {
        "swimlanes": [{"id": "core", "label": "Core", "color": "#3b82f6"}],
        "wip_limits": {"in_progress": 2, "testing": 3, "emergency": 2},
        **extra,
    }
    (root / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump(data), encoding="utf-8"
    )
    (root / "docs" / "tasks").mkdir(parents=True, exist_ok=True)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "coding-os.db")


def test_sequential_is_the_default(tmp_path, conn):
    _write_config(tmp_path)
    assert mcp_tools._next_task_id(conn, tmp_path) == "TASK-001"


def test_namespaced_uses_explicit_prefix(tmp_path, conn):
    _write_config(tmp_path, task_id_scheme="namespaced", task_id_prefix="KO")
    assert mcp_tools._next_task_id(conn, tmp_path) == "TASK-KO-001"
    # the next one increments within the namespace
    assert mcp_tools._next_task_id(conn, tmp_path) == "TASK-KO-002"


def test_namespaces_are_independent_no_collision(tmp_path, conn):
    # Simulate a sibling contributor's task already in the DB (e.g. pulled).
    conn.execute(
        "INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime) "
        "VALUES ('TASK-JD-280', 'x', 'icebox', 'docs/tasks/TASK-JD-280-x.md', '', 0)"
    )
    conn.commit()
    _write_config(tmp_path, task_id_scheme="namespaced", task_id_prefix="KO")
    # KO's counter is unaffected by JD's 280 → no collision at PR/merge.
    assert mcp_tools._next_task_id(conn, tmp_path) == "TASK-KO-001"


def test_namespaced_ignores_sequential_max(tmp_path, conn):
    conn.execute(
        "INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime) "
        "VALUES ('TASK-300', 'x', 'icebox', 'docs/tasks/TASK-300-x.md', '', 0)"
    )
    conn.commit()
    _write_config(tmp_path, task_id_scheme="namespaced", task_id_prefix="KO")
    assert mcp_tools._next_task_id(conn, tmp_path) == "TASK-KO-001"


def test_config_rejects_bad_prefix(tmp_path):
    with pytest.raises(cfg_mod.ConfigValidationError):
        cfg_mod.parse_config(
            {
                "swimlanes": [{"id": "core", "label": "Core", "color": "#3b82f6"}],
                "task_id_scheme": "namespaced",
                "task_id_prefix": "lowercase",
            }
        )


def test_config_rejects_unknown_scheme(tmp_path):
    with pytest.raises(cfg_mod.ConfigValidationError):
        cfg_mod.parse_config(
            {
                "swimlanes": [{"id": "core", "label": "Core", "color": "#3b82f6"}],
                "task_id_scheme": "magic",
            }
        )


def test_parser_reads_namespaced_h1(tmp_path):
    body = (
        "---\nid: TASK-KO-280\nswimlane: core\nkind: bug\nstatus: icebox\n---\n"
        "# TASK-KO-280: a namespaced task\n\n## Work Log\n"
    )
    parsed = board_parser.parse_task(body)
    assert parsed is not None
    assert parsed.task_id == "TASK-KO-280"


def test_seam_dispatches_local_vs_namespaced(tmp_path):
    _write_config(tmp_path)
    assert isinstance(mcp_tools._resolve_task_id_allocator(tmp_path), mcp_tools._LocalAllocator)
    _write_config(tmp_path, task_id_scheme="namespaced", task_id_prefix="KO")
    assert isinstance(
        mcp_tools._resolve_task_id_allocator(tmp_path), mcp_tools._NamespacedAllocator
    )


def test_seam_registry_is_the_dispatch_point(tmp_path, conn, monkeypatch):
    # A future allocator drops in via the registry with zero caller change.
    _write_config(tmp_path, task_id_scheme="namespaced", task_id_prefix="KO")

    class _StubAllocator:
        def allocate(self, conn, project_root):
            return "TASK-STUB-7"

    monkeypatch.setitem(mcp_tools._TASK_ID_ALLOCATORS, "namespaced", _StubAllocator())
    assert mcp_tools._next_task_id(conn, tmp_path) == "TASK-STUB-7"


def test_derive_ns_is_stable_uppercase(tmp_path, monkeypatch):
    # Deterministic for a fixed email; shape is letter-first uppercase alnum.
    import subprocess

    class _R:
        stdout = "dev@example.com\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    ns = mcp_tools._derive_ns_from_git(tmp_path)
    assert ns[0].isalpha() and ns.isupper() and 2 <= len(ns) <= 8
    assert mcp_tools._derive_ns_from_git(tmp_path) == ns  # stable


# --- external_ref (optional forge issue/PR link) -------------------------------


def test_normalize_external_ref_variants(monkeypatch):
    monkeypatch.setattr(mcp_tools, "_detect_forge", lambda root: "github")
    n = mcp_tools._normalize_external_ref
    root = Path(".")
    assert n("42", root) == "github#42"
    assert n("#42", root) == "github#42"
    assert n("github#42", root) == "github#42"
    assert n("https://github.com/x/y/issues/42", root) == "github#42"
    assert n("https://gitlab.com/x/y/-/merge_requests/17", root) == "gitlab!17"
    assert n("nonsense", root) is None
    assert n("", root) is None


def test_normalize_bare_number_needs_a_forge(monkeypatch):
    monkeypatch.setattr(mcp_tools, "_detect_forge", lambda root: "")
    assert mcp_tools._normalize_external_ref("42", Path(".")) is None
    # but an explicit forge in the ref still resolves with no remote
    assert mcp_tools._normalize_external_ref("gitlab#9", Path(".")) == "gitlab#9"


def _seed_task(conn, tmp_path, task_id):
    (tmp_path / "docs" / "tasks").mkdir(parents=True, exist_ok=True)
    rel = f"docs/tasks/{task_id}-x.md"
    (tmp_path / rel).write_text(
        f"---\nid: {task_id}\nstatus: icebox\n---\n# {task_id}: x\n\n## Work Log\n"
    )
    conn.execute(
        "INSERT INTO tasks (task_id,title,status,file_path,content_hash,mtime) "
        "VALUES (?,?,?,?,?,?)",
        (task_id, "x", "icebox", rel, "", 0),
    )
    conn.commit()
    return tmp_path / rel


def test_cos_task_link_sets_external_ref_and_parser_reads_it(tmp_path, conn, monkeypatch):
    from core.board_os import parser as board_parser

    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_tools, "_detect_forge", lambda root: "github")
    md = _seed_task(conn, tmp_path, "TASK-001")
    res = mcp_tools.cos_task_link(conn, task_id="TASK-001", ref="42")
    assert "github#42" in res
    parsed = board_parser.parse_task(md.read_text())
    assert parsed.external_ref == "github#42"


def test_cos_task_link_rejects_unparseable_ref(tmp_path, conn, monkeypatch):
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(mcp_tools, "_detect_forge", lambda root: "github")
    _seed_task(conn, tmp_path, "TASK-002")
    res = mcp_tools.cos_task_link(conn, task_id="TASK-002", ref="not-a-ref").lower()
    assert "validation" in res or '"ok": false' in res


def test_cos_task_link_unknown_task(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    res = mcp_tools.cos_task_link(conn, task_id="TASK-999", ref="github#1").lower()
    assert "not_found" in res
