"""End-to-end persona coverage for the task system (Phase L.10).

Verifies that EVERY role persona can:
  1. create a task of the matching kind via cos_task_create
  2. see kind-appropriate next_steps in the response
  3. see kind-appropriate placeholders in the body
  4. validate the task (preflight) before transitioning
  5. transition through the full lifecycle: icebox → in_progress →
     testing → complete, with the gate firing at the right places.

Role ↔ kind mapping (from AGENTS.md + core/thinking_os/roles/):
  researcher       → spike
  analyst          → feature   (decomposition work uses feature kind)
  architect        → feature   (or refactor for component re-shape)
  documenter       → docs
  implementer      → feature   (or bug for fixes)
  reviewer         → (no specific kind — operates on others' tasks)
  debugger         → bug
  security_auditor → security
  deployer         → chore
  observer         → chore     (monitoring/runbooks)
  refactorer       → refactor

Plus: bug (universal — every implementer-style role files them).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from core.board_os import mcp_tools
from core.thinking_os import database as db

PERSONAS = [
    ("researcher", "spike", "Investigate whether kuzu can replace sqlite for graph layer."),
    ("analyst", "feature", "Add OAuth login flow that issues 24-hour JWT tokens with refresh."),
    (
        "architect",
        "refactor",
        "Extract retry logic into shared decorator with exponential backoff.",
    ),
    ("documenter", "docs", "Document the Phase L.10 override-audit policy in docs/governance/."),
    ("implementer", "bug", "Stop double-charging users on retry of failed payment webhook."),
    ("debugger", "bug", "Cover the OAuth refresh-token edge case at integration level."),
    ("deployer", "chore", "Bump dependency cryptography to v45 for security advisory."),
    ("security_auditor", "security", "Rotate all signing keys and tighten cookie SameSite policy."),
    (
        "refactorer",
        "refactor",
        "Collapse three duplicate auth middleware shims into one composable unit.",
    ),
]


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os" / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {
                "swimlanes": [{"id": "core", "label": "Core", "color": "#3b82f6"}],
                "wip_limits": {"in_progress": 5, "testing": 5, "emergency": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    return db.init_db(tmp_path / "coding-os.db")


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _fill_body_for_kind(file_path: Path, kind: str, outcome: str) -> None:
    """Replace placeholders with realistic, DoR-compliant content."""
    body = file_path.read_text(encoding="utf-8")
    # Outcome
    import re

    body = re.sub(
        r"\*\*Outcome \(one sentence\):\*\*\s*\(fill in[^\n]*",
        f"**Outcome (one sentence):** {outcome}",
        body,
    )
    # Read First (always render a real entry when section is present)
    body = body.replace(
        "- (no doc yet — exploratory)",
        "- [docs/phase-l10-plan.md](../phase-l10-plan.md)",
    )
    # Acceptance G/W/T (whenever present)
    body = body.replace(
        "- **Given** ...\n- **When** ...\n- **Then** ...",
        "- **Given** the gate is configured with kind-aware rules\n"
        "- **When** an agent transitions a filled task to in_progress\n"
        "- **Then** the validator returns PASS for this kind.",
    )
    # bug Repro Steps
    if kind == "bug":
        body = body.replace(
            "## Repro Steps\n"
            "1. (fill in: exact steps to reproduce)\n"
            "2. ...\n"
            "Expected: ...\n"
            "Actual: ...",
            "## Repro Steps\n"
            "1. Trigger payment with a card that 3DS-redirects.\n"
            "2. Force webhook retry by replaying the original event.\n"
            "Expected: idempotent — single charge.\n"
            "Actual: customer charged twice.",
        )
    # security Threat Model
    if kind == "security":
        body = body.replace(
            "## Threat Model\n(fill in: attacker, asset, attack vector, mitigation)",
            "## Threat Model\n"
            "Attacker: external; Asset: signing keys; Vector: leaked CI logs; "
            "Mitigation: rotation + scoped read-once secret store.",
        )
    file_path.write_text(body, encoding="utf-8")


def _validate(conn: sqlite3.Connection, project: Path, task_id: str, target: str):
    """Run the same validator the live gate uses, against this task's body."""
    from core.board_os.parser import extract_frontmatter
    from core.board_os.transition_gates import load_gates_config
    from core.board_os.transition_gates_validator import validate_transition

    row = conn.execute(
        "SELECT file_path, kind FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    body = (project / row[0]).read_text(encoding="utf-8")
    fm = extract_frontmatter(body) or {}
    return validate_transition(
        task_id=task_id,
        kind=str(fm["kind"]),
        body=body,
        new_status=target,
        config=load_gates_config(),
        has_recent_verify=(target == "complete"),
        verify_age_seconds=60,
        has_work_log=True,
    )


# ────────────────────────────────────────────────────────────────────
# Cross-persona walkthroughs
# ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "persona,kind,outcome", PERSONAS, ids=lambda x: x if isinstance(x, str) else ""
)
def test_persona_can_create_task_with_kind_aware_next_steps(
    project: Path,
    conn: sqlite3.Connection,
    persona: str,
    kind: str,
    outcome: str,
) -> None:
    """Every persona's typical kind produces a meaningful next_steps payload."""
    env = json.loads(
        mcp_tools.cos_task_create(
            conn,
            title=f"{persona}: {outcome[:30]}",
            swimlane="core",
            kind=kind,
        )
    )
    assert env["ok"] is True, f"{persona} create failed"
    ns = env["data"]["next_steps"]
    assert ns["kind"] == kind, f"{persona} next_steps kind mismatch"
    sections = [s["section"] for s in ns["required_for_in_progress"]]

    # Every persona must at minimum see Outcome required.
    assert "Outcome" in sections, f"{persona} missing Outcome requirement"

    # Spec-driven expectations per kind:
    if kind == "bug":
        assert "Repro Steps" in sections, f"{persona}/bug missing Repro Steps"
    elif kind == "security":
        assert "Threat Model" in sections, f"{persona}/security missing Threat Model"
    elif kind == "chore":
        assert sections == ["Outcome"], f"{persona}/chore should be lean: {sections}"
    elif kind == "spike":
        assert sections == ["Outcome"], f"{persona}/spike should be lean: {sections}"
    elif kind in ("feature", "refactor", "test", "docs"):
        # Feature, refactor, test all require Acceptance + Read First.
        # docs requires Read First but not Acceptance.
        assert "Read First" in sections, f"{persona}/{kind} missing Read First"


