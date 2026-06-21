"""Tests for the SDK-uuid bridge captured into presence (TASK-184)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_HELPER = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "core"
    / "hooks"
    / "_helpers"
    / "presence_write.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("presence_write", _HELPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sdk_uuid_is_captured(tmp_path):
    pw = _load()
    f = tmp_path / "ses-claude-x.json"
    rc = pw.main(
        [
            "prog",
            str(f),
            "claude",
            "ses-claude-x",
            "123",
            "prompt",
            "1000",
            "claude-opus-4-8",
            "sdk-abc",
        ]
    )
    assert rc == 0
    d = json.loads(f.read_text())
    assert d["sdk_uuid"] == "sdk-abc"
    assert d["model"] == "claude-opus-4-8"
    assert d["session_id"] == "ses-claude-x"


def test_sdk_uuid_preserved_across_events(tmp_path):
    pw = _load()
    f = tmp_path / "ses.json"
    pw.main(["prog", str(f), "claude", "ses", "1", "start", "1000", "", "uuid-1"])
    # A later event without the sdk_uuid arg must not wipe it.
    pw.main(["prog", str(f), "claude", "ses", "1", "tool", "1005", ""])
    d = json.loads(f.read_text())
    assert d["sdk_uuid"] == "uuid-1"


def test_backward_compatible_without_sdk_uuid(tmp_path):
    pw = _load()
    f = tmp_path / "ses.json"
    rc = pw.main(["prog", str(f), "claude", "ses", "1", "prompt", "1000"])
    assert rc == 0
    d = json.loads(f.read_text())
    assert d["sdk_uuid"] is None
