"""The review loop's dispatch side: every move to testing starts a review round.

Split from test_auto_dispatch_crossprovider.py, which keeps role selection,
budgets, usage capture and scope checks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src" / "core" / "hooks" / "_helpers"))

from test_auto_dispatch_crossprovider import _POLICY, HOOK


class TestBothMovesToTestingStartTheReview:
    """`cos task-move … --to testing` skipped review: only the MCP move fired it."""

    def _harness(self, tmp_path: Path) -> tuple[Path, Path]:
        hooks = tmp_path / "hooks"
        (hooks / "_helpers").mkdir(parents=True)
        hook = hooks / HOOK.name
        hook.write_text(HOOK.read_text(encoding="utf-8"), encoding="utf-8")
        (hooks / "cos-env.sh").write_text(
            "cos_read_stdin_bounded() { cat; }\n"
            "cos_current_session() { echo ses-test; }\n"
            "cos_resolve_python() { command -v python3; }\n",
            encoding="utf-8",
        )
        calls = tmp_path / "calls"
        (hooks / "_helpers" / "auto_dispatch.py").write_text(
            f"import sys\nopen({str(calls)!r}, 'a').write(sys.argv[1] + '\\n')\n",
            encoding="utf-8",
        )
        return hook, calls

    @pytest.mark.parametrize(
        ("payload", "task"),
        [
            (
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "cos task-move TASK-42 --to testing"},
                },
                "TASK-42",
            ),
            (
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "cd x && cos task-move TASK-42 --to=testing"},
                },
                "TASK-42",
            ),
            (
                {
                    "tool_name": "mcp__coding-os__cos_task_move",
                    "tool_input": {"task_id": "TASK-9", "to": "testing"},
                },
                "TASK-9",
            ),
            (
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": "cos task-move TASK-42 --to complete"},
                },
                None,
            ),
            ({"tool_name": "Bash", "tool_input": {"command": "git commit -m 'testing'"}}, None),
        ],
    )
    def test_dispatches_once_per_real_move(
        self, tmp_path: Path, payload: dict, task: str | None
    ) -> None:
        hook, calls = self._harness(tmp_path)

        subprocess.run(
            ["bash", str(hook)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=30,
            env={**os.environ, "COS_AGENT": "claude"},
            check=False,
        )
        deadline = time.time() + (5 if task else 0.5)
        while not calls.exists() and time.time() < deadline:
            time.sleep(0.05)

        assert (calls.read_text().split() if calls.exists() else []) == ([task] if task else [])


class TestEveryRoundGetsAReviewer:
    """Supervision decides who reviews, never whether the work is reviewed."""

    def _roles(
        self, policy: dict, session: str = "claude", security: bool = False
    ) -> list[tuple[str, str, str]]:
        from auto_dispatch import review_targets

        targets = review_targets(policy, session, security=security)
        return [(t["role"], t["adapter"], t["model"]) for t in targets]

    def test_supervision_off_reviews_on_the_sessions_own_adapter(self) -> None:
        assert self._roles({**_POLICY, "enabled": False}) == [("reviewer", "claude", "")]
        assert self._roles({}) == [("reviewer", "claude", "")]
        assert self._roles({}, security=True) == [
            ("reviewer", "claude", ""),
            ("security_auditor", "claude", ""),
        ]

    def test_supervision_on_keeps_the_pinned_reviewers(self) -> None:
        assert self._roles(_POLICY) == [("reviewer", "codex", "gpt-5.6-sol")]
        assert self._roles(_POLICY, security=True) == [
            ("reviewer", "codex", "gpt-5.6-sol"),
            ("security_auditor", "codex", "gpt-5.6-sol"),
        ]

    def test_a_same_provider_pin_picks_the_model_and_effort(self) -> None:
        from auto_dispatch import review_targets

        policy = {
            "enabled": True,
            "roles": {
                "reviewer": {"adapter": "claude", "model": "claude-sonnet-5", "effort": "high"},
                "security_auditor": {"adapter": "claude", "model": "claude-opus-5"},
            },
        }
        targets = review_targets(policy, "claude", security=True)
        assert [(t["role"], t["model"], t["effort"]) for t in targets] == [
            ("reviewer", "claude-sonnet-5", "high"),
            ("security_auditor", "claude-opus-5", ""),
        ]

    def test_a_model_id_in_the_adapter_slot_still_dispatches_nothing(self) -> None:
        assert self._roles({}, session="fable") == []


class TestEachRoundIsReviewedOnce:
    """A task back from rework is a new round; the same move fired twice is not."""

    def test_rework_opens_a_new_round_in_the_ledger(self, tmp_path: Path, monkeypatch) -> None:
        import sqlite3

        import auto_dispatch

        db = tmp_path / "coding-os.db"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE task_status_history (task_id TEXT, new_status TEXT)")
            conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("COS_PANEL_DIR", str(tmp_path))
        monkeypatch.setattr(auto_dispatch, "load_policy", lambda _dir: _POLICY)
        (tmp_path / ".last-verify.json").write_text(
            json.dumps({"board-os": {"status": "PASS", "ts": int(time.time())}}), encoding="utf-8"
        )
        contexts: list[dict] = []

        def fake_dispatch(target, _task, _session, _db, context=None):
            contexts.append(context or {})
            return {
                "role": target["role"],
                "status": "ok",
                "passed": False,
                "findings": ["medium: x"],
            }

        monkeypatch.setattr(auto_dispatch, "_dispatch_one", fake_dispatch)
        argv = ["auto_dispatch.py", "TASK-7", "ses-test", "claude"]

        auto_dispatch.main(argv)
        auto_dispatch.main(argv)
        with sqlite3.connect(db) as conn:
            conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
        auto_dispatch.main(argv)

        rows = [
            json.loads(line) for line in (tmp_path / "review-ledger.jsonl").read_text().splitlines()
        ]
        # No linked commits, so no security-sensitive diff: the reviewer alone.
        assert [(r["round"], r["role"], r["state"]) for r in rows] == [
            (round_no, "reviewer", state) for round_no in (1, 2) for state in ("running", "done")
        ]
        assert rows[1]["findings"] == ["medium: x"] and rows[1]["passed"] is False
        # Round 2 is handed round 1's findings so it checks those first.
        priors = [c.get("previous_review_findings", []) for c in contexts]
        assert priors == [[], ["medium: x"]]
        # Every round sees which suites the author ran: the reviewer cannot run them.
        assert all(c["verification_evidence"][0]["suite"] == "board-os" for c in contexts)

    def test_every_due_review_is_pending_before_the_first_runs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import sqlite3

        import auto_dispatch

        from board_os import review_security

        db = tmp_path / "coding-os.db"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE task_status_history (task_id TEXT, new_status TEXT)")
            conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("COS_PANEL_DIR", str(tmp_path))
        monkeypatch.setattr(auto_dispatch, "load_policy", lambda _dir: {})
        monkeypatch.setattr(review_security, "audit_digest", lambda *_a, **_k: "d1")
        ledger = tmp_path / "review-ledger.jsonl"
        seen_at_start: list[list[str]] = []

        def fake_dispatch(target, _task, _session, _db, context=None):
            seen_at_start.append(
                [json.loads(line)["state"] for line in ledger.read_text().splitlines()]
            )
            return {"role": target["role"], "status": "ok", "passed": True, "findings": []}

        monkeypatch.setattr(auto_dispatch, "_dispatch_one", fake_dispatch)

        auto_dispatch.main(["auto_dispatch.py", "TASK-7", "ses-test", "claude"])

        rows = [json.loads(line) for line in ledger.read_text().splitlines()]
        assert seen_at_start[0] == ["running", "running"]
        assert [(r["role"], r["state"]) for r in rows] == [
            ("reviewer", "running"),
            ("security_auditor", "running"),
            ("reviewer", "done"),
            ("security_auditor", "done"),
        ]
        assert rows[3]["digest"] == "d1" and "digest" not in rows[2]

    def test_a_malformed_verify_ledger_never_stops_the_review(self, tmp_path: Path) -> None:
        from auto_dispatch import review_context

        now = int(time.time())
        (tmp_path / ".last-verify.json").write_text(
            json.dumps(
                {
                    "board-os": {"status": "PASS", "ts": now},
                    "lint": {"status": "PASS", "ts": "yesterday"},
                    "stray": "not a run",
                }
            ),
            encoding="utf-8",
        )

        context = review_context(tmp_path, "TASK-7", 1)

        assert context["verification_evidence"] == [
            {"suite": "board-os", "status": "PASS", "ran_at": now}
        ]

    def test_a_long_review_is_kept_whole(self) -> None:
        from auto_dispatch import _verdict

        output = {
            "passed": False,
            "review_findings": [{"severity": "low", "detail": "d" * 250}] * 9,
        }

        passed, findings = _verdict(output)

        assert passed is False and len(findings) == 9
        assert findings[0] == "low: " + "d" * 250


def test_the_package_is_found_from_the_project_root_not_the_state_dir(tmp_path, monkeypatch):
    # COS_STATE_DIR may live outside the project (the Hub's ~/.coding-os); the task
    # files and git history are the project's.
    from auto_dispatch import review_context

    project = tmp_path / "project"
    (project / "docs" / "tasks").mkdir(parents=True)
    (project / "docs" / "tasks" / "TASK-7-demo.md").write_text(
        "## Acceptance\n- **Given** x\n", encoding="utf-8"
    )
    monkeypatch.setenv("COS_PROJECT_ROOT", str(project))

    context = review_context(tmp_path / "elsewhere", "TASK-7", 1)

    assert "**Given** x" in context["acceptance_criteria"]


def test_a_sensitive_commit_brings_the_auditor_once(tmp_path: Path, monkeypatch) -> None:
    # End to end through real git: task file -> linked commit -> digest -> targets.
    import sqlite3

    import auto_dispatch

    project, state = tmp_path / "project", tmp_path / "state"
    (project / "scripts").mkdir(parents=True)
    state.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
            cwd=project,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    (project / "scripts" / "deploy.sh").write_text("echo one\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "add the deploy script")
    sha = git("rev-parse", "--short", "HEAD")
    (project / "docs" / "tasks").mkdir(parents=True)
    (project / "docs" / "tasks" / "TASK-7-demo.md").write_text(
        f'---\ntitle: "demo"\n---\n## Work Log\n- commit {sha} — add the deploy script\n',
        encoding="utf-8",
    )
    db = state / "coding-os.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE task_status_history (task_id TEXT, new_status TEXT)")
        conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
    monkeypatch.setenv("COS_PROJECT_ROOT", str(project))
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    monkeypatch.setenv("COS_PANEL_DIR", str(state))
    monkeypatch.setattr(auto_dispatch, "load_policy", lambda _dir: {})
    ran: list[str] = []

    def fake_dispatch(target, _task, _session, _db, context=None):
        ran.append(target["role"])
        return {"role": target["role"], "status": "ok", "passed": True, "findings": []}

    monkeypatch.setattr(auto_dispatch, "_dispatch_one", fake_dispatch)
    argv = ["auto_dispatch.py", "TASK-7", "ses-test", "claude"]

    auto_dispatch.main(argv)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
    auto_dispatch.main(argv)

    # Round 2 changed nothing sensitive and round 1's audit passed, so the reviewer runs alone.
    assert ran == ["reviewer", "security_auditor", "reviewer"]


class TestReviewWeight:
    """An important change is reviewed on the session's model, a routine one stays cheap."""

    @staticmethod
    def _gate(tmp_path: Path, level: str) -> Path:
        (tmp_path / ".thinking_os-gate").write_text(f"ses-test {level} 3", encoding="utf-8")
        return tmp_path

    def test_the_gate_and_the_diff_decide_the_weight(self, tmp_path: Path) -> None:
        from auto_dispatch import review_weight

        assert review_weight(self._gate(tmp_path, "COMPLICATED"), False) == "COMPLICATED"
        assert review_weight(self._gate(tmp_path, "COMPLEX"), False) == "COMPLEX"
        assert review_weight(self._gate(tmp_path, "CHAOTIC"), False) == "COMPLEX"
        assert review_weight(self._gate(tmp_path, "CLEAR"), True) == "COMPLEX"
        assert review_weight(tmp_path / "no-panel", False) == "COMPLICATED"

    def test_a_weighty_review_runs_on_the_session_model_and_a_pin_still_wins(self) -> None:
        from auto_dispatch import review_targets, weighted

        unpinned = review_targets({}, "claude", security=True)
        heavy = weighted(unpinned, "COMPLEX", "claude", "claude-opus-5-5")
        assert [(t["model"], t["complexity"]) for t in heavy] == [
            ("claude-opus-5-5", "COMPLEX")
        ] * 2
        light = weighted(unpinned, "COMPLICATED", "claude", "claude-opus-5-5")
        assert [t["model"] for t in light] == ["", ""]
        unknown = weighted(unpinned, "COMPLEX", "claude", "")
        assert [t["model"] for t in unknown] == ["", ""]

        pinned = review_targets(_POLICY, "claude")
        assert weighted(pinned, "COMPLEX", "claude", "claude-opus-5-5")[0]["model"] == "gpt-5.6-sol"

    def test_main_dispatches_the_weighty_review_on_the_session_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import sqlite3

        import auto_dispatch

        with sqlite3.connect(tmp_path / "coding-os.db") as conn:
            conn.execute("CREATE TABLE task_status_history (task_id TEXT, new_status TEXT)")
            conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
        self._gate(tmp_path, "COMPLEX")
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("COS_PANEL_DIR", str(tmp_path))
        monkeypatch.setenv("COS_AGENT_MODEL", "claude-opus-5-5")
        monkeypatch.setattr(auto_dispatch, "load_policy", lambda _dir: {})
        sent: list[dict[str, str]] = []

        def fake_dispatch(
            target: dict[str, str], _task: str, _session: str, _db: str, context: object = None
        ) -> dict[str, object]:
            sent.append(target)
            return {"role": target["role"], "status": "ok", "passed": True, "findings": []}

        monkeypatch.setattr(auto_dispatch, "_dispatch_one", fake_dispatch)

        auto_dispatch.main(["auto_dispatch.py", "TASK-7", "ses-test", "claude"])

        assert [(t["role"], t["model"], t["complexity"]) for t in sent] == [
            ("reviewer", "claude-opus-5-5", "COMPLEX")
        ]