@pytest.mark.parametrize(
    "persona,kind,outcome", PERSONAS, ids=lambda x: x if isinstance(x, str) else ""
)
def test_persona_placeholder_blocks_then_filled_passes(
    project: Path,
    conn: sqlite3.Connection,
    persona: str,
    kind: str,
    outcome: str,
) -> None:
    """Round-trip: placeholder → BLOCK; filled body → PASS."""
    env = json.loads(
        mcp_tools.cos_task_create(
            conn,
            title=f"{persona} round-trip",
            swimlane="core",
            kind=kind,
        )
    )
    task_id = env["data"]["task_id"]
    file_path = project / env["data"]["file_path"]

    # Pre-fill verdict — every kind has at least Outcome with placeholder
    # text matching forbid_substrings, so all kinds must BLOCK pre-fill.
    pre = _validate(conn, project, task_id, "in_progress")
    assert pre.blocked, f"{persona}/{kind} should BLOCK pre-fill; got {pre.verdict}"

    # Fill the body
    _fill_body_for_kind(file_path, kind, outcome)

    # Post-fill verdict
    post = _validate(conn, project, task_id, "in_progress")
    assert post.verdict.value == "pass", (
        f"{persona}/{kind} should PASS post-fill; got "
        f"{[(m.code, m.message) for m in post.messages]}"
    )


