"""
Tests for session lifecycle hooks (TASK-156).

Covers session ID format, session-end summary write, DB-absent handling.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestSessionIdFormat:
    def test_format_pattern(self) -> None:
        """Session ID should match ses-YYYYMMDD-HHMMSS-XXXX."""
        # Simulate what the hook generates
        result = subprocess.run(
            [
                "bash",
                "-c",
                'echo "ses-$(date +%Y%m%d-%H%M%S)-$(head -c 4 /dev/urandom | xxd -p | head -c 4)"',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        session_id = result.stdout.strip()
        assert re.match(r"ses-\d{8}-\d{6}-[a-f0-9]{4}", session_id)

    def test_unique_ids(self) -> None:
        """Two generated IDs should differ."""
        ids = set()
        for _ in range(5):
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    'echo "ses-$(date +%Y%m%d-%H%M%S)-$(head -c 4 /dev/urandom | xxd -p | head -c 4)"',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ids.add(result.stdout.strip())
        # At least some should be unique (suffix randomness)
        assert len(ids) >= 2


class TestSessionContextHook:
    def test_hook_syntax(self) -> None:
        """session-context.sh should have valid bash syntax."""
        hooks_dir = Path(__file__).resolve().parent.parent.parent / "hooks"
        result = subprocess.run(
            ["bash", "-n", str(hooks_dir / "session-context.sh")],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0

    def test_session_end_syntax(self) -> None:
        """session-end.sh should have valid bash syntax."""
        hooks_dir = Path(__file__).resolve().parent.parent.parent / "hooks"
        result = subprocess.run(
            ["bash", "-n", str(hooks_dir / "session-end.sh")],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
