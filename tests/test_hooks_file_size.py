"""The write-time half of the file-size ceiling (anti-overengineering.md § 6).

`block-bad-patterns.sh` is the one PreToolUse Write|Edit mechanism that already
rejects code anti-patterns, so the ceiling rides it rather than adding a hook
(Raptor § component consolidation). The asymmetry these tests pin down is the
point: authoring an oversized file is blocked, shrinking one never is — a gate
that deadlocked its own burndown would be uninstalled within a week.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "src" / "core" / "hooks" / "block-bad-patterns.sh"
CEILING = 800


def _invoke(payload: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        env=full_env,
    )


def _lines(count: int) -> str:
    return "\n".join(f"value_{i} = {i}" for i in range(count))


def _write(path: str, count: int) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": _lines(count)}}


class TestWriteCeiling:
    def test_blocks_a_new_file_over_the_ceiling(self, tmp_path: Path) -> None:
        result = _invoke(_write(str(tmp_path / "fresh.py"), CEILING + 100))
        assert result.returncode == 2
        assert f"{CEILING + 100} lines" in result.stderr
        assert str(CEILING) in result.stderr

    def test_allows_a_file_exactly_at_the_ceiling(self, tmp_path: Path) -> None:
        assert _invoke(_write(str(tmp_path / "exact.py"), CEILING)).returncode == 0

    def test_allows_shrinking_an_already_oversized_file(self, tmp_path: Path) -> None:
        target = tmp_path / "legacy.py"
        target.write_text(_lines(CEILING + 500))
        # Still over the ceiling, but smaller than before: this is the split
        # itself, and blocking it would make the debt unpayable.
        result = _invoke(_write(str(target), CEILING + 100))
        assert result.returncode == 0

    def test_blocks_growing_an_already_oversized_file(self, tmp_path: Path) -> None:
        target = tmp_path / "legacy.py"
        target.write_text(_lines(CEILING + 100))
        assert _invoke(_write(str(target), CEILING + 300)).returncode == 2

    def test_ceiling_is_overridable_for_projects_with_a_different_standard(
        self, tmp_path: Path
    ) -> None:
        payload = _write(str(tmp_path / "fresh.py"), 300)
        assert _invoke(payload, env={"COS_MAX_FILE_LINES": "200"}).returncode == 2


class TestExemptions:
    def test_ignores_downstream_owned_scaffold_files(self, tmp_path: Path) -> None:
        path = str(tmp_path / "src" / "templates" / "python" / "scaffold" / "big.py")
        assert _invoke(_write(path, CEILING + 400)).returncode == 0

    def test_ignores_generated_and_vendored_trees(self, tmp_path: Path) -> None:
        for segment in ("node_modules", "vendor", "migrations", "dist"):
            path = str(tmp_path / segment / "big.py")
            assert _invoke(_write(path, CEILING + 400)).returncode == 0, segment

    def test_ignores_non_source_files(self, tmp_path: Path) -> None:
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / "data.json"), "content": _lines(5000)},
        }
        assert _invoke(payload).returncode == 0


class TestEditWarning:
    def test_warns_without_blocking_when_an_edit_grows_an_oversized_file(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "legacy.py"
        target.write_text(_lines(CEILING + 400))
        result = _invoke(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(target),
                    "old_string": "value_1 = 1",
                    "new_string": "value_1 = 1\nvalue_1b = 2",
                },
            }
        )
        assert result.returncode == 0
        assert "grows it" in result.stderr

    def test_stays_quiet_when_an_edit_shrinks_an_oversized_file(self, tmp_path: Path) -> None:
        target = tmp_path / "legacy.py"
        target.write_text(_lines(CEILING + 400))
        result = _invoke(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(target),
                    "old_string": "value_1 = 1\nvalue_2 = 2",
                    "new_string": "value_1 = 1",
                },
            }
        )
        assert result.returncode == 0
        assert "grows it" not in result.stderr
