"""TASK-668 — the test-cadence reminder rides the formal pulse, never casual chat."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks" / "session-context.sh"


def _pulse(tmp_path: Path, mode: str) -> str:
    panel = tmp_path / "panels" / "smoke"
    panel.mkdir(parents=True, exist_ok=True)
    (panel / "session-id").write_text("ses-smoke", encoding="utf-8")
    # Write to both the panel-first path and the agent-dir fallback so the
    # hook resolves the mode regardless of panel-dir computation.
    (panel / ".task-mode").write_text(mode, encoding="utf-8")
    (tmp_path / ".task-mode").write_text(mode, encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"session_id": "ses-smoke", "prompt": "x"}).encode(),
        capture_output=True,
        timeout=30,
        env={
            **os.environ,
            "COS_AGENT_DIR": str(tmp_path),
            "COS_PANEL_ID": "smoke",
            "COS_STATE_DIR": str(tmp_path),
        },
    )
    return proc.stdout.decode(errors="ignore")


def test_cadence_in_formal(tmp_path: Path) -> None:
    assert "test-cadence" in _pulse(tmp_path, "formal")


def test_no_cadence_in_query(tmp_path: Path) -> None:
    assert "test-cadence" not in _pulse(tmp_path, "query")


def test_no_cadence_in_chore(tmp_path: Path) -> None:
    assert "test-cadence" not in _pulse(tmp_path, "chore")


def test_banner_still_emitted_in_formal(tmp_path: Path) -> None:
    # The cadence is appended AFTER the banner line — the banner contract is intact.
    assert "USER_BANNER" in _pulse(tmp_path, "formal")
