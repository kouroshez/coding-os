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