def test_a_weighty_review_gets_the_budget_its_model_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    # Opus at the Sonnet-sized budget died at 11 turns and at 120 s.
    import asyncio

    import auto_dispatch

    from thinking_os import dispatcher

    built: list[dispatcher.DispatchRequest] = []

    async def fake_dispatch(
        request: dispatcher.DispatchRequest, _db: str
    ) -> dispatcher.DispatchResult:
        built.append(request)
        return dispatcher.DispatchResult(formula_id=request.formula_id, status="error")

    monkeypatch.setattr(dispatcher, "dispatch_request", fake_dispatch)
    monkeypatch.setattr(asyncio, "run", _drive)
    target = {"role": "reviewer", "adapter": "claude", "model": "", "effort": "", "pinned": False}

    auto_dispatch._dispatch_one(
        {**target, "complexity": "COMPLICATED"}, "TASK-7", "ses", ":memory:"
    )
    auto_dispatch._dispatch_one({**target, "complexity": "COMPLEX"}, "TASK-7", "ses", ":memory:")

    from thinking_os.dispatcher_helpers import load_agent_prompt
    from thinking_os.tools._dispatch_request import _turn_budget

    light, heavy = built
    _body, meta = load_agent_prompt(light.agent_file)
    assert heavy.max_turns == 2 * (_turn_budget(meta, "full") or 0)
    assert light.max_turns == _turn_budget(meta, "standard")
    assert heavy.timeout_s == auto_dispatch.WEIGHTY_TIMEOUT_S and light.timeout_s < heavy.timeout_s


