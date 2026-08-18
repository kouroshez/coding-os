"""shared_context — a dispatched child is told which task it serves (TASK-1012).

A child inherits no parent conversation. Codex dispatch additionally runs
--sandbox read-only with mcp_servers={}, so it cannot look anything up: the
prompt is its only channel. A role that does not know its task still answers
confidently, and the envelope cannot tell that apart from a grounded answer.
"""

from __future__ import annotations

from thinking_os.dispatcher import DispatchRequest
from thinking_os.dispatcher_helpers import render_shared_context

_CONTEXT = {
    "task_id": "TASK-1012",
    "title": "Make supervision spend and context visible",
    "status": "in_progress",
    "recent_work_log": ["added adapter dimension", "added doctor check"],
}


class TestRenderer:
    def test_empty_context_renders_nothing(self) -> None:
        assert render_shared_context({}) == ""
        assert render_shared_context(None) == ""

    def test_renders_task_identity_and_work_log(self) -> None:
        out = render_shared_context(_CONTEXT)
        assert "TASK-1012" in out
        assert "Make supervision spend and context visible" in out
        assert "in_progress" in out
        assert "added adapter dimension" in out

    def test_states_the_child_inherits_no_conversation(self) -> None:
        # The instruction to declare missing context is the anti-hallucination
        # half; without it the child fills gaps silently.
        assert "inherit no prior conversation" in render_shared_context(_CONTEXT)

    def test_work_log_is_capped(self) -> None:
        out = render_shared_context({**_CONTEXT, "recent_work_log": [f"e{i}" for i in range(20)]})
        assert out.count("\n  - ") == 5

    def test_survives_a_malformed_work_log(self) -> None:
        out = render_shared_context({**_CONTEXT, "recent_work_log": "not-a-list"})
        assert "TASK-1012" in out


class TestContract:
    def test_dispatch_request_defaults_to_empty(self) -> None:
        req = DispatchRequest(formula_id="reviewer", agent_file="x.md", prompt="p")
        assert req.shared_context == {}

    def test_dispatch_request_carries_context(self) -> None:
        req = DispatchRequest(
            formula_id="reviewer", agent_file="x.md", prompt="p", shared_context=_CONTEXT
        )
        assert req.shared_context["task_id"] == "TASK-1012"


class TestBothAdaptersCarryIt:
    """Adapter-neutral: neither runtime may be the one that drops the context."""

    def test_codex_prompt_includes_it(self) -> None:
        from adapters.codex.sdk_dispatcher import _dispatch_context

        req = DispatchRequest(
            formula_id="reviewer", agent_file="x.md", prompt="p", shared_context=_CONTEXT
        )
        assert "TASK-1012" in _dispatch_context(req)

    def test_claude_prompt_includes_it(self) -> None:
        from adapters.claude._claude_sdk_options import _formula_prompts

        req = DispatchRequest(
            formula_id="reviewer", agent_file="x.md", prompt="p", shared_context=_CONTEXT
        )
        _system, user_prompt = _formula_prompts(req, "body")
        assert "TASK-1012" in user_prompt

    def test_both_render_identical_context_text(self) -> None:
        # One renderer, so the two runtimes cannot drift apart.
        from adapters.claude._claude_sdk_options import _formula_prompts
        from adapters.codex.sdk_dispatcher import _dispatch_context

        req = DispatchRequest(
            formula_id="reviewer", agent_file="x.md", prompt="p", shared_context=_CONTEXT
        )
        block = render_shared_context(_CONTEXT)
        assert block in _dispatch_context(req)
        assert block in _formula_prompts(req, "body")[1]


class TestShardedContextQuery:
    """_shared_context against a real tasks table — the renderer tests above
    never exercised the query that feeds it."""

    def _db(self, tmp_path, rows):
        import sqlite3

        db = tmp_path / "coding-os.db"
        with sqlite3.connect(db) as conn:
            conn.execute(
                "CREATE TABLE tasks (task_id TEXT, title TEXT, status TEXT, "
                "agent_session TEXT, updated_at TEXT, work_log_last_5 TEXT)"
            )
            conn.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?)", rows)
        return db

    def test_picks_the_in_progress_task(self, tmp_path) -> None:
        from thinking_os.tools._dispatch_request import _shared_context

        db = self._db(
            tmp_path,
            [("TASK-9", "Ship it", "in_progress", "ses-a", "2026-08-18", '["did a thing"]')],
        )
        ctx = _shared_context("ses-a", db)
        assert ctx["task_id"] == "TASK-9"
        assert ctx["title"] == "Ship it"
        assert ctx["recent_work_log"] == ["did a thing"]

    def test_prefers_this_sessions_task_over_another(self, tmp_path) -> None:
        from thinking_os.tools._dispatch_request import _shared_context

        db = self._db(
            tmp_path,
            [
                ("TASK-OTHER", "Theirs", "in_progress", "ses-b", "2026-08-18", "[]"),
                ("TASK-MINE", "Mine", "in_progress", "ses-a", "2026-08-01", "[]"),
            ],
        )
        # Newer row belongs to another session; ours must still win.
        assert _shared_context("ses-a", db)["task_id"] == "TASK-MINE"

    def test_empty_when_nothing_is_active(self, tmp_path) -> None:
        from thinking_os.tools._dispatch_request import _shared_context

        db = self._db(tmp_path, [("TASK-1", "Done", "complete", "ses-a", "2026-08-18", "[]")])
        assert _shared_context("ses-a", db) == {}

    def test_survives_a_missing_database(self, tmp_path) -> None:
        from thinking_os.tools._dispatch_request import _shared_context

        assert _shared_context("ses-a", tmp_path / "nope.db") == {}

    def test_survives_malformed_work_log_json(self, tmp_path) -> None:
        from thinking_os.tools._dispatch_request import _shared_context

        db = self._db(
            tmp_path, [("TASK-9", "T", "testing", "ses-a", "2026-08-18", "{not json")]
        )
        assert _shared_context("ses-a", db)["recent_work_log"] == []
