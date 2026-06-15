"""Smoke tests for install.sh — the GUI-first install path (TASK-390, ADR-0007).

The installer boots the Hub from a machine with no prior `cos` CLI. These tests
guard it without touching the real network or starting a real server: syntax +
shellcheck, structural contract (preflight + bootstrap-doctor + hub start), and
one end-to-end run with every external command stubbed and HOME isolated.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"


def test_install_script_exists() -> None:
    assert INSTALL_SH.is_file(), "install.sh missing from repo root"


def test_syntax_valid() -> None:
    result = subprocess.run(
        ["bash", "-n", str(INSTALL_SH)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"install.sh syntax error: {result.stderr}"


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_shellcheck_clean() -> None:
    result = subprocess.run(
        ["shellcheck", str(INSTALL_SH)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"shellcheck findings:\n{result.stdout}"


def test_structural_contract() -> None:
    """The script must preflight prerequisites, verify via bootstrap doctor,
    bind the Hub to localhost, and never assume a pre-existing CLI."""
    text = INSTALL_SH.read_text()
    assert "set -euo pipefail" in text
    for tool in ("git", "uv"):  # preflight prerequisite checks
        assert f"command -v {tool}" in text, f"preflight missing {tool} check"
    assert "cos doctor --bootstrap" in text, "no bootstrap-doctor verification"
    assert "hub start" in text, "never starts the Hub"
    assert "127.0.0.1" in text, "Hub not bound to localhost"
    assert "COS_HUB_TOKEN" in text, "no auth-token seam (TASK-363)"


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    path.chmod(0o755)


def test_smoke_runs_with_mocked_commands(tmp_path: Path) -> None:
    """End-to-end run with git/uv/cos stubbed and HOME isolated — no network,
    no real Hub. Asserts the script reaches bootstrap-doctor + hub start."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    call_log = tmp_path / "cos-calls.log"

    _stub(bin_dir, "git", "exit 0")
    _stub(bin_dir, "uv", "exit 0")
    # `cos` records its argv so we can assert the boot sequence ran.
    _stub(bin_dir, "cos", f'echo "$@" >> "{call_log}"\nexit 0')

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["HOME"] = str(home)  # so install_cli's ~/.local/bin prepend stays empty

    result = subprocess.run(
        ["bash", str(INSTALL_SH)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),  # detected as the coding-os checkout (no git clone)
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, f"installer failed:\n{result.stdout}\n{result.stderr}"
    assert "onboarding wizard" in result.stdout
    calls = call_log.read_text()
    assert "doctor --bootstrap" in calls, "bootstrap doctor not invoked"
    assert "hub start" in calls, "hub start not invoked"
