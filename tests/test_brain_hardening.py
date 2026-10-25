"""Regression coverage for the surviving R-items of the brain pipeline hardening.

- R3:  cos-env.sh resolves COS_AGENT_MODEL from env + .model file.
- R11: retrieve._normalize_task_id extracts TASK-NNN from composite markers.
- R17: session-context.sh rewrites .agent marker on Claude startup.
"""

from __future__ import annotations

import json
import os
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
