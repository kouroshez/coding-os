"""Smoke-test the executable or import path for every top-level script."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = REPO_ROOT / "src" / "scripts"


def _scripts() -> tuple[Path, ...]:
    """Return runnable top-level scripts, excluding the package marker."""

    return tuple(path for path in sorted(SCRIPT_ROOT.glob("*.py")) if path.name != "__init__.py")


def _command_for(script: Path) -> list[str]:
    """Use the script's public help path, or its safe module-import path."""

    source = script.read_text(encoding="utf-8")
    if "argparse" in source or "click" in source:
        return [sys.executable, str(script), "--help"]
    return [sys.executable, "-c", f"import scripts.{script.stem}"]


@pytest.mark.parametrize("script", _scripts(), ids=lambda path: path.name)
def test_script_entrypoint_smoke(script: Path, tmp_path: Path) -> None:
    """Every script must expose a non-mutating help or import smoke path."""

    env = os.environ.copy()
    pythonpath = [
        str(REPO_ROOT / "src"),
        str(REPO_ROOT / "src" / "core"),
        str(REPO_ROOT / "src" / "core" / "thinking_os"),
        # Several scripts import a sibling unqualified (`from _audit_harness
        # import ...`). That resolves when the file is RUN, because Python puts
        # the script's own directory on sys.path — but not when it is imported
        # as `scripts.<name>`. Without this the smoke test fails scripts that
        # actually work, which is worse than not testing them.
        str(SCRIPT_ROOT),
    ]
    if env.get("PYTHONPATH"):
        pythonpath.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)

    corpus = tmp_path / "corpus"
    (corpus / "docs" / "tasks").mkdir(parents=True)
    (corpus / "docs" / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
    (corpus / "docs" / "tasks" / "TASK-001-example.md").write_text("# TASK-001\n", encoding="utf-8")
    env["COS_CORPUS_PATH"] = str(corpus)

    # A few audit scripts inspect the database during import. Give them an
    # isolated path so a smoke test never creates or reads repository state.
    db_path = tmp_path / "coding-os.db"
    db_path.touch()
    env["COS_DB_PATH"] = str(db_path)

    command = _command_for(script)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, (
        f"{script.relative_to(REPO_ROOT)} failed its smoke command "
        f"({' '.join(command)}):\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