def _drive(coro):  # type: ignore[no-untyped-def]
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    raise AssertionError("fake dispatch awaited something")


class TestWhichModelReviews:
    def test_a_model_only_pin_is_a_pin(self) -> None:
        from auto_dispatch import review_targets, weighted

        policy = {"enabled": True, "roles": {"reviewer": {"model": "claude-sonnet-5-5"}}}
        target = review_targets(policy, "claude")[0]
        assert (target["adapter"], target["model"], target["pinned"]) == (
            "claude",
            "claude-sonnet-5-5",
            True,
        )
        assert weighted([target], "COMPLEX", "claude", "claude-opus-5-5")[0]["model"] == (
            "claude-sonnet-5-5"
        )

    def test_the_session_model_must_be_listed_and_no_weaker_than_sonnet(self) -> None:
        from auto_dispatch import session_review_model

        assert session_review_model("claude", "claude-opus-5-5") == "claude-opus-5-5"
        assert session_review_model("claude", "claude-haiku-5-5") == ""
        assert session_review_model("claude", "gpt-6.1-sol") == ""
        assert session_review_model("claude", "") == ""
        # Another provider's family is not ranked; its listed model qualifies.
        assert session_review_model("codex", "gpt-6.1-sol") == "gpt-6.1-sol"

    def test_only_the_level_token_weighs_never_the_justification(self, tmp_path: Path) -> None:
        from auto_dispatch import review_weight

        (tmp_path / ".thinking_os-gate").write_text(
            "ses-x CLEAR 1 nothing complex or chaotic here", encoding="utf-8"
        )
        assert review_weight(tmp_path, False) == "COMPLICATED"
