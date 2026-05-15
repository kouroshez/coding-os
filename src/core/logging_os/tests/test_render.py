from __future__ import annotations

import json

import pytest

from core.logging_os import render as render_mod
from core.logging_os.render import RESET, render_json, render_pretty, render_short


@pytest.fixture
def event() -> dict:
    return {
        "ts": "2026-05-14T22:51:11Z",
        "lvl": "WARN",
        "scope": "hook.enforce_skill",
        "msg": "graph-explorer not loaded",
        "kv": {"file": "src/core/x.py"},
    }


def test_short_is_single_line_with_kv_appended(event: dict) -> None:
    line = render_short(event)
    assert line == "22:51:11 WARN  hook.enforce_skill graph-explorer not loaded file=src/core/x.py"
    assert "\n" not in line


def test_short_omits_kv_when_empty(event: dict) -> None:
    event["kv"] = {}
    line = render_short(event)
    assert line == "22:51:11 WARN  hook.enforce_skill graph-explorer not loaded"


def test_pretty_starts_with_emoji_and_includes_color_reset(event: dict) -> None:
    line = render_pretty(event)
    assert line.startswith("⚠️ ")
    assert RESET in line
    assert "WARN" in line
    assert "graph-explorer not loaded" in line
    assert "file=src/core/x.py" in line


def test_pretty_pads_scope_for_alignment(event: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COS_LOG_SCOPE_WIDTH", "30")
    line = render_pretty(event)
    assert "hook.enforce_skill" + " " * 12 in line


def test_json_is_valid_ndjson_with_flattened_kv(event: dict) -> None:
    line = render_json(event)
    parsed = json.loads(line)
    assert parsed == {
        "ts": "2026-05-14T22:51:11Z",
        "lvl": "WARN",
        "scope": "hook.enforce_skill",
        "msg": "graph-explorer not loaded",
        "file": "src/core/x.py",
    }
    assert "\n" not in line


def test_json_does_not_overwrite_reserved_keys(event: dict) -> None:
    event["kv"] = {"msg": "shadow attempt", "extra": "kept"}
    parsed = json.loads(render_json(event))
    assert parsed["msg"] == "graph-explorer not loaded"
    assert parsed["extra"] == "kept"


def test_render_dispatch_falls_back_to_short_for_unknown_mode(event: dict) -> None:
    assert render_mod.render("unknown_mode", event) == render_short(event)


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "OK", "WARN", "ERROR", "FATAL"])
def test_pretty_has_emoji_for_every_level(event: dict, level: str) -> None:
    event["lvl"] = level
    line = render_pretty(event)
    assert line.split("  ")[0].strip(), f"missing emoji prefix for {level}"


def test_value_with_space_is_quoted_in_short(event: dict) -> None:
    event["kv"] = {"path": "src/has space/x.py"}
    line = render_short(event)
    assert 'path="src/has space/x.py"' in line
