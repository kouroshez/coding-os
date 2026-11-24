"""A review on the session's own runtime runs as its native subagent.

The operator could not see a detached SDK review: it surfaced only as a pulse line
after it finished. These tests pin the hand-off — the move to testing asks the
agent for the subagent, SubagentStart hands it the package, SubagentStop writes
the verdict — and the fallbacks that keep every round reviewed.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src" / "core" / "hooks" / "_helpers"))

import auto_dispatch
import native_review

from board_os import review_gate
from test_auto_dispatch_crossprovider import _POLICY

HOOK = _ROOT / "src" / "adapters" / "claude" / "hooks" / "native-review-subagent.sh"


def _git(project: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def world(tmp_path: Path, monkeypatch) -> dict:
    project, state = tmp_path / "project", tmp_path / "state"
    (project / "src").mkdir(parents=True)
    state.mkdir()
    _git(project, "init", "-q")
    (project / "src" / "app.py").write_text("print('one')\n", encoding="utf-8")
    _git(project, "add", ".")
    _git(project, "commit", "-qm", "add the app")
    sha = _git(project, "rev-parse", "--short", "HEAD")
    (project / "docs" / "tasks").mkdir(parents=True)
    (project / "docs" / "tasks" / "TASK-7-demo.md").write_text(
        '---\ntitle: "Print one"\n---\n# TASK-7\n\n'
        "**Outcome (one sentence):** The app prints one.\n\n"
        "## Acceptance (G/W/T)\n- **Given** the app **When** run **Then** it prints one\n\n"
        f"## Work Log\n- commit {sha} — add the app\n",
        encoding="utf-8",
    )
    agents = project / ".claude" / "agents"
    agents.mkdir(parents=True)
    for name in ("cos-reviewer", "cos-security-auditor"):
        (agents / f"{name}.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    with sqlite3.connect(state / "coding-os.db") as conn:
        conn.execute("CREATE TABLE task_status_history (task_id TEXT, new_status TEXT)")
        conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
    (state / ".last-verify.json").write_text(
        json.dumps({"board-os": {"status": "PASS", "ts": int(time.time())}}), encoding="utf-8"
    )
    monkeypatch.setenv("COS_PROJECT_ROOT", str(project))
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    monkeypatch.setenv("COS_PANEL_DIR", str(state))
    monkeypatch.setenv("COS_AGENT_MODEL", "claude-opus-5-5")
    monkeypatch.setattr(auto_dispatch, "load_policy", lambda _dir: {})
    detached: list[str] = []

    def fake_dispatch(target, _task, _session, _db, context=None):
        detached.append(f"{target['role']}@{target['adapter']}")
        return {"role": target["role"], "status": "ok", "passed": True, "findings": []}

    monkeypatch.setattr(auto_dispatch, "_dispatch_one", fake_dispatch)
    return {"project": project, "state": state, "detached": detached}


def _rows(state: Path) -> list[dict]:
    return [json.loads(line) for line in (state / "review-ledger.jsonl").read_text().splitlines()]


def _context(output: str) -> str:
    return json.loads(output)["hookSpecificOutput"]["additionalContext"]


class TestTheMoveToTestingAsksForTheSubagent:
    def test_a_routine_review_is_a_sonnet_subagent_and_nothing_runs_detached(self, world) -> None:
        text = _context(native_review.plan("TASK-7", "claude"))
        auto_dispatch.main(["auto_dispatch.py", "TASK-7", "ses", "claude"])

        assert 'Agent(subagent_type="cos-reviewer", model="sonnet")' in text
        assert review_gate.BOARD_EVENTS_HEADER in text
        assert "🔎 TASK-7 review ready — reviewer runs as subagent cos-reviewer" in text
        assert world["detached"] == []
        rows = _rows(world["state"])
        assert [(r["role"], r["state"], r["adapter"]) for r in rows] == [
            ("reviewer", "running", "claude")
        ]
        assert rows[0]["native"] == 'Agent(subagent_type="cos-reviewer", model="sonnet")'

    def test_a_weighty_review_inherits_the_sessions_model(self, world) -> None:
        (world["state"] / ".thinking_os-gate").write_text("ses COMPLEX 3 why", encoding="utf-8")

        text = _context(native_review.plan("TASK-7", "claude"))

        assert 'Agent(subagent_type="cos-reviewer")' in text
        assert "model=" not in text

    def test_the_same_move_seen_twice_asks_once(self, world) -> None:
        assert native_review.plan("TASK-7", "claude")
        assert native_review.plan("TASK-7", "claude") == ""
        assert len(_rows(world["state"])) == 1

    def test_a_project_without_the_definition_keeps_the_detached_review(self, world) -> None:
        for definition in (world["project"] / ".claude" / "agents").iterdir():
            definition.unlink()

        text = _context(native_review.plan("TASK-7", "claude"))
        auto_dispatch.main(["auto_dispatch.py", "TASK-7", "ses", "claude"])

        assert "🛰️ TASK-7 review started — reviewer@claude (its default model)" in text
        assert "Agent(" not in text
        assert world["detached"] == ["reviewer@claude"]

    def test_a_codex_pinned_review_runs_detached_and_says_so(self, world, monkeypatch) -> None:
        monkeypatch.setattr(auto_dispatch, "load_policy", lambda _dir: _POLICY)

        text = _context(native_review.plan("TASK-7", "claude"))
        auto_dispatch.main(["auto_dispatch.py", "TASK-7", "ses", "claude"])

        assert "🛰️ TASK-7 review started — reviewer@codex (gpt-5.6-sol)" in text
        assert "Agent(" not in text
        assert world["detached"] == ["reviewer@codex"]

    def test_a_codex_session_has_no_native_agent(self, world) -> None:
        text = _context(native_review.plan("TASK-7", "codex"))

        assert "🛰️ TASK-7 review started — reviewer@codex" in text
        assert "Agent(" not in text


class TestTheGateRepeatsTheCallUntilTheSubagentStarts:
    def test_pending_names_the_call_then_waits_once_started(self, world) -> None:
        ledger = world["state"] / "review-ledger.jsonl"
        native_review.plan("TASK-7", "claude")

        before = review_gate.verdict("TASK-7", 1, path=ledger)
        code, blocks, detail = review_gate.dod_review_outcome(before)
        assert (code, blocks) == ("DOD_REVIEW_PENDING", True)
        assert 'start it now with Agent(subagent_type="cos-reviewer", model="sonnet")' in detail

        native_review.start({"agent_type": "cos-reviewer", "agent_id": "a1"})
        after = review_gate.verdict("TASK-7", 1, path=ledger)
        assert after.pending == ("reviewer@claude",) and after.start == ()
        assert "still running" in review_gate.dod_review_outcome(after)[2]

    def test_a_request_nobody_starts_ends_as_the_stale_warning(self, world) -> None:
        native_review.plan("TASK-7", "claude")

        late = int(time.time()) + review_gate.STALE_AFTER_SECONDS + 1
        stale = review_gate.verdict(
            "TASK-7", 1, path=world["state"] / "review-ledger.jsonl", now=late
        )

        assert stale.line() == "⚠️ TASK-7 closing without review — reviewer@claude could not run"


class TestSubagentStartHandsOverThePackage:
    def test_the_context_holds_the_whole_package(self, world) -> None:
        native_review.plan("TASK-7", "claude")

        text = _context(native_review.start({"agent_type": "cos-reviewer", "agent_id": "a1"}))

        for expected in (
            "Print one",
            "The app prints one.",
            "it prints one",
            "add the app",
            "+print('one')",
            "board-os",
        ):
            assert expected in text
        package = world["state"] / "review-packages" / "TASK-7-r1-reviewer.md"
        assert str(package) in text
        assert "ReviewerOutput" in package.read_text(encoding="utf-8")

    def test_round_two_carries_round_ones_findings(self, world) -> None:
        state = world["state"]
        review_gate.record(
            "TASK-7", 1, "reviewer", "claude", state="done", findings=["high: x"], passed=False
        )
        with sqlite3.connect(state / "coding-os.db") as conn:
            conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
        native_review.plan("TASK-7", "claude")

        text = _context(native_review.start({"agent_type": "cos-reviewer", "agent_id": "a2"}))

        assert "previous_review_findings" in text and "high: x" in text

    def test_a_large_diff_stays_under_the_hook_cap(self, world) -> None:
        project = world["project"]
        (project / "src" / "app.py").write_text("x = 1\n" * 5000, encoding="utf-8")
        _git(project, "commit", "-qam", "grow the app")
        sha = _git(project, "rev-parse", "--short", "HEAD")
        task = project / "docs" / "tasks" / "TASK-7-demo.md"
        task.write_text(task.read_text() + f"- commit {sha} — grow the app\n", encoding="utf-8")
        native_review.plan("TASK-7", "claude")

        text = _context(native_review.start({"agent_type": "cos-reviewer", "agent_id": "a1"}))

        assert len(text) < 10_000
        assert "The app prints one." in text and "characters; in" in text

    def test_a_subagent_nobody_asked_for_gets_nothing(self, world) -> None:
        assert native_review.start({"agent_type": "cos-reviewer", "agent_id": "a1"}) == ""


class TestSubagentStopRecordsTheVerdict:
    def _started(self, agent_id: str = "a1") -> None:
        native_review.plan("TASK-7", "claude")
        native_review.start({"agent_type": "cos-reviewer", "agent_id": agent_id})

    def test_the_findings_reach_the_ledger_from_the_subagents_own_message(self, world) -> None:
        self._started()
        output = {
            "passed": False,
            "review_findings": [{"severity": "high", "file": "src/app.py", "detail": "no test"}],
        }

        native_review.stop(
            {
                "agent_type": "cos-reviewer",
                "agent_id": "a1",
                "last_assistant_message": f"Done.\n```json\n{json.dumps(output)}\n```",
            }
        )

        done = _rows(world["state"])[-1]
        assert (done["state"], done["passed"]) == ("done", False)
        assert done["findings"] == ["high: src/app.py — no test"]
        gate = review_gate.verdict("TASK-7", 1, path=world["state"] / "review-ledger.jsonl")
        assert review_gate.dod_review_outcome(gate)[0] == "DOD_REVIEW_FINDINGS"

    def test_a_clean_review_lets_the_task_close(self, world) -> None:
        self._started()

        native_review.stop(
            {
                "agent_type": "cos-reviewer",
                "agent_id": "a1",
                "last_assistant_message": '{"passed": true, "review_findings": []}',
            }
        )

        gate = review_gate.verdict("TASK-7", 1, path=world["state"] / "review-ledger.jsonl")
        assert gate.line() is None

    def test_a_message_without_json_is_an_error_not_a_pass(self, world) -> None:
        self._started()

        native_review.stop(
            {"agent_type": "cos-reviewer", "agent_id": "a1", "last_assistant_message": "LGTM"}
        )

        assert _rows(world["state"])[-1]["state"] == "error"
        gate = review_gate.verdict("TASK-7", 1, path=world["state"] / "review-ledger.jsonl")
        assert gate.skipped.endswith("reviewer@claude could not run")

    def test_a_subagent_that_never_claimed_a_request_records_nothing(self, world) -> None:
        native_review.plan("TASK-7", "claude")

        native_review.stop(
            {"agent_type": "cos-reviewer", "agent_id": "zz", "last_assistant_message": "{}"}
        )

        assert [r["state"] for r in _rows(world["state"])] == ["running"]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ('{"passed": true}', {"passed": True}),
        ('Here it is:\n```json\n{"passed": false}\n```', {"passed": False}),
        (
            'Summary first. {"passed": true, "review_findings": []} trailing',
            {"passed": True, "review_findings": []},
        ),
        ("no json at all", None),
        ("[1, 2]", None),
    ],
)
def test_parse_output(message: str, expected: dict | None) -> None:
    assert native_review.parse_output(message) == expected


def test_the_hook_passes_start_and_stop_to_the_helper(tmp_path: Path) -> None:
    hooks = tmp_path / "adapters" / "claude" / "hooks"
    helpers = tmp_path / "core" / "hooks" / "_helpers"
    hooks.mkdir(parents=True)
    helpers.mkdir(parents=True)
    hook = hooks / HOOK.name
    hook.write_text(HOOK.read_text(encoding="utf-8"), encoding="utf-8")
    (hooks / "cos-env.sh").write_text(
        "cos_read_stdin_bounded() { cat; }\ncos_resolve_python() { command -v python3; }\n",
        encoding="utf-8",
    )
    calls = tmp_path / "calls"
    (helpers / "native_review.py").write_text(
        f"import sys\nopen({str(calls)!r}, 'a').write(sys.argv[1] + '\\n')\n"
        "print('{\"ok\": 1}')\n",
        encoding="utf-8",
    )
    outputs = []
    for event in ("SubagentStart", "SubagentStop", "Stop"):
        proc = subprocess.run(
            ["bash", str(hook)],
            input=json.dumps({"hook_event_name": event, "agent_type": "cos-reviewer"}).encode(),
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 0
        outputs.append(proc.stdout.decode().strip())

    assert calls.read_text().split() == ["start", "stop"]
    assert outputs == ['{"ok": 1}', '{"ok": 1}', ""]