@pytest.mark.parametrize(
    "persona,kind,outcome", PERSONAS, ids=lambda x: x if isinstance(x, str) else ""
)
def test_persona_full_lifecycle_to_complete(
    project: Path,
    conn: sqlite3.Connection,
    persona: str,
    kind: str,
    outcome: str,
) -> None:
    """Full lifecycle for each persona:
    icebox → in_progress (DoR gate) → testing → complete (DoD gate).
    """
    env = json.loads(
        mcp_tools.cos_task_create(
            conn,
            title=f"{persona} lifecycle",
            swimlane="core",
            kind=kind,
        )
    )
    task_id = env["data"]["task_id"]
    file_path = project / env["data"]["file_path"]
    _fill_body_for_kind(file_path, kind, outcome)

    # icebox → in_progress
    move_env = json.loads(
        mcp_tools.cos_task_move(
            conn,
            task_id=task_id,
            to="in_progress",
        )
    )
    assert move_env["ok"] is True, f"{persona}/{kind} icebox→in_progress failed: {move_env}"

    # in_progress → testing (no body gate today, so unconditional)
    move_env = json.loads(
        mcp_tools.cos_task_move(
            conn,
            task_id=task_id,
            to="testing",
        )
    )
    assert move_env["ok"] is True

    # testing → complete: DoD gate fires.
    # docs kind doesn't require verify, so it passes without recording one.
    # Other kinds require a recent verify — bypass for the test by force-DoD-only.
    if kind == "docs":
        move_env = json.loads(mcp_tools.cos_task_move(conn, task_id=task_id, to="complete"))
        assert move_env["ok"] is True, f"{persona}/docs complete failed: {move_env}"
    else:
        # Without verify, the gate must BLOCK.
        move_env = json.loads(mcp_tools.cos_task_move(conn, task_id=task_id, to="complete"))
        assert move_env["ok"] is False, f"{persona}/{kind} should BLOCK complete without verify"
        assert (
            "transition gate failed" in move_env["error"]["message"].lower()
            or "DOD_VERIFY_MISSING" in move_env["error"]["message"]
        )
        # Recording verify makes it pass — done via bypass_gates which lets
        # the workflow skip the gate entirely (test isolation).
        ok_env = json.loads(
            mcp_tools.cos_task_move(
                conn,
                task_id=task_id,
                to="complete",
                bypass_gates=True,
            )
        )
        assert ok_env["ok"] is True


# ────────────────────────────────────────────────────────────────────
# Reviewer + Releaser personas (operate on others' tasks)
# ────────────────────────────────────────────────────────────────────


def test_f6_reviewer_can_preview_any_task_via_validate(
    project: Path,
    conn: sqlite3.Connection,
) -> None:
    """F6 Reviewer's primary verb is preview — task-validate must work
    on any kind without modifying state."""
    for persona, kind, outcome in PERSONAS[:3]:  # sample
        env = json.loads(
            mcp_tools.cos_task_create(
                conn,
                title=f"{persona} reviewer",
                swimlane="core",
                kind=kind,
            )
        )
        task_id = env["data"]["task_id"]
        # Pre-fill: BLOCK
        pre = _validate(conn, project, task_id, "in_progress")
        assert pre.blocked
        # Status must NOT have changed
        row = conn.execute(
            "SELECT status FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        assert row[0] == "icebox", "preview must not change status"


def test_f8_releaser_audit_trail_on_override(
    project: Path,
    conn: sqlite3.Connection,
    monkeypatch,
) -> None:
    """F8 Releaser closes tasks. When a verify-skipped close is required,
    the override must land in task_status_history.override_reason."""
    env = json.loads(
        mcp_tools.cos_task_create(
            conn,
            title="F8 releaser audit",
            swimlane="core",
            kind="feature",
        )
    )
    task_id = env["data"]["task_id"]
    file_path = project / env["data"]["file_path"]
    _fill_body_for_kind(
        file_path,
        "feature",
        "Ship the new feature flag rollout to canary fleet.",
    )

    # Drive the lifecycle.
    mcp_tools.cos_task_move(conn, task_id=task_id, to="in_progress")
    mcp_tools.cos_task_move(conn, task_id=task_id, to="testing")

    # Set up override env vars
    monkeypatch.setenv("COS_VERIFY_OVERRIDE", "1")
    monkeypatch.setenv(
        "COS_OVERRIDE_REASON",
        "Hotfix INC-9999; verify ran locally on hot-patched build.",
    )
    monkeypatch.setenv("COS_AGENT", "claude")

    move_env = json.loads(mcp_tools.cos_task_move(conn, task_id=task_id, to="complete"))
    assert move_env["ok"] is True

    # Audit row must carry the override.
    row = conn.execute(
        "SELECT override_reason, override_actor FROM task_status_history "
        "WHERE task_id = ? AND new_status = 'complete'",
        (task_id,),
    ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert "INC-9999" in row[0]
    assert row[1] == "claude"
