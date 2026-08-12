"""Smoke-test the executable or import path for every top-level script."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPO_ROOT / "src" / "scripts"
SMOKE_TIMEOUT_S = 30

# A developer's live panel or another project's state dir would otherwise steer
# these scripts, so the suite would pass or fail by machine rather than by code.
_INHERITED_STATE_ENV = (
    "COS_STATE_DIR",
    "COS_AGENT_DIR",
    "COS_PANEL_DIR",
    "COS_AGENT_SESSION_ID",
    "CLAUDE_PROJECT_DIR",
    "CODEX_PROJECT_DIR",
    "PYTHONPATH",
)


# Loading by file path rather than as `scripts.<name>` keeps one mechanism for
# every directory: src/scripts/dev/ has no package marker, and adding one to
# satisfy a test would put a dev-only tree into the packaging story.
_LOAD_BY_PATH = (
    "import importlib.util as u, sys; "
    "s = u.spec_from_file_location('smoke', sys.argv[1]); "
    "m = u.module_from_spec(s); "
    "s.loader.exec_module(m)"
)


def _scripts() -> tuple[Path, ...]:
    # `_`-prefixed modules are helpers imported by an entry script, not
    # entrypoints; each is covered transitively by the script that drives it.
    # Recursive: src/scripts/dev/ holds eight more, two of them Makefile targets.
    return tuple(
        p
        for p in sorted(SCRIPT_ROOT.rglob("*.py"))
        if not p.name.startswith("_") and "__pycache__" not in p.parts
    )


def _command_for(script: Path) -> list[str]:
    source = script.read_text(encoding="utf-8")
    # Match the import, not the bare word: prose mentioning "click" must not
    # route a mutating script to an `--help` it does not implement.
    if "import argparse" in source or "import click" in source:
        return [sys.executable, str(script), "--help"]
    return [sys.executable, "-c", _LOAD_BY_PATH, str(script)]


def _pythonpath_for(script: Path, command: list[str]) -> str | None:
    # Running a file by path must inherit NOTHING: the script's own sys.path
    # bootstrap is the thing under test, and injecting src/core here would mask
    # a broken bootstrap (a wrong `sys.path.insert` still resolves, so the
    # smoke test greenlights a script that dies under a real invocation).
    if "-c" not in command:
        return None
    # The import form needs the package root, plus the script's OWN directory for
    # the siblings some scripts import unqualified (`from _audit_harness import
    # ...`) — that resolves when the file is RUN, but not under a bare import.
    return os.pathsep.join((str(REPO_ROOT / "src"), str(script.parent)))


def _failure(
    script: Path, command: list[str], what: str, stdout: str | None, stderr: str | None
) -> str:
    return (
        f"{script.relative_to(REPO_ROOT)} {what} on its smoke command.\n"
        f"reproduce: {' '.join(command)}\n"
        f"stdout:\n{stdout or ''}\nstderr:\n{stderr or ''}"
    )


def test_the_script_set_is_discovered() -> None:
    # An empty parametrize set is reported as a skip, not a failure, so a moved
    # or renamed script root would hollow this suite out and still exit 0.
    found = _scripts()
    assert len(found) >= 28, f"only {len(found)} scripts found under {SCRIPT_ROOT}"
    # The dev/ tree is the half that has no package marker, so a regression that
    # silently drops it would still clear a flat count.
    assert any(p.parent.name == "dev" for p in found), "src/scripts/dev is not being discovered"


@pytest.mark.parametrize("script", _scripts(), ids=lambda path: path.name)
def test_script_entrypoint_smoke(script: Path, tmp_path: Path) -> None:
    env = os.environ.copy()
    for key in _INHERITED_STATE_ENV:
        env.pop(key, None)

    corpus = tmp_path / "corpus"
    (corpus / "docs" / "tasks").mkdir(parents=True)
    (corpus / "docs" / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
    (corpus / "docs" / "tasks" / "TASK-001-example.md").write_text("# TASK-001\n", encoding="utf-8")
    env["COS_CORPUS_PATH"] = str(corpus)

    # A few audit scripts open the database during import. Give them an
    # isolated path so a smoke test never creates or reads repository state.
    env["COS_DB_PATH"] = str(tmp_path / "coding-os.db")

    command = _command_for(script)
    pythonpath = _pythonpath_for(script, command)
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath

    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=SMOKE_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        pytest.fail(
            _failure(
                script,
                command,
                f"hung past {SMOKE_TIMEOUT_S}s",
                expired.stdout,
                expired.stderr,
            )
        )

    assert result.returncode == 0, _failure(
        script, command, f"exited {result.returncode}", result.stdout, result.stderr
    )
