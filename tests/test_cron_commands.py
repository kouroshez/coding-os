"""Tests for `cos cron` cross-platform install (launchd on macOS / systemd on Linux)."""

from __future__ import annotations

import sys
from pathlib import Path

import click
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cli import cron_commands as cc


def test_render_systemd_substitutes_all_placeholders() -> None:
    service, timer = cc._render_systemd(7)
    assert "{{" not in service, service
    assert "{{" not in timer, timer
    assert "OnCalendar=*-*-* 07:00:00" in timer
    assert "Persistent=true" in timer
    assert "WantedBy=timers.target" in timer
    assert "ExecStart=" in service


def test_render_systemd_zero_pads_hour() -> None:
    _service, timer = cc._render_systemd(3)
    assert "03:00:00" in timer


def test_exec_args_nonempty_strings() -> None:
    args = cc._exec_args()
    assert args and all(isinstance(a, str) and a for a in args)


def test_install_unsupported_os_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cc.platform, "system", lambda: "Plan9")
    with pytest.raises(click.ClickException):
        cc.cron_install.callback(hour=3)


def test_install_rejects_bad_hour() -> None:
    with pytest.raises(click.ClickException):
        cc.cron_install.callback(hour=25)
