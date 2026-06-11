"""Regression tests for the TASK-059 workflow-integrity hooks.

Covers the three new hooks behaviourally (subprocess + synthetic stdin),
including the allow-list / override paths that were only manually smoke-tested
during implementation:
  - enforce-task-transition.sh — BLOCKs status/checkbox transitions on
    docs/tasks/**, allow-listed for governance tasks and
    COS_ALLOW_TASK_EDIT=1.
  - sync-task-current.sh — auto-writes .task-current on task -> in_progress.
  - nudge-task-discovery.sh — warns on raw docs/tasks reads, emits prompt nudge.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "src" / "core" / "hooks"


def _run(hook: str, payload: dict, panel: Path, env: dict | None = None):
    e = dict(os.environ)
    e.update(
        {
            "COS_STATE_DIR": str(panel.parents[1]),
            "COS_AGENT_DIR": str(panel.parents[0]),
            "COS_PANEL_DIR": str(panel),
            "COS_PANEL_ID": panel.name,
            "COS_AGENT": "claude",
        }
    )
    if env:
        e.update(env)
    proc = subprocess.run(
        ["bash", str(HOOKS / hook)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=20,
        env=e,
    )
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def _panel(tmp_path: Path, task_current: str | None = None, sid: str = "sx") -> Path:
    panel = tmp_path / "claude" / "panels" / "p"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text(sid + "\n", encoding="utf-8")
    if task_current is not None:
        (panel / ".task-current").write_text(f"{sid} {task_current}\n", encoding="utf-8")
    return panel


class TestEnforceTaskTransition:
    H = "enforce-task-transition.sh"

    def test_blocks_status_change(self, tmp_path):
        panel = _panel(tmp_path, task_current="TASK-1")
        rc, _, err = _run(
            self.H,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "docs/tasks/TASK-1-x.md",
                    "old_string": "status: in_progress",
                    "new_string": "status: complete",
                },
            },
            panel,
        )
        assert rc == 2
        assert "BLOCKED" in err

    def test_blocks_checkbox_tick(self, tmp_path):
        panel = _panel(tmp_path, task_current="TASK-1")
        rc, _, _ = _run(
            self.H,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "docs/tasks/TASK-1-x.md",
                    "old_string": "- [ ] acceptance item",
                    "new_string": "- [x] acceptance item",
                },
            },
            panel,
        )
        assert rc == 2

    def test_allows_worklog_edit(self, tmp_path):
        panel = _panel(tmp_path, task_current="TASK-1")
        rc, _, _ = _run(
            self.H,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "docs/tasks/TASK-1-x.md",
                    "old_string": "## Work Log",
                    "new_string": "## Work Log\n- 2026-06-02 note",
                },
            },
            panel,
        )
        assert rc == 0

    def test_allows_non_task_file(self, tmp_path):
        panel = _panel(tmp_path, task_current="TASK-1")
        rc, _, _ = _run(
            self.H,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "src/core/foo.py",
                    "old_string": "status: in_progress",
                    "new_string": "status: complete",
                },
            },
            panel,
        )
        assert rc == 0

    def test_allows_with_override_env(self, tmp_path):
        panel = _panel(tmp_path, task_current="TASK-1")
        rc, _, _ = _run(
            self.H,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "docs/tasks/TASK-1-x.md",
                    "old_string": "status: in_progress",
                    "new_string": "status: complete",
                },
            },
            panel,
            env={"COS_ALLOW_TASK_EDIT": "1"},
        )
        assert rc == 0

    def test_allows_governance_task(self, tmp_path):
        panel = _panel(tmp_path, task_current="governance-docs-update")
        rc, _, _ = _run(
            self.H,
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "docs/tasks/TASK-1-x.md",
                    "old_string": "status: in_progress",
                    "new_string": "status: complete",
                },
            },
            panel,
        )
        assert rc == 0

class TestSyncTaskCurrent:
    H = "sync-task-current.sh"

    def test_writes_on_mcp_in_progress(self, tmp_path):
        panel = _panel(tmp_path)
        rc, _, _ = _run(
            self.H,
            {
                "tool_name": "mcp__coding-os__cos_task_move",
                "tool_input": {"task_id": "TASK-7", "to": "in_progress"},
            },
            panel,
        )
        assert rc == 0
        assert (panel / ".task-current").read_text(encoding="utf-8").strip().endswith("TASK-7")

    def test_writes_on_bash_task_start(self, tmp_path):
        panel = _panel(tmp_path)
        _run(
            self.H, {"tool_name": "Bash", "tool_input": {"command": "cos task-start TASK-8"}}, panel
        )
        assert (panel / ".task-current").read_text(encoding="utf-8").strip().endswith("TASK-8")

    def test_no_write_on_complete(self, tmp_path):
        panel = _panel(tmp_path)
        _run(
            self.H,
            {
                "tool_name": "mcp__coding-os__cos_task_move",
                "tool_input": {"task_id": "TASK-7", "to": "complete"},
            },
            panel,
        )
        assert not (panel / ".task-current").exists()

    def test_no_write_on_unrelated_bash(self, tmp_path):
        panel = _panel(tmp_path)
        _run(self.H, {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, panel)
        assert not (panel / ".task-current").exists()


class TestNudgeTaskDiscovery:
    H = "nudge-task-discovery.sh"

    def test_bash_leg_warns_on_docs_tasks_read(self, tmp_path):
        panel = _panel(tmp_path)
        rc, _, err = _run(
            self.H,
            {"tool_name": "Bash", "tool_input": {"command": "ls docs/tasks/ | grep 058"}},
            panel,
        )
        assert rc == 0
        assert "task nudge" in err

    def test_bash_leg_silent_on_cos_task_show(self, tmp_path):
        panel = _panel(tmp_path)
        rc, _, err = _run(
            self.H,
            {"tool_name": "Bash", "tool_input": {"command": "cos task-show TASK-058"}},
            panel,
        )
        assert rc == 0
        assert "task nudge" not in err

    def test_prompt_leg_emits_additional_context(self, tmp_path):
        panel = _panel(tmp_path)
        rc, out, _ = _run(self.H, {"prompt": "check task TASK-058 please"}, panel)
        assert rc == 0
        assert "additionalContext" in out

    def test_bash_leg_warns_on_broadened_readers(self, tmp_path):
        # A3: awk/sed/rg etc. now trigger the warning too. Each
        # reader needs its own panel — the bash leg is debounced once/session.
        for i, cmd in enumerate(
            (
                "rg 058 docs/tasks/",
                "sed -n 1p docs/tasks/TASK-1.md",
                "awk '{print}' docs/tasks/x.md",
            )
        ):
            panel = tmp_path / f"claude{i}" / "panels" / "p"
            panel.mkdir(parents=True)
            (panel / "session-id").write_text("sx\n", encoding="utf-8")
            rc, _, err = _run(self.H, {"tool_name": "Bash", "tool_input": {"command": cmd}}, panel)
            assert rc == 0
            assert "task nudge" in err, cmd

    def test_read_leg_warns_on_docs_tasks_read(self, tmp_path):
        # A3: a raw Read of docs/tasks/** warns (never blocks).
        panel = _panel(tmp_path)
        rc, _, err = _run(
            self.H,
            {"tool_name": "Read", "tool_input": {"file_path": "docs/tasks/TASK-058-x.md"}},
            panel,
        )
        assert rc == 0
        assert "task nudge" in err

    def test_read_leg_silent_on_non_task_file(self, tmp_path):
        panel = _panel(tmp_path)
        rc, _, err = _run(
            self.H,
            {"tool_name": "Read", "tool_input": {"file_path": "src/core/foo.py"}},
            panel,
        )
        assert rc == 0
        assert "task nudge" not in err


