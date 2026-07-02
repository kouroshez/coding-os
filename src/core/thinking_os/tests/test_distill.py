"""Distillation path: fake-dispatcher minting, fallback, idempotency, adoption."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import distill
from database import init_db
from dispatcher import DispatchResult
from tools.learning import _mint_friction_lesson, _upsert_pattern


class StubDispatcher:
    name = "stub"

    def __init__(self, output_json: dict | None, status: str = "ok") -> None:
        self.calls = 0
        self.output_json = output_json or {}
        self.status = status

    def available(self) -> bool:
        return True

    async def dispatch(self, request) -> DispatchResult:
        self.calls += 1
        return DispatchResult(
            formula_id=request.formula_id,
            status=self.status,
            output_json=self.output_json,
            dispatcher_name="stub",
        )


class DownDispatcher(StubDispatcher):
    def available(self) -> bool:
        return False


GOOD_OUTPUT = {
    "situation": "creating a git worktree while the project is in trunk mode",
    "action": "inspect the branch read-only with git show branch:path instead",
    "why": "worktrees fork shared state that live symlinks propagate",
}


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = init_db(str(tmp_path / "test.db"))
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


def _mint(connection: sqlite3.Connection, state: dict | None) -> dict:
    return _mint_friction_lesson(
        connection,
        kind="hook_block",
        cluster_key="branch-guard:worktree-add",
        count=5,
        template_text=(
            "Recurring block (5 occurrences): branch-guard — worktree-add "
            "→ satisfy the blocked rule before retrying the action"
        ),
        hook="branch-guard",
        rule="worktree-add",
        samples=["git worktree add ../wt rule=worktree-add"],
        distill_state=state,
        concepts=json.dumps(["lesson", "hook_block", "branch-guard"]),
    )


def _row(connection: sqlite3.Connection, pattern_id: int) -> sqlite3.Row:
    return connection.execute(
        "SELECT * FROM learned_patterns WHERE id = ?", (pattern_id,)
    ).fetchone()


def test_distilled_lesson_minted(conn, monkeypatch) -> None:
    stub = StubDispatcher(GOOD_OUTPUT)
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)

    result = _mint(conn, {"remaining": 20})

    assert result["action"] == "created"
    row = _row(conn, result["id"])
    assert row["provenance"] == "llm_distilled"
    assert row["confidence"] == 0.5
    assert row["distill_fingerprint"]
    assert "worktree" in row["pattern"]
    assert "satisfy the blocked rule" not in row["pattern"]
    evidence = json.loads(row["evidence_json"])
    assert evidence["recurrences"] == 5
    assert evidence["samples"]
    assert stub.calls == 1


def test_fallback_template_when_dispatcher_down(conn, monkeypatch) -> None:
    stub = DownDispatcher(GOOD_OUTPUT)
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)
    monkeypatch.setattr(distill, "_adapter_scan", lambda: None)

    result = _mint(conn, {"remaining": 20})

    row = _row(conn, result["id"])
    assert "satisfy the blocked rule" in row["pattern"]
    assert row["provenance"] != "llm_distilled"
    assert row["distill_fingerprint"] is None
    assert stub.calls == 0


def test_fallback_template_on_schema_reject(conn, monkeypatch) -> None:
    stub = StubDispatcher({"situation": "x", "action": "y"})
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)

    result = _mint(conn, {"remaining": 20})

    row = _row(conn, result["id"])
    assert "satisfy the blocked rule" in row["pattern"]
    assert stub.calls == 1


def test_idempotent_second_run_makes_no_llm_call(conn, monkeypatch) -> None:
    stub = StubDispatcher(GOOD_OUTPUT)
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)

    first = _mint(conn, {"remaining": 20})
    second = _mint(conn, {"remaining": 20})

    assert stub.calls == 1
    assert second["id"] == first["id"]
    row = _row(conn, first["id"])
    assert row["times_validated"] >= 1


def test_budget_exhausted_falls_back_to_template(conn, monkeypatch) -> None:
    stub = StubDispatcher(GOOD_OUTPUT)
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)

    result = _mint(conn, {"remaining": 0})

    row = _row(conn, result["id"])
    assert "satisfy the blocked rule" in row["pattern"]
    assert stub.calls == 0


def test_legacy_template_row_adopted_and_archived(conn, monkeypatch) -> None:
    template = (
        "Recurring block (3 occurrences): branch-guard — worktree-add "
        "→ satisfy the blocked rule before retrying the action"
    )
    legacy = _upsert_pattern(
        conn,
        pattern=template,
        memory_type="lesson",
        domain=None,
        source="friction",
        confidence=0.6,
        concepts=json.dumps(["lesson", "hook_block", "branch-guard"]),
    )
    conn.execute(
        "UPDATE learned_patterns SET times_validated = 5, access_count = 7 WHERE id = ?",
        (legacy["id"],),
    )
    conn.commit()

    stub = StubDispatcher(GOOD_OUTPUT)
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)

    result = _mint(conn, {"remaining": 20})

    assert result["id"] != legacy["id"]
    new_row = _row(conn, result["id"])
    old_row = _row(conn, legacy["id"])
    assert new_row["times_validated"] >= 5
    assert new_row["access_count"] >= 7
    assert old_row["promoted_to"] == "archived"
    assert old_row["archived_at"] is not None


def test_promoted_lesson_leaves_suggest_and_survives_remine(conn, monkeypatch) -> None:
    from tools.learning import learn_suggest

    stub = StubDispatcher(GOOD_OUTPUT)
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)

    minted = _mint(conn, {"remaining": 20})
    conn.execute(
        "UPDATE learned_patterns SET promoted_to = 'rule:git-workflow.md', "
        "confidence = 0.8, times_validated = 4 WHERE id = ?",
        (minted["id"],),
    )
    conn.commit()

    suggested_ids = [s["id"] for s in learn_suggest(conn)["suggestions"]]
    assert minted["id"] not in suggested_ids

    _mint(conn, {"remaining": 20})
    row = _row(conn, minted["id"])
    assert row["promoted_to"] == "rule:git-workflow.md"


def test_archived_row_revives_on_remine(conn, monkeypatch) -> None:
    stub = StubDispatcher(GOOD_OUTPUT)
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)

    minted = _mint(conn, {"remaining": 20})
    conn.execute(
        "UPDATE learned_patterns SET promoted_to = 'archived', "
        "archived_at = CURRENT_TIMESTAMP WHERE id = ?",
        (minted["id"],),
    )
    conn.commit()

    _mint(conn, {"remaining": 20})
    row = _row(conn, minted["id"])
    assert row["promoted_to"] is None
    assert row["archived_at"] is None


def test_kill_switch_disables_distillation(conn, monkeypatch) -> None:
    stub = StubDispatcher(GOOD_OUTPUT)
    monkeypatch.setattr(distill, "get_dispatcher", lambda: stub)
    monkeypatch.setenv("COS_DISTILL_LLM", "0")

    result = _mint(conn, {"remaining": 20})

    row = _row(conn, result["id"])
    assert "satisfy the blocked rule" in row["pattern"]
    assert stub.calls == 0
