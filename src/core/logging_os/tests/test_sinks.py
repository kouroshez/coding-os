from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.logging_os import sinks


@pytest.fixture
def temp_log_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("COS_LOG_FILE", raising=False)
    return tmp_path


def _event() -> dict:
    return {
        "ts": "2026-05-14T22:51:11Z",
        "lvl": "WARN",
        "scope": "core.test",
        "msg": "fan-out check",
        "kv": {"file": "x.py"},
    }


def test_dispatch_writes_to_all_three_sinks(
    temp_log_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sinks.dispatch(_event())

    text_log = temp_log_dir / ".cos.log"
    json_log = temp_log_dir / ".cos.log.jsonl"

    assert text_log.exists(), "text sink missing"
    assert json_log.exists(), "jsonl sink missing"

    text_content = text_log.read_text(encoding="utf-8").strip()
    assert text_content == "22:51:11 WARN  core.test fan-out check file=x.py"

    parsed = json.loads(json_log.read_text(encoding="utf-8").strip())
    assert parsed["lvl"] == "WARN"
    assert parsed["file"] == "x.py"

    captured = capsys.readouterr()
    assert "fan-out check" in captured.err


def test_dispatch_appends_multiple_events(temp_log_dir: Path) -> None:
    sinks.dispatch(_event())
    sinks.dispatch(_event())

    text_lines = (temp_log_dir / ".cos.log").read_text(encoding="utf-8").splitlines()
    json_lines = (temp_log_dir / ".cos.log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(text_lines) == 2
    assert len(json_lines) == 2


def test_dispatch_fails_open_when_file_unwritable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    blocked = tmp_path / "no" / "such" / ".cos.log"
    monkeypatch.setenv("COS_LOG_FILE", str(blocked))

    def deny_mkdir(self: Path, *args: object, **kwargs: object) -> None:
        raise OSError("denied")

    monkeypatch.setattr(Path, "mkdir", deny_mkdir)
    sinks.dispatch(_event())

    captured = capsys.readouterr()
    assert "fan-out check" in captured.err


def test_dispatch_truncates_when_cap_exceeded(
    temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COS_LOG_MAX_LINES", "100")
    for _ in range(250):
        sinks.dispatch(_event())
    text_lines = (temp_log_dir / ".cos.log").read_text().splitlines()
    json_lines = (temp_log_dir / ".cos.log.jsonl").read_text().splitlines()
    assert len(text_lines) <= 200
    assert len(text_lines) >= 100
    assert len(json_lines) <= 200
    assert len(json_lines) >= 100


def test_dispatch_survives_broken_stderr(
    temp_log_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenStream:
        def write(self, _value: str) -> int:
            raise BrokenPipeError("closed")

        def flush(self) -> None:
            return None

        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("sys.stderr", BrokenStream())
    sinks.dispatch(_event())

    assert (temp_log_dir / ".cos.log").exists()
