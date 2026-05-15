from __future__ import annotations

import io

import pytest

from core.logging_os import config


def _force_stderr_tty(monkeypatch: pytest.MonkeyPatch, isatty: bool) -> None:
    class FakeStream(io.StringIO):
        def isatty(self) -> bool:
            return isatty

    monkeypatch.setattr("sys.stderr", FakeStream())


def test_json_env_overrides_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COS_LOG_JSON", "1")
    monkeypatch.setenv("COS_LOG_FORCE_PRETTY", "1")
    _force_stderr_tty(monkeypatch, True)
    assert config.detect_render() == "json"


def test_force_pretty_when_no_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COS_LOG_JSON", raising=False)
    monkeypatch.setenv("COS_LOG_FORCE_PRETTY", "1")
    _force_stderr_tty(monkeypatch, False)
    assert config.detect_render() == "pretty"


def test_no_color_drops_to_short_even_in_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COS_LOG_JSON", raising=False)
    monkeypatch.delenv("COS_LOG_FORCE_PRETTY", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    _force_stderr_tty(monkeypatch, True)
    assert config.detect_render() == "short"


def test_pipe_renders_short(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COS_LOG_JSON", raising=False)
    monkeypatch.delenv("COS_LOG_FORCE_PRETTY", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    _force_stderr_tty(monkeypatch, False)
    assert config.detect_render() == "short"


def test_tty_renders_pretty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COS_LOG_JSON", raising=False)
    monkeypatch.delenv("COS_LOG_FORCE_PRETTY", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    _force_stderr_tty(monkeypatch, True)
    assert config.detect_render() == "pretty"


def test_normalize_scope_accepts_dotted_snake() -> None:
    canonical, raw = config.normalize_scope("cli.doctor")
    assert canonical == "cli.doctor"
    assert raw is None


def test_normalize_scope_rejects_uppercase() -> None:
    canonical, raw = config.normalize_scope("Cli.Doctor")
    assert canonical == config.INVALID_SCOPE_FALLBACK
    assert raw == "Cli.Doctor"


def test_normalize_scope_rejects_undotted() -> None:
    canonical, _ = config.normalize_scope("noscope")
    assert canonical == config.INVALID_SCOPE_FALLBACK


def test_normalize_scope_rejects_empty() -> None:
    canonical, _ = config.normalize_scope("")
    assert canonical == config.INVALID_SCOPE_FALLBACK


def test_normalize_scope_rejects_too_long() -> None:
    canonical, _ = config.normalize_scope("a." + "b" * 60)
    assert canonical == config.INVALID_SCOPE_FALLBACK


def test_current_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COS_LOG_LEVEL", raising=False)
    assert config.current_level() == config.Level.INFO


def test_current_level_falls_back_on_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COS_LOG_LEVEL", "loud")
    assert config.current_level() == config.Level.INFO


def test_setup_persists_level_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COS_LOG_LEVEL", raising=False)
    config.setup(level="warn")
    assert config.current_level() == config.Level.WARN
