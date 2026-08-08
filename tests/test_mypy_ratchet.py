"""Smoke + branch coverage for the mypy count-ratchet gate (src/scripts/mypy_ratchet.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "src" / "scripts" / "mypy_ratchet.py"

sys.path.insert(0, str(SCRIPT.parent))
import mypy_ratchet


def _run_with_output(monkeypatch, stdout: str) -> int:
    monkeypatch.setattr(
        mypy_ratchet.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout=stdout, returncode=1),
    )
    return mypy_ratchet.main()


def test_passes_at_or_below_baseline(monkeypatch, capsys) -> None:
    at = f"Found {mypy_ratchet.BASELINE} errors in 272 files (checked 277 source files)"
    assert _run_with_output(monkeypatch, at) == 0
    below = "Found 1 errors in 1 file (checked 277 source files)"
    assert _run_with_output(monkeypatch, below) == 0
    assert "lower BASELINE" in capsys.readouterr().out


def test_fails_above_baseline(monkeypatch, capsys) -> None:
    above = f"x.py:1: error: boom\nFound {mypy_ratchet.BASELINE + 1} errors in 1 file"
    assert _run_with_output(monkeypatch, above) == 1
    assert "FAIL" in capsys.readouterr().out


def test_clean_tree_passes(monkeypatch) -> None:
    assert _run_with_output(monkeypatch, "Success: no issues found in 277 source files") == 0


def test_unparseable_output_is_loud(monkeypatch) -> None:
    assert _run_with_output(monkeypatch, "internal error: crashed") == 2


def test_script_runs_as_entrypoint() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(SCRIPT.parent)!r}); import mypy_ratchet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
