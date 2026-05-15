from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import logging_os
from core.logging_os import api


@pytest.fixture
def temp_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("COS_LOG_FILE", raising=False)
    monkeypatch.delenv("COS_LOG_LEVEL", raising=False)
    return tmp_path


def test_public_surface_is_locked() -> None:
    expected = {
        "Level",
        "ScopedLogger",
        "debug",
        "error",
        "fatal",
        "info",
        "install_bridge",
        "ok",
        "scoped",
        "setup",
        "uninstall_bridge",
        "warn",
    }
    assert set(logging_os.__all__) == expected
    for name in expected:
        assert hasattr(logging_os, name), f"missing public export: {name}"


def test_warn_emits_event_to_all_sinks(
    temp_state: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    logging_os.warn("cli.test", "something happened", file="x.py")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip())
    assert parsed["lvl"] == "WARN"
    assert parsed["scope"] == "cli.test"
    assert parsed["file"] == "x.py"
    captured = capsys.readouterr()
    assert "something happened" in captured.err


def test_level_floor_drops_lower_events(
    temp_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COS_LOG_LEVEL", "warn")
    logging_os.info("cli.test", "muted")
    logging_os.warn("cli.test", "kept")
    text_log = (temp_state / ".cos.log").read_text()
    assert "muted" not in text_log
    assert "kept" in text_log


def test_invalid_scope_falls_back_and_keeps_raw(temp_state: Path) -> None:
    logging_os.warn("Bad Scope", "msg")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip())
    assert parsed["scope"] == "invalid.scope"
    assert parsed["raw_scope"] == "Bad Scope"


def test_scoped_binds_scope(temp_state: Path) -> None:
    log = logging_os.scoped("cli.bound")
    log.error("boom", code="E1")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip())
    assert parsed["scope"] == "cli.bound"
    assert parsed["lvl"] == "ERROR"
    assert parsed["code"] == "E1"


def test_fatal_exits_after_emit(temp_state: Path) -> None:
    with pytest.raises(SystemExit) as info:
        logging_os.fatal("cli.test", "abort")
    assert info.value.code == 1
    text_log = (temp_state / ".cos.log").read_text()
    assert "abort" in text_log


def test_setup_changes_level_floor(
    temp_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COS_LOG_LEVEL", raising=False)
    logging_os.setup(level="error")
    logging_os.warn("cli.test", "muted")
    logging_os.error("cli.test", "kept")
    text_log = (temp_state / ".cos.log").read_text()
    assert "muted" not in text_log
    assert "kept" in text_log


def test_emit_returns_iso_utc_timestamp(temp_state: Path) -> None:
    api.info("cli.test", "ts check")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip())
    assert parsed["ts"].endswith("Z")
    assert "T" in parsed["ts"]
    assert len(parsed["ts"]) == 20
