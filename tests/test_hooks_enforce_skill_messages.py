"""enforce-skill names only remedies every project has and every code gate accepts.

The hook runs in every consumer; naming a stack's skill sent a project without
that stack to a skill it does not have, and naming a domain skill the .ts gate
does not accept blocked the agent again after it followed the advice.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "src" / "core" / "hooks" / "enforce-skill.sh"


def _stack_only_skills() -> set[str]:
    core = {path.name for path in (REPO / "src" / "core" / "skills").iterdir() if path.is_dir()}
    stacks = {
        path.name for path in (REPO / "src" / "templates").glob("*/skills/*") if path.is_dir()
    }
    return stacks - core


def test_no_block_message_names_a_stack_only_skill() -> None:
    messages = [line for line in HOOK.read_text(encoding="utf-8").splitlines() if "echo" in line]
    named = {skill for skill in _stack_only_skills() if any(skill in line for line in messages)}
    assert named == set()


def test_a_session_without_a_skill_is_told_to_load_clean_code(tmp_path: Path) -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": "src/backend/app/main.py"}}
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
        env={
            "PATH": "/usr/bin:/bin",
            "COS_PANEL_DIR": str(tmp_path),
            "COS_AGENT_DIR": str(tmp_path),
        },
        check=False,
    )
    assert result.returncode == 2
    assert 'Skill skill: "clean-code"' in result.stderr
