"""The PostToolUseFailure capture helper is a 2nd memory writer — the re-audit
found it persisted tool-error text raw, leaking the OS username (PII) and never
redacting secrets. It now routes title/narrative/files_modified/facts through the
same SSOT (sanitizer.redact_secrets + scrub_username) the capture hook uses."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src" / "core" / "thinking_os"))
sys.path.insert(0, str(_ROOT / "src" / "core" / "hooks" / "_helpers"))

from database import init_db  # noqa: E402
import tool_failure_capture  # noqa: E402


def test_failure_capture_scrubs_username_and_secrets(tmp_path: Path) -> None:
    db = tmp_path / ".coding-os" / "coding-os.db"
    db.parent.mkdir(parents=True)
    conn = init_db(db)
    home = str(Path.home())
    user = Path.home().name
    payload = {
        "tool_name": "Edit",
        "error": f"Edit failed at {home}/proj/x.py key=AKIA1234567890ABCDEF mail a@b.com",
        "tool_input": {"file_path": f"{home}/proj/x.py"},
    }

    status = tool_failure_capture.capture(conn, "ses-1", payload)
    assert status == "captured"

    narrative, fm, facts = conn.execute(
        "SELECT narrative, files_modified, facts FROM observations LIMIT 1"
    ).fetchone()
    conn.close()

    assert user not in narrative  # username scrubbed
    assert user not in (fm or "")  # files_modified scrubbed
    assert user not in facts  # facts.error_snippet scrubbed
    assert "AKIA" not in narrative  # AWS key redacted
    assert "a@b.com" not in narrative  # email redacted


def _fresh(tmp_path: Path):
    db = tmp_path / ".coding-os" / "coding-os.db"
    db.parent.mkdir(parents=True)
    return init_db(db)


def test_blocked_input_records_hook_block(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    payload = {
        "tool_name": "Edit",
        "error": "BLOCKED: no domain skill invoked",
        "tool_input": {"file_path": "src/x.py"},
    }
    assert tool_failure_capture.capture(conn, "s", payload) == "captured"
    mt, title, impact = conn.execute(
        "SELECT memory_type, title, impact_score FROM observations LIMIT 1"
    ).fetchone()
    conn.close()
    assert mt == "hook_block"  # blocked → hook_block (not 'error')
    assert title.startswith("[BLOCKED] ")
    assert impact == 0.6  # blocked impact, distinct from 0.3 for plain errors


def test_empty_payload_skipped(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    assert tool_failure_capture.capture(conn, "s", {"tool_name": "Edit"}) == "empty_payload"
    assert tool_failure_capture.capture(conn, "s", {"error": "boom"}) == "empty_payload"
    conn.close()


def test_noisy_bash_failure_skipped(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    # A non-blocked Bash failure is too noisy → skipped (but a BLOCKED Bash is kept).
    payload = {"tool_name": "Bash", "error": "exit 1", "tool_input": {"command": "ls"}}
    assert tool_failure_capture.capture(conn, "s", payload) == "skipped_noisy"
    conn.close()


def test_no_observations_table(tmp_path: Path) -> None:
    raw = sqlite3.connect(":memory:")  # no migrations → no observations table
    raw.row_factory = sqlite3.Row
    payload = {"tool_name": "Edit", "error": "boom", "tool_input": {}}
    assert tool_failure_capture.capture(raw, "s", payload) == "no_table"
    raw.close()


def test_duplicate_within_window_deduped(tmp_path: Path) -> None:
    conn = _fresh(tmp_path)
    payload = {"tool_name": "Edit", "error": "same error", "tool_input": {"file_path": "a.py"}}
    assert tool_failure_capture.capture(conn, "s", payload) == "captured"
    assert tool_failure_capture.capture(conn, "s", payload) == "deduped"  # same hash, <60s
    conn.close()
