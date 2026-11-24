"""Which model reviews a testing round: task weight, policy, session model, budget.

Split from test_auto_dispatch_review_rounds.py, which keeps the round mechanics.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src" / "core" / "hooks" / "_helpers"))

from test_auto_dispatch_crossprovider import _POLICY


class TestReviewWeight:
    """An important change is reviewed on the session's model, a routine one stays cheap."""

    @staticmethod
    def _gate(tmp_path: Path, level: str) -> Path:
        (tmp_path / ".thinking_os-gate").write_text(f"ses-test {level} 3", encoding="utf-8")
        return tmp_path

    def test_the_gate_and_the_diff_decide_the_weight(self, tmp_path: Path) -> None:
        from review_model import review_weight

        assert review_weight(self._gate(tmp_path, "COMPLICATED"), False) == "COMPLICATED"
        assert review_weight(self._gate(tmp_path, "COMPLEX"), False) == "COMPLEX"
        assert review_weight(self._gate(tmp_path, "CHAOTIC"), False) == "COMPLEX"
        assert review_weight(self._gate(tmp_path, "CLEAR"), True) == "COMPLEX"
        assert review_weight(tmp_path / "no-panel", False) == "COMPLICATED"

    def test_a_weighty_review_runs_on_the_session_model_and_a_pin_still_wins(self) -> None:
        from auto_dispatch import review_targets
        from review_model import weighted

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
        from auto_dispatch import review_targets
        from review_model import weighted

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
        from review_model import session_review_model

        assert session_review_model("claude", "claude-opus-5-5") == "claude-opus-5-5"
        assert session_review_model("claude", "claude-haiku-5-5") == ""
        assert session_review_model("claude", "gpt-6.1-sol") == ""
        assert session_review_model("claude", "") == ""
        # A model of unknown strength never stands in for the role's tier.
        assert session_review_model("codex", "gpt-6.1-sol") == ""

    def test_only_the_level_token_weighs_never_the_justification(self, tmp_path: Path) -> None:
        from review_model import review_weight

        (tmp_path / ".thinking_os-gate").write_text(
            "ses-x CLEAR 1 nothing complex or chaotic here", encoding="utf-8"
        )
        assert review_weight(tmp_path, False) == "COMPLICATED"


class TestPolicyDecidesWhenRoutingIsOn:
    def _run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: dict[str, object]
    ) -> list[dict[str, str]]:
        import sqlite3

        import auto_dispatch

        with sqlite3.connect(tmp_path / "coding-os.db") as conn:
            conn.execute("CREATE TABLE task_status_history (task_id TEXT, new_status TEXT)")
            conn.execute("INSERT INTO task_status_history VALUES ('TASK-7', 'testing')")
        (tmp_path / ".thinking_os-gate").write_text("ses-test COMPLEX 3", encoding="utf-8")
        monkeypatch.setenv("COS_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("COS_PANEL_DIR", str(tmp_path))
        monkeypatch.setenv("COS_AGENT_MODEL", "claude-opus-5-5")
        monkeypatch.setattr(auto_dispatch, "load_policy", lambda _dir: policy)
        sent: list[dict[str, str]] = []

        def fake_dispatch(
            target: dict[str, str], _task: str, _session: str, _db: str, context: object = None
        ) -> dict[str, object]:
            sent.append(target)
            return {"role": target["role"], "status": "ok", "passed": True, "findings": []}

        monkeypatch.setattr(auto_dispatch, "_dispatch_one", fake_dispatch)
        auto_dispatch.main(["auto_dispatch.py", "TASK-7", "ses-test", "claude"])
        return sent

    def test_routing_off_reviews_on_the_session_model_at_high(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        sent = self._run(tmp_path, monkeypatch, {})
        assert [(t["model"], t["effort"]) for t in sent] == [("claude-opus-5-5", "high")]

    def test_routing_on_leaves_the_model_to_the_hub(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        # The orchestrator default is the Hub's choice; the session model must not replace it.
        sent = self._run(tmp_path, monkeypatch, {"enabled": True, "mode": "explicit"})
        assert [(t["model"], t["effort"]) for t in sent] == [("", "")]

    def test_a_pin_below_the_adaptive_gate_is_ignored(self, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        policy = {
            "enabled": True,
            "mode": "adaptive",
            "complexity_threshold": "CHAOTIC",
            "roles": {"reviewer": {"model": "claude-haiku-5-5"}},
        }
        sent = self._run(tmp_path, monkeypatch, policy)
        assert [t["model"] for t in sent] == ["claude-opus-5-5"]
