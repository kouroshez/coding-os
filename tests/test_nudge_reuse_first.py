"""Tests for the reuse-first placement nudge hook (TASK-366).

Exercises the Python delegate's heuristic directly (subprocess) plus a bash
smoke that the hook is fail-open and non-blocking.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "src" / "core" / "hooks"
DELEGATE = HOOKS_DIR / "_nudge_reuse_first.py"
HOOK = HOOKS_DIR / "nudge-reuse-first.sh"


def _run_delegate(rel_path: str, project_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DELEGATE), rel_path, str(project_root)],
        capture_output=True,
        text=True,
        timeout=15,
    )


def _make_service_file(project: Path, service: str, name: str, body: str) -> None:
    path = project / "src" / "services" / service / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# ---------- delegate heuristic ----------


def test_nudge_detects_cross_service_duplicate(tmp_path: Path) -> None:
    _make_service_file(tmp_path, "alpha", "handler.py", "def calculate_invoice_total(x):\n    return x\n")
    _make_service_file(tmp_path, "beta", "billing.py", "def calculate_invoice_total(y):\n    return y\n")
    result = _run_delegate("src/services/alpha/handler.py", tmp_path)
    assert result.returncode == 0
    assert "[reuse-first]" in result.stdout
    assert "calculate_invoice_total" in result.stdout
    assert "src/shared/py/" in result.stdout
    assert "src/services/beta/billing.py" in result.stdout


def test_nudge_silent_when_no_duplicate(tmp_path: Path) -> None:
    _make_service_file(tmp_path, "alpha", "handler.py", "def calculate_invoice_total(x):\n    return x\n")
    _make_service_file(tmp_path, "beta", "other.py", "def render_dashboard():\n    return 1\n")
    result = _run_delegate("src/services/alpha/handler.py", tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_nudge_silent_for_non_service_file(tmp_path: Path) -> None:
    (tmp_path / "src" / "backend").mkdir(parents=True)
    (tmp_path / "src" / "backend" / "main.py").write_text("def calculate_invoice_total():\n    pass\n")
    result = _run_delegate("src/backend/main.py", tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_nudge_silent_for_unsupported_suffix(tmp_path: Path) -> None:
    _make_service_file(tmp_path, "alpha", "notes.md", "# calculate_invoice_total\n")
    result = _run_delegate("src/services/alpha/notes.md", tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_nudge_skips_short_symbol_names(tmp_path: Path) -> None:
    # `run` is 3 chars — below MIN_SYMBOL_LENGTH, too common to nudge on.
    _make_service_file(tmp_path, "alpha", "a.py", "def run(x):\n    return x\n")
    _make_service_file(tmp_path, "beta", "b.py", "def run(y):\n    return y\n")
    result = _run_delegate("src/services/alpha/a.py", tmp_path)
    assert result.stdout.strip() == ""


def test_nudge_detects_go_duplicate(tmp_path: Path) -> None:
    _make_service_file(tmp_path, "alpha", "pay.go", "package alpha\nfunc ProcessPayment() {}\n")
    _make_service_file(tmp_path, "beta", "pay.go", "package beta\nfunc ProcessPayment() {}\n")
    result = _run_delegate("src/services/alpha/pay.go", tmp_path)
    assert "ProcessPayment" in result.stdout
    assert "src/shared/go/" in result.stdout


# ---------- bash hook smoke (fail-open, non-blocking) ----------


def _invoke_hook(payload: dict, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(cwd),
    )


def test_hook_exits_zero_for_non_write_tool(tmp_path: Path) -> None:
    result = _invoke_hook({"tool_name": "Read", "tool_input": {"file_path": "x.py"}}, tmp_path)
    assert result.returncode == 0


def test_hook_exits_zero_for_non_service_path(tmp_path: Path) -> None:
    result = _invoke_hook(
        {"tool_name": "Write", "tool_input": {"file_path": "README.md"}}, tmp_path
    )
    assert result.returncode == 0
    assert result.stderr.strip() == ""
