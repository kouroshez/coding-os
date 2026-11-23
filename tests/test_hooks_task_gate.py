"""Task gate: a code edit runs under this session's in_progress task.

Contract: docs/engineering/task-mode-matrix.md § Task enforcement is not a mode
decision. Each hook runs as a subprocess with synthetic stdin, like Claude Code.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOKS = REPO / "src" / "core" / "hooks"
SUBAGENT_HOOK = REPO / "src" / "adapters" / "claude" / "hooks" / "inject-subagent-task.sh"
SID = "ses-claude-gate"


def _project(tmp_path: Path, tasks: dict[str, str] | None = None, config: str = "") -> Path:
    project = tmp_path / "proj"
    (project / "docs" / "tasks").mkdir(parents=True)
    for task_id, status in (tasks or {}).items():
        (project / "docs" / "tasks" / f"{task_id}-demo.md").write_text(
            f'---\nid: {task_id}\ntitle: "demo \\u2014 work"\nstatus: {status}\n---\n\n'
            "## Read First\n- docs/spec.md\n\n## Work Log\n",
            encoding="utf-8",
        )
    if config:
        (project / ".coding-os.yaml").write_text(config, encoding="utf-8")
    return project


def _panel(tmp_path: Path, *, task: str = "", mode: str = "", gate: str = "") -> Path:
    panel = tmp_path / "state" / "claude" / "panels" / "p"
    panel.mkdir(parents=True)
    (panel / "session-id").write_text(SID + "\n", encoding="utf-8")
    for name, value in ((".task-current", task), (".thinking_os-gate", gate)):
        if value:
            (panel / name).write_text(f"{SID} {value}\n", encoding="utf-8")
    if mode:
        (panel / ".task-mode").write_text(mode + "\n", encoding="utf-8")
    return panel


def _run(script: Path, payload: dict, panel: Path, project: Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env.update(
        {
            "COS_STATE_DIR": str(panel.parents[1]),
            "COS_AGENT_DIR": str(panel.parents[0]),
            "COS_PANEL_DIR": str(panel),
            "COS_PANEL_ID": panel.name,
            "COS_AGENT": "claude",
            "COS_PROJECT_ROOT": str(project),
        }
    )
    proc = subprocess.run(
        ["bash", str(script)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=20,
        env=env,
        cwd=project,
    )
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def _edit(path: str) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": path}}


class TestEnforceTaskStart:
    H = HOOKS / "enforce-task-start.sh"

    def test_a_query_turn_still_needs_a_task(self, tmp_path):
        project = _project(tmp_path)
        code, _, err = _run(self.H, _edit("src/main.go"), _panel(tmp_path, mode="query"), project)
        assert code == 2
        assert "No in_progress task" in err

    def test_clear1_excuses_a_trivial_edit_outside_implementation(self, tmp_path):
        panel = _panel(tmp_path, mode="chore", gate="CLEAR 1 typo")
        assert _run(self.H, _edit("src/main.go"), panel, _project(tmp_path))[0] == 0

    def test_clear1_is_refused_for_an_implementation_prompt(self, tmp_path):
        panel = _panel(tmp_path, mode="propose-formal", gate="CLEAR 1 typo")
        code, _, err = _run(self.H, _edit("src/main.go"), panel, _project(tmp_path))
        assert code == 2
        assert "CLEAR 1 gate does not apply" in err

    def test_the_in_progress_task_lets_the_edit_through(self, tmp_path):
        project = _project(tmp_path, {"TASK-7": "in_progress"})
        panel = _panel(tmp_path, task="TASK-7", mode="formal")
        assert _run(self.H, _edit("src/app.py"), panel, project)[0] == 0

    def test_a_task_in_testing_no_longer_counts(self, tmp_path):
        project = _project(tmp_path, {"TASK-7": "testing"})
        panel = _panel(tmp_path, task="TASK-7", mode="formal")
        code, _, err = _run(self.H, _edit("src/app.py"), panel, project)
        assert code == 2
        assert "cos task-move TASK-7 --to in_progress" in err

    def test_a_marker_naming_no_real_task_blocks(self, tmp_path):
        panel = _panel(tmp_path, task="TASK-404", mode="formal")
        assert _run(self.H, _edit("src/app.py"), panel, _project(tmp_path))[0] == 2

    def test_project_code_extensions_add_to_the_builtin_list(self, tmp_path):
        project = _project(tmp_path, config="code_extensions:\n  - lua\n")
        panel = _panel(tmp_path, mode="query")
        assert _run(self.H, _edit("src/game.lua"), panel, project)[0] == 2
        assert _run(self.H, _edit("src/app.swift"), panel, project)[0] == 2
        assert _run(self.H, _edit("notes.txt"), panel, project)[0] == 0


class TestClassifyTaskModeSticky:
    H = HOOKS / "classify-task-mode.sh"

    def _mode(self, prompt: str, panel: Path, project: Path) -> str:
        _run(self.H, {"prompt": prompt}, panel, project)
        return (panel / ".task-mode").read_text(encoding="utf-8").strip()

    def test_a_short_follow_up_keeps_the_implementation_mode(self, tmp_path):
        panel, project = _panel(tmp_path), _project(tmp_path)
        assert (
            self._mode("implement retry logic in the uploader", panel, project) == "propose-formal"
        )
        assert self._mode("ok, go ahead", panel, project) == "propose-formal"
        assert self._mode("اره ادامه بده", panel, project) == "propose-formal"

    def test_a_question_resets_the_mode(self, tmp_path):
        panel, project = _panel(tmp_path), _project(tmp_path)
        self._mode("fix the login bug", panel, project)
        assert self._mode("why is the login slow?", panel, project) == "query"


class TestDocAnchorNamesTheActiveTask:
    H = HOOKS / "enforce-doc-anchor.sh"

    def _anchored(self, tmp_path: Path, anchor: str, task: str, tasks: dict) -> int:
        project = _project(tmp_path, tasks)
        panel = _panel(tmp_path, task=task, mode="formal")
        (panel / ".doc-anchor").write_text(f"{SID} {anchor}\n", encoding="utf-8")
        return _run(self.H, _edit("src/app.py"), panel, project)[0]

    def test_an_anchor_for_another_task_blocks(self, tmp_path):
        tasks = {"TASK-7": "complete", "TASK-8": "in_progress"}
        assert self._anchored(tmp_path, "task:TASK-7", "TASK-8", tasks) == 2

    def test_an_anchor_for_the_active_task_passes(self, tmp_path):
        assert self._anchored(tmp_path, "task:TASK-8", "TASK-8", {"TASK-8": "in_progress"}) == 0

    def test_a_non_task_name_without_a_doc_path_blocks(self, tmp_path):
        assert self._anchored(tmp_path, "task:anything", "TASK-8", {"TASK-8": "in_progress"}) == 2


class TestClassifyPromptGetsThePanel:
    H = HOOKS / "inject-mcp-caller-session.sh"

    def test_agent_dir_is_injected(self, tmp_path):
        panel = _panel(tmp_path)
        payload = {
            "tool_name": "mcp__coding-os__cos_classify_prompt",
            "tool_input": {"prompt": "fix it"},
        }
        code, out, _ = _run(self.H, payload, panel, _project(tmp_path))
        assert code == 0
        updated = json.loads(out)["hookSpecificOutput"]["updatedInput"]
        assert updated == {"prompt": "fix it", "agent_dir": str(panel)}
        assert "agent_session" not in updated


class TestSyncTaskCurrentClearing:
    H = HOOKS / "sync-task-current.sh"

    def _move(self, tmp_path: Path, marker: str, task_id: str, to: str) -> bool:
        panel = _panel(tmp_path, task=marker)
        payload = {
            "tool_name": "mcp__coding-os__cos_task_move",
            "tool_input": {"task_id": task_id, "to": to},
        }
        _run(self.H, payload, panel, _project(tmp_path))
        return (panel / ".task-current").exists()

    def test_finishing_task_1_keeps_a_marker_for_task_12(self, tmp_path):
        assert self._move(tmp_path, "TASK-12", "TASK-1", "complete") is True

    def test_archive_clears_the_marker(self, tmp_path):
        assert self._move(tmp_path, "TASK-12", "TASK-12", "archive") is False

    def _bash(self, tmp_path: Path, command: str) -> str:
        panel = _panel(tmp_path)
        project = _project(tmp_path, {"TASK-5": "in_progress", "TASK-6": "icebox"})
        _run(self.H, {"tool_name": "Bash", "tool_input": {"command": command}}, panel, project)
        marker = panel / ".task-current"
        return marker.read_text(encoding="utf-8").split()[-1] if marker.exists() else ""

    def test_a_chained_task_start_binds_the_panel(self, tmp_path):
        assert self._bash(tmp_path, "cd repo && cos task-start TASK-5") == "TASK-5"

    def test_a_move_the_board_rejected_does_not_bind(self, tmp_path):
        assert self._bash(tmp_path, "cos task-start TASK-6") == ""

    def test_text_that_only_mentions_a_task_start_does_not(self, tmp_path):
        assert self._bash(tmp_path, "printf 'cos task-start TASK-5' | head") == ""


class TestSubagentStart:
    def _context(self, tmp_path: Path, task: str, tasks: dict) -> str:
        project = _project(tmp_path, tasks)
        panel = _panel(tmp_path, task=task)
        code, out, _ = _run(SUBAGENT_HOOK, {"agent_type": "Explore"}, panel, project)
        assert code == 0
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def test_the_subagent_learns_the_active_task(self, tmp_path):
        context = self._context(tmp_path, "TASK-7", {"TASK-7": "in_progress"})
        assert "TASK-7 (in_progress): demo — work" in context
        assert "Read First: docs/spec.md." in context

    def test_without_a_task_the_subagent_is_told_edits_are_blocked(self, tmp_path):
        assert "no in_progress task" in self._context(tmp_path, "", {})
