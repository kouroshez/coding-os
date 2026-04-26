"""Tests for `cos task-validate TASK-NN` pre-flight mode (Phase L.10 / TASK-109).

The CLI wrapper is thin (dispatches to `validate_transition`) — these
tests exercise the integration: real task file on disk + real DB row
+ validator + verdict reporting.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from core.board_os import mcp_tools
from core.thinking_os import db


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {
                "swimlanes": [{"id": "core", "label": "Core", "color": "#3b82f6"}],
                "wip_limits": {"in_progress": 2, "testing": 3, "emergency": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "thinking_os.db")


def _create_task(
    conn: sqlite3.Connection,
    project: Path,
    *,
    title: str,
    kind: str,
    outcome: str | None = None,
    read_first: list[str] | None = None,
) -> str:
    env = json.loads(
        mcp_tools.cos_task_create(
            conn,
            title=title,
            swimlane="core",
            kind=kind,
            outcome=outcome,
            read_first=read_first,
        )
    )
    return env["data"]["task_id"]


# ────────────────────────────────────────────────────────────────────
# Pre-flight integration via direct call (avoids spinning click runner)
# ────────────────────────────────────────────────────────────────────


def _preflight(task_id: str, *, for_status: str = "in_progress") -> "ValidationResult":  # noqa: F821
    """Mirror what `_task_validate_preflight` does — body+kind from DB,
    config from disk, validator pure."""
    from core.board_os.parser import extract_frontmatter
    from core.board_os.transition_gates import load_gates_config
    from core.board_os.transition_gates_cli import (
        _has_work_log_entries,
        _verify_state,
    )
    from core.board_os.transition_gates_validator import validate_transition

    import sqlite3 as _sql
    conn = _sql.connect(str(Path.cwd() / "thinking_os.db"))
    row = conn.execute(
        "SELECT file_path, kind FROM tasks WHERE task_id = ?", (task_id,),
    ).fetchone()
    conn.close()
    assert row, f"{task_id} not in DB"
    body = (Path.cwd() / row[0]).read_text(encoding="utf-8")
    fm = extract_frontmatter(body) or {}
    kind = str(fm.get("kind") or row[1] or "feature")

    has_recent, age = _verify_state()
    return validate_transition(
        task_id=task_id,
        kind=kind,
        body=body,
        new_status=for_status,
        config=load_gates_config(),
        has_recent_verify=has_recent,
        verify_age_seconds=age,
        has_work_log=_has_work_log_entries(body),
    )


def test_preflight_blocks_default_placeholder_body(
    project: Path, conn: sqlite3.Connection, monkeypatch,
) -> None:
    """Task created with no --outcome → preflight reports BLOCK with
    DOR_OUTCOME_PLACEHOLDER, exact same verdict cos task-start would
    produce."""
    monkeypatch.chdir(project)
    tid = _create_task(conn, project, title="placeholder feature", kind="feature")

    # Need to point the helper at the right DB by chdir — fixture already did.
    # Instead of running the click command, validate directly.
    from core.board_os.parser import extract_frontmatter
    from core.board_os.transition_gates import load_gates_config
    from core.board_os.transition_gates_validator import validate_transition

    body = (project / f"docs/tasks").glob(f"{tid}*.md").__next__().read_text()
    fm = extract_frontmatter(body) or {}
    result = validate_transition(
        task_id=tid,
        kind=str(fm["kind"]),
        body=body,
        new_status="in_progress",
        config=load_gates_config(),
    )
    assert result.blocked
    codes = [m.code for m in result.messages]
    assert any(c.endswith("_PLACEHOLDER") or c.endswith("_MISSING") for c in codes)


def test_preflight_passes_when_outcome_filled_for_chore(
    project: Path, conn: sqlite3.Connection, monkeypatch,
) -> None:
    """Chore kind only needs Outcome ≥15 chars; passes when filled."""
    monkeypatch.chdir(project)
    tid = _create_task(
        conn, project,
        title="filled chore",
        kind="chore",
        outcome="Bump dep X to v2.3 for security patch.",
    )
    from core.board_os.parser import extract_frontmatter
    from core.board_os.transition_gates import load_gates_config
    from core.board_os.transition_gates_validator import Verdict, validate_transition

    body = next((project / "docs/tasks").glob(f"{tid}*.md")).read_text()
    fm = extract_frontmatter(body) or {}
    result = validate_transition(
        task_id=tid,
        kind=str(fm["kind"]),
        body=body,
        new_status="in_progress",
        config=load_gates_config(),
    )
    assert result.verdict is Verdict.PASS


def test_preflight_for_complete_blocks_without_verify(
    project: Path, conn: sqlite3.Connection, monkeypatch,
) -> None:
    """target=complete checks DoD — without verify, BLOCK."""
    monkeypatch.chdir(project)
    tid = _create_task(
        conn, project,
        title="filled feature",
        kind="chore",
        outcome="Sufficient outcome for a chore-kind preflight test.",
    )
    from core.board_os.parser import extract_frontmatter
    from core.board_os.transition_gates import load_gates_config
    from core.board_os.transition_gates_validator import validate_transition

    body = next((project / "docs/tasks").glob(f"{tid}*.md")).read_text()
    fm = extract_frontmatter(body) or {}
    result = validate_transition(
        task_id=tid,
        kind=str(fm["kind"]),
        body=body,
        new_status="complete",
        config=load_gates_config(),
        has_recent_verify=False,
        has_work_log=False,
    )
    assert result.blocked
    assert any(m.code == "DOD_VERIFY_MISSING" for m in result.messages)


def test_preflight_idempotent_no_state_change(
    project: Path, conn: sqlite3.Connection, monkeypatch,
) -> None:
    """Running preflight must not change task status or write history rows."""
    monkeypatch.chdir(project)
    tid = _create_task(
        conn, project, title="idempotent", kind="chore",
        outcome="Outcome long enough for chore.",
    )
    before = conn.execute(
        "SELECT status FROM tasks WHERE task_id = ?", (tid,),
    ).fetchone()[0]
    history_before = conn.execute(
        "SELECT COUNT(*) FROM task_status_history WHERE task_id = ?",
        (tid,),
    ).fetchone()[0]

    # Run preflight twice via the validator (mirrors what CLI does).
    from core.board_os.parser import extract_frontmatter
    from core.board_os.transition_gates import load_gates_config
    from core.board_os.transition_gates_validator import validate_transition

    body = next((project / "docs/tasks").glob(f"{tid}*.md")).read_text()
    fm = extract_frontmatter(body) or {}
    for _ in range(2):
        validate_transition(
            task_id=tid,
            kind=str(fm["kind"]),
            body=body,
            new_status="in_progress",
            config=load_gates_config(),
        )

    after = conn.execute(
        "SELECT status FROM tasks WHERE task_id = ?", (tid,),
    ).fetchone()[0]
    history_after = conn.execute(
        "SELECT COUNT(*) FROM task_status_history WHERE task_id = ?",
        (tid,),
    ).fetchone()[0]

    assert after == before  # status unchanged
    assert history_after == history_before  # no audit row written
