"""Hooks that run coding-os Python must work from a consumer root, which has no core package.

Spec: docs/engineering/hooks-reference.md § Adding a new hook.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_BODY_HOOK = REPO_ROOT / "src" / "core" / "hooks" / "enforce-task-body.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("cos") is None or shutil.which("jq") is None,
    reason="resolves the interpreter from the cos entry point and parses JSON with jq",
)


def _consumer(tmp_path: Path) -> Path:
    project = tmp_path / "consumer"
    (project / ".coding-os").mkdir(parents=True)
    (project / "docs" / "tasks").mkdir(parents=True)
    return project


def _completing_bug_without_acceptance(project: Path) -> str:
    content = "---\nid: TASK-999\nkind: bug\nstatus: complete\n---\nbody only\n"
    return json.dumps(
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(project / "docs" / "tasks" / "TASK-999-probe.md"),
                "content": content,
            },
        }
    )


def _run(project: Path, payload: str, path: str | None = None) -> subprocess.CompletedProcess:
    # A consumer session has no VIRTUAL_ENV/UV_* pointing at coding-os; pytest under
    # `uv run` does, and that alone made the old `uv run python -m core` pass here.
    leaked = ("COS_", "CLAUDE_", "UV_", "VIRTUAL_ENV")
    env = {k: v for k, v in os.environ.items() if not k.startswith(leaked)}
    env |= {"COS_PROJECT_ROOT": str(project), "COS_AGENT": "claude"}
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        ["bash", str(TASK_BODY_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=project,
    )


def _last_log_line(project: Path) -> str:
    return (project / ".coding-os" / ".hooks.log").read_text(encoding="utf-8").splitlines()[-1]


def test_task_gate_runs_from_a_consumer_root(tmp_path: Path) -> None:
    project = _consumer(tmp_path)

    proc = _run(project, _completing_bug_without_acceptance(project))

    assert "ModuleNotFoundError" not in proc.stderr
    assert proc.returncode == 2, proc.stderr
    assert "DOD_ACCEPTANCE_MISSING" in proc.stderr
    assert "[enforce-task-body] [block]" in _last_log_line(project)


def test_a_runner_crash_is_logged_as_error_not_block(tmp_path: Path) -> None:
    project = _consumer(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("jq", "perl", "bash", "dirname", "cat", "date", "mkdir", "head", "tr"):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    fake_python = bin_dir / "python3"
    fake_python.write_text("#!/bin/sh\necho 'no module named core' >&2\nexit 1\n")
    fake_python.chmod(0o755)

    proc = _run(project, _completing_bug_without_acceptance(project), path=str(bin_dir))

    assert proc.returncode == 1
    assert "[enforce-task-body] [error]" in _last_log_line(project)


@pytest.mark.parametrize("shebang", ["#!/bin/sh", "#!/usr/bin/env python3"])
def test_a_cos_script_without_a_python_shebang_resolves_the_venv_python(
    tmp_path: Path, shebang: str
) -> None:
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python3").symlink_to(shutil.which("python3"))
    cos = venv_bin / "cos"
    cos.write_text(f"{shebang}\nexec true\n")
    cos.chmod(0o755)

    proc = subprocess.run(
        ["bash", "-c", f'source "{REPO_ROOT}/src/core/hooks/_cos_env_io.sh"; cos_resolve_python'],
        env={**os.environ, "PATH": f"{venv_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=True,
    )

    assert proc.stdout.strip() == str(venv_bin / "python3")
