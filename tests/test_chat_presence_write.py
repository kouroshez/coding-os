"""Regression guard for the Hub-chat presence write (TASK-932).

`_chat_presence_write` declares `global _CHAT_PRESENCE_WRITER,
_CHAT_PRESENCE_TRIED` and reads them on the first call. A module split left the
two bindings behind, so the read raised `NameError` straight into the function's
own `except Exception` — the chat never appeared in the Live-agents HUD and
nothing surfaced the failure. An AST scan cannot catch this: `global x` marks
the name local, so the reference looks bound.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from web.routes import _cognition_chat_sdk as chat_sdk  # noqa: E402


def test_probe_state_is_bound_at_module_level() -> None:
    assert chat_sdk._CHAT_PRESENCE_WRITER is None or callable(chat_sdk._CHAT_PRESENCE_WRITER)
    assert isinstance(chat_sdk._CHAT_PRESENCE_TRIED, bool)


def test_first_call_resolves_the_writer_instead_of_swallowing_a_nameerror(
    tmp_path: Path, monkeypatch, caplog
) -> None:
    monkeypatch.setattr(chat_sdk, "_CHAT_PRESENCE_WRITER", None)
    monkeypatch.setattr(chat_sdk, "_CHAT_PRESENCE_TRIED", False)

    written: list[tuple[Path, str, str, str]] = []
    monkeypatch.setattr(
        chat_sdk,
        "_CHAT_PRESENCE_WRITER",
        lambda cwd, agent, sid, event, pid=None: written.append((cwd, agent, sid, event)),
    )
    monkeypatch.setattr(chat_sdk, "_CHAT_PRESENCE_TRIED", True)

    with caplog.at_level("DEBUG", logger=chat_sdk.__name__):
        chat_sdk._chat_presence_write(str(tmp_path), "sid-1", "prompt")

    assert written == [(tmp_path, "claude", "sid-1", "prompt")]
    assert "is not defined" not in caplog.text


def test_cold_probe_binds_the_adapter_writer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(chat_sdk, "_CHAT_PRESENCE_WRITER", None)
    monkeypatch.setattr(chat_sdk, "_CHAT_PRESENCE_TRIED", False)

    chat_sdk._chat_presence_write(str(tmp_path), "sid-2", "stop")

    assert chat_sdk._CHAT_PRESENCE_TRIED is True
    assert callable(chat_sdk._CHAT_PRESENCE_WRITER)
