"""_rotate_telemetry_atomically: rotation under size cap, atomic rename."""
from __future__ import annotations

import os
from pathlib import Path

from graph_os.tools import graph as gtools


def test_no_rotation_when_under_cap(tmp_path: Path, monkeypatch):
    log = tmp_path / "tel.jsonl"
    log.write_text("a" * 1024, encoding="utf-8")
    gtools._rotate_telemetry_atomically(str(log))
    assert log.read_text() == "a" * 1024


def test_rotation_drops_first_half_when_over_cap(tmp_path: Path, monkeypatch):
    log = tmp_path / "tel.jsonl"
    cap = gtools._TELEMETRY_MAX_BYTES
    payload = b"x" * (cap + 1000)
    log.write_bytes(payload)
    gtools._rotate_telemetry_atomically(str(log))
    after = log.read_bytes()
    assert len(after) <= cap // 2 + 1000 + 1
    assert len(after) > 0


def test_rotation_cleans_up_tmp_on_failure(tmp_path: Path, monkeypatch):
    log = tmp_path / "missing-dir" / "tel.jsonl"
    gtools._rotate_telemetry_atomically(str(log))
    siblings = list(tmp_path.glob("*.rotating"))
    assert siblings == []


def test_emit_telemetry_appends_one_line(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
    gtools._TELEMETRY_PATH_CACHE.clear()
    gtools._emit_telemetry(meta={"layer": "graph", "backend": "sqlite"}, ok=True)
    log = tmp_path / ".graph-telemetry.jsonl"
    assert log.exists()
    lines = log.read_text().splitlines()
    assert len(lines) == 1
    assert "\"ok\": true" in lines[0]
    assert "\"backend\": \"sqlite\"" in lines[0]
