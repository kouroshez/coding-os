from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core import logging_os
from core.logging_os import api


@pytest.fixture
def temp_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("COS_LOG_FILE", raising=False)
    monkeypatch.delenv("COS_LOG_LEVEL", raising=False)
    monkeypatch.delenv("COS_DB_PATH", raising=False)
    monkeypatch.delenv("COS_SESSION_ID", raising=False)
    monkeypatch.delenv("COS_PANEL_ID", raising=False)
    monkeypatch.delenv("COS_TRACE_ID", raising=False)
    return tmp_path


def test_public_surface_is_locked() -> None:
    expected = {
        "CosFatalError",
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
        "swallow_safe",
        "swallowed_count",
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


def test_level_floor_drops_lower_events(temp_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_fatal_raises_cos_fatal_error_after_emit(temp_state: Path) -> None:
    with pytest.raises(logging_os.CosFatalError):
        logging_os.fatal("cli.test", "abort")
    text_log = (temp_state / ".cos.log").read_text()
    assert "abort" in text_log


def test_setup_changes_level_floor(temp_state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def _migrated_db(state_dir: Path) -> None:
    try:
        from core.thinking_os.database import init_db
    except ImportError:
        from thinking_os.database import init_db
    init_db(state_dir / "coding-os.db").close()


def test_error_redacts_secret_in_message(temp_state: Path) -> None:
    logging_os.error("cli.test", "auth failed token=abc123secretvalue tail")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip())
    assert "abc123secretvalue" not in parsed["msg"]
    assert "<redacted>" in parsed["msg"]


def test_error_redacts_sensitive_kv_key(temp_state: Path) -> None:
    logging_os.error("cli.test", "boom", password="hunter2", file="x.py")
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip())
    assert parsed["password"] == "<redacted>"
    assert parsed["file"] == "x.py"


def test_error_with_exc_captures_type_and_stack(temp_state: Path) -> None:
    _migrated_db(temp_state)
    try:
        raise ValueError("deep cause")
    except ValueError as exc:
        logging_os.error("cli.test", "operation failed", exc=exc)
    parsed = json.loads((temp_state / ".cos.log.jsonl").read_text().strip())
    assert parsed["exc"] == "ValueError"
    row = sqlite3.connect(str(temp_state / "coding-os.db")).execute(
        "SELECT exc_type, stack FROM log_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "ValueError"
    assert row[1] and "deep cause" in row[1]


def test_swallow_safe_counts_and_stays_quiet_at_default_level(temp_state: Path) -> None:
    before = logging_os.swallowed_count()
    try:
        raise RuntimeError("oops")
    except RuntimeError as exc:
        logging_os.swallow_safe("cli.test", "fire and forget", exc=exc)
    assert logging_os.swallowed_count() == before + 1
    # default level=info → the debug emit is dropped (quiet); the counter is the always-on signal
    jsonl = temp_state / ".cos.log.jsonl"
    if jsonl.exists():
        assert "fire and forget" not in jsonl.read_text()


def test_session_and_trace_stamped_from_env(
    temp_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COS_SESSION_ID", "ses-xyz")
    monkeypatch.setenv("COS_TRACE_ID", "trace-1")
    _migrated_db(temp_state)
    logging_os.error("cli.test", "boom")
    row = sqlite3.connect(str(temp_state / "coding-os.db")).execute(
        "SELECT session_id, trace_id FROM log_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "ses-xyz"
    assert row[1] == "trace-1"
