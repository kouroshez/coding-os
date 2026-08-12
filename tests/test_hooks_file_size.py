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
CEILING = 500
WARN_AT = 400
NOTICE_AT = 300


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

    def test_warns_without_blocking_between_the_warn_tier_and_the_ceiling(
        self, tmp_path: Path
    ) -> None:
        result = _invoke(_write(str(tmp_path / "growing.py"), WARN_AT + 50))
        assert result.returncode == 0
        assert "is now" in result.stderr

    def test_stays_quiet_below_the_warn_tier(self, tmp_path: Path) -> None:
        result = _invoke(_write(str(tmp_path / "small.py"), WARN_AT - 50))
        assert result.returncode == 0
        assert "is now" not in result.stderr

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


class TestPreferredBudgetNotice:
    """300 is the documented preferred budget; 400/500 were the only tiers the
    hook implemented, so the number an agent reads was never the number it felt.
    The notice fires on the CROSSING only — 241 of this repo's 1060 sources are
    already past 300, and a tier that re-fires forever is one agents scroll past.
    """

    def test_notices_a_new_file_crossing_the_preferred_budget(self, tmp_path: Path) -> None:
        result = _invoke(_write(str(tmp_path / "fresh.py"), NOTICE_AT + 20))
        assert result.returncode == 0
        assert f"crosses {NOTICE_AT} lines" in result.stderr

    def test_stays_quiet_under_the_preferred_budget(self, tmp_path: Path) -> None:
        result = _invoke(_write(str(tmp_path / "small.py"), NOTICE_AT - 20))
        assert result.returncode == 0
        assert "crosses" not in result.stderr

    def test_does_not_re_notice_a_file_already_over_the_budget(self, tmp_path: Path) -> None:
        # The no-nag guarantee: the seam question is asked once, when it is cheap.
        target = tmp_path / "already_big.py"
        target.write_text(_lines(NOTICE_AT + 50))
        result = _invoke(_write(str(target), NOTICE_AT + 80))
        assert result.returncode == 0
        assert "crosses" not in result.stderr

    def test_the_warn_tier_supersedes_the_notice(self, tmp_path: Path) -> None:
        result = _invoke(_write(str(tmp_path / "big.py"), WARN_AT + 30))
        assert result.returncode == 0
        assert "crosses" not in result.stderr
        assert "is now" in result.stderr

    def test_the_budget_is_overridable_per_project(self, tmp_path: Path) -> None:
        result = _invoke(
            _write(str(tmp_path / "fresh.py"), NOTICE_AT - 20),
            env={"COS_NOTICE_FILE_LINES": str(NOTICE_AT - 100)},
        )
        assert result.returncode == 0
        assert f"crosses {NOTICE_AT - 100} lines" in result.stderr


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


def _source_write(path: str, source: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": source}}


class TestRuntimeCostWarning:
    """Critical Rule 27 rides the same hook, one tier softer.

    Complexity cannot be proven statically, so every finding here warns and
    none blocks: a false BLOCK on a legitimate small-n loop is how a gate
    gets routed around, and then it protects nothing at all.
    """

    def test_warns_on_io_inside_a_loop(self, tmp_path: Path) -> None:
        source = "def render(tasks):\n    for task in tasks:\n        database.execute(task)\n"
        result = _invoke(_source_write(str(tmp_path / "n_plus_one.py"), source))
        assert result.returncode == 0
        assert "N+1" in result.stderr

    def test_warns_on_list_membership_inside_a_loop(self, tmp_path: Path) -> None:
        source = (
            "def filter_new(incoming, existing):\n"
            "    known = list(existing)\n"
            "    for item in incoming:\n"
            "        if item in known:\n"
            "            continue\n"
        )
        result = _invoke(_source_write(str(tmp_path / "quadratic.py"), source))
        assert result.returncode == 0
        assert "scans" in result.stderr

    def test_warns_on_string_concatenation_inside_a_loop(self, tmp_path: Path) -> None:
        source = 'def report(rows):\n    out = ""\n    for row in rows:\n        out += f"{row}"\n'
        result = _invoke(_source_write(str(tmp_path / "concat.py"), source))
        assert result.returncode == 0
        assert "accumulator" in result.stderr

    def test_stays_quiet_on_the_batched_rewrite_of_the_same_logic(self, tmp_path: Path) -> None:
        source = (
            "def render(tasks, existing):\n"
            "    known = set(existing)\n"
            "    rows = database.fetch_all(tasks)\n"
            '    return "".join(f"{row}" for row in rows if row.key in known)\n'
        )
        result = _invoke(_source_write(str(tmp_path / "batched.py"), source))
        assert result.returncode == 0
        assert "Runtime-cost" not in result.stderr

    def test_never_blocks_even_when_every_shape_is_present(self, tmp_path: Path) -> None:
        source = (
            "def render(tasks, existing):\n"
            "    known = list(existing)\n"
            '    out = ""\n'
            "    for task in tasks:\n"
            "        row = database.execute(task)\n"
            "        if row in known:\n"
            '            out += f"{row}"\n'
        )
        assert _invoke(_source_write(str(tmp_path / "all_three.py"), source)).returncode == 0

    def test_ignores_non_python_sources(self, tmp_path: Path) -> None:
        source = "for (const task of tasks) { db.execute(task); }\n"
        result = _invoke(_source_write(str(tmp_path / "loop.ts"), source))
        assert "Runtime-cost" not in result.stderr

    def test_survives_syntactically_invalid_python(self, tmp_path: Path) -> None:
        source = "def broken(:\n    for x in y:\n        db.execute(x)\n"
        result = _invoke(_source_write(str(tmp_path / "broken.py"), source))
        assert result.returncode == 0
        assert "Runtime-cost" not in result.stderr
