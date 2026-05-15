"""E2E tests for enforce-wip-limit.sh consuming scrumban-config.yaml (Wave 1 E4).

Verifies that the shell hook + Python helper + config + DB all integrate
correctly — this is the full path from hook invocation to exit code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Resolve to core/ so board_os imports work.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CORE = _REPO_ROOT / "core"
_HOOK = _CORE / "hooks" / "enforce-wip-limit.sh"

# Skip all tests in this module if the hook doesn't exist (safety guard).
pytestmark = pytest.mark.skipif(
    not _HOOK.exists(),
    reason=f"hook not found: {_HOOK}",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path, in_progress_count: int) -> Path:
    """Create a minimal DB at tmp_path/coding-os.db with N in_progress tasks."""
    db_path = tmp_path / ".coding-os" / "coding-os.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if str(_CORE / "thinking_os") not in sys.path:
        sys.path.insert(0, str(_CORE / "thinking_os"))
    if str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))

    import database as thinking_os_db  # type: ignore

    conn = thinking_os_db.init_db(str(db_path))
    for i in range(in_progress_count):
        conn.execute(
            """
            INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime)
            VALUES (?, ?, 'in_progress', ?, '', 0)
            """,
            (f"TASK-{900 + i:03d}", f"Task {i}", f"/fake/TASK-{900 + i:03d}.md"),
        )
    conn.commit()
    conn.close()
    return db_path


def _make_config(tmp_path: Path, wip_cap: int) -> Path:
    """Write a minimal scrumban-config.yaml with given in_progress WIP cap."""
    cfg_dir = tmp_path / ".coding-os"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = cfg_dir / "scrumban-config.yaml"
    cfg_path.write_text(
        f"swimlanes:\n  - id: general\n    label: General\n"
        f"wip_limits:\n  in_progress: {wip_cap}\n  testing: 10\n  emergency: 2\n"
    )
    return cfg_path


_IN_PROGRESS_CONTENT = (
    "---\ntask_id: TASK-998\ntitle: Test\nstatus: in_progress\n"
    "swimlane: general\nkind: feature\n---\n\nBody.\n"
)


def _task_file(tmp_path: Path) -> Path:
    """Create a minimal task .md file under docs/tasks/ with status: open."""
    td = tmp_path / "docs" / "tasks"
    td.mkdir(parents=True, exist_ok=True)
    p = td / "TASK-998-test.md"
    # File on disk is 'open' so a Write with in_progress content is a real transition.
    p.write_text(
        "---\ntask_id: TASK-998\ntitle: Test\nstatus: open\n"
        "swimlane: general\nkind: feature\n---\n\nBody.\n"
    )
    return p


def _invoke_hook(
    tmp_path: Path,
    task_file: Path,
    *,
    wip_override: bool = False,
) -> subprocess.CompletedProcess:
    """Run enforce-wip-limit.sh with a Write payload transitioning task to in_progress."""
    db_path = tmp_path / ".coding-os" / "coding-os.db"
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(task_file),
            "content": _IN_PROGRESS_CONTENT,
        },
    })
    env = {
        **os.environ,
        "COS_PROJECT_ROOT": str(tmp_path),
        "COS_STATE_DIR": str(tmp_path / ".coding-os"),
        "COS_DB_PATH": str(db_path),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    if wip_override:
        env["COS_WIP_OVERRIDE"] = "1"
    else:
        env.pop("COS_WIP_OVERRIDE", None)
    return subprocess.run(
        ["bash", str(_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_allows_when_under_cap(tmp_path: Path):
    """0 in_progress tasks, cap=2 → hook allows (exit 0)."""
    _make_db(tmp_path, in_progress_count=0)
    _make_config(tmp_path, wip_cap=2)
    task_file = _task_file(tmp_path)
    result = _invoke_hook(tmp_path, task_file)
    assert result.returncode == 0, f"expected 0, got rc={result.returncode}\nstderr={result.stderr}"


def test_allows_at_cap_minus_one(tmp_path: Path):
    """1 in_progress task, cap=2 → still 1 slot available → exit 0."""
    _make_db(tmp_path, in_progress_count=1)
    _make_config(tmp_path, wip_cap=2)
    task_file = _task_file(tmp_path)
    result = _invoke_hook(tmp_path, task_file)
    assert result.returncode == 0, f"stderr: {result.stderr}"


def test_blocks_when_cap_reached(tmp_path: Path):
    """2 in_progress tasks, cap=2 → cap reached → exit 2 (BLOCK)."""
    _make_db(tmp_path, in_progress_count=2)
    _make_config(tmp_path, wip_cap=2)
    task_file = _task_file(tmp_path)
    result = _invoke_hook(tmp_path, task_file)
    assert result.returncode == 2, (
        f"expected exit 2 (block), got rc={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "wip" in result.stderr.lower() or "cap" in result.stderr.lower()


def test_wip_override_bypasses_block(tmp_path: Path):
    """COS_WIP_OVERRIDE=1 bypasses the cap even when exceeded."""
    _make_db(tmp_path, in_progress_count=5)
    _make_config(tmp_path, wip_cap=1)
    task_file = _task_file(tmp_path)
    result = _invoke_hook(tmp_path, task_file, wip_override=True)
    assert result.returncode == 0, f"WIP_OVERRIDE should bypass; stderr={result.stderr}"


def test_non_task_file_passes_through(tmp_path: Path):
    """Hook only acts on docs/tasks/*.md; other files exit 0 immediately."""
    _make_db(tmp_path, in_progress_count=99)
    _make_config(tmp_path, wip_cap=1)
    # Use a non-task file path
    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / "core" / "hooks" / "some_hook.sh"),
            "content": "#!/usr/bin/env bash\nexit 0\n",
        },
    })
    result = subprocess.run(
        ["bash", str(_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env={**os.environ, "COS_PROJECT_ROOT": str(tmp_path)},
        cwd=str(tmp_path),
    )
    assert result.returncode == 0


def test_missing_db_passes_through(tmp_path: Path):
    """If DB is absent, hook fails-soft (exit 0)."""
    _make_config(tmp_path, wip_cap=1)
    task_file = _task_file(tmp_path)
    # Don't call _make_db — DB file won't exist
    result = _invoke_hook(tmp_path, task_file)
    assert result.returncode == 0, f"missing DB should fail-soft; rc={result.returncode}"


def test_missing_config_passes_through(tmp_path: Path):
    """If config is absent, hook fails-soft (exit 0)."""
    _make_db(tmp_path, in_progress_count=5)
    task_file = _task_file(tmp_path)
    # Don't call _make_config — no config file
    result = _invoke_hook(tmp_path, task_file)
    assert result.returncode == 0, f"missing config should fail-soft; rc={result.returncode}"
