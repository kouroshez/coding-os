"""Unit tests for cli.board_commands runtime/session detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli import board_commands

_ENV_KEYS = [
    "COS_AGENT",
    "COS_AGENT_DIR",
    "COS_PANEL_DIR",
    "COS_AGENT_SESSION_ID",
    "COS_PROJECT_ROOT",
    "CURSOR_AGENT",
    "CURSOR_PROJECT_DIR",
    "CURSOR_VERSION",
    "CODEX_SESSION_ID",
    "CODEX_AGENT_DIR",
    "CODEX_HOME",
    "CLAUDECODE",
    "CLAUDE_CODE_SSE_PORT",
    "CLAUDE_PROJECT_DIR",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_AGENT_SDK_VERSION",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every detector input so each test sets exactly what it needs."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _write_session(project: Path, agent: str, sid: str) -> None:
    d = project / ".coding-os" / agent
    d.mkdir(parents=True, exist_ok=True)
    (d / "session-id").write_text(sid, encoding="utf-8")


def test_explicit_cos_agent_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COS_AGENT", "codex")
    monkeypatch.setenv("CURSOR_AGENT", "1")  # would otherwise win
    assert board_commands._detect_agent_runtime() == "codex"


def test_cursor_env_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CURSOR_AGENT", "1")
    assert board_commands._detect_agent_runtime() == "cursor"


def test_claude_code_env_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    assert board_commands._detect_agent_runtime() == "claude"


def test_claude_code_entrypoint_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """VSCode/Antigravity variants only export CLAUDE_CODE_ENTRYPOINT."""
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "claude-vscode")
    assert board_commands._detect_agent_runtime() == "claude"


def test_claude_agent_sdk_version_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_AGENT_SDK_VERSION", "0.2.119")
    assert board_commands._detect_agent_runtime() == "claude"


def test_codex_env_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_SESSION_ID", "abc")
    assert board_commands._detect_agent_runtime() == "codex"


def test_priority_prefers_claude_over_codex_and_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CODEX_SESSION_ID", "abc")
    monkeypatch.setenv("CURSOR_AGENT", "1")
    assert board_commands._detect_agent_runtime() == "claude"


def test_priority_prefers_codex_over_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODEX_SESSION_ID", "abc")
    monkeypatch.setenv("CURSOR_AGENT", "1")
    assert board_commands._detect_agent_runtime() == "codex"


def test_marker_file_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / ".agent").write_text("claude\n", encoding="utf-8")
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    assert board_commands._detect_agent_runtime() == "claude"


def test_no_signals_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    assert board_commands._detect_agent_runtime() is None


def test_agent_session_id_reads_matching_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_session(tmp_path, "claude", "ses-claude-20260424-abcdef")
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDECODE", "1")
    assert board_commands._agent_session_id() == "ses-claude-20260424-abcdef"


def test_agent_session_id_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COS_AGENT_SESSION_ID", "ses-explicit-override")
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    assert board_commands._agent_session_id() == "ses-explicit-override"


def test_agent_session_id_returns_none_when_no_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    assert board_commands._agent_session_id() is None


def test_agent_session_id_prefers_active_session_over_fossil(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flat session-id freezes at its last SessionStart; .active-session
    is refreshed every prompt and must win in the no-env fallback (TASK-341 —
    weeks-old fossils were attributed to fresh CLI board mutations)."""
    _write_session(tmp_path, "claude", "ses-claude-20260527-fossil")
    (tmp_path / ".coding-os" / "claude" / ".active-session").write_text(
        "ses-claude-20260610-fresh\n", encoding="utf-8"
    )
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("CLAUDECODE", "1")
    assert board_commands._agent_session_id() == "ses-claude-20260610-fresh"
