"""board_os workflow — the gates that decide whether a move is allowed.

Two independent layers, both evaluated before `transition` takes the write lock:

* **workflow policy** (config-driven) — ready label, dependency completion, and
  the in_progress→complete shortcut.
* **transition gates** (DoR / DoD) — validates the task *body* against the
  kind's rules via `transition_gates_validator`.

Both report through `GateOutcome` so the caller owns building the
`TransitionResult`; neither touches the database beyond a dependency read.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from board_os.config import READY_LABEL, WorkflowPolicy

from ._workflow_deps import incomplete_dependencies
from ._workflow_frontmatter import _extract_kind_from_frontmatter


@dataclass(frozen=True)
class GateOutcome:
    """Verdict of one gate layer: a block, or warnings plus audit metadata."""

    error: str | None = None
    error_category: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    skip_testing_warning: str | None = None
    override_reason: str | None = None
    override_actor: str | None = None

    @property
    def blocked(self) -> bool:
        return self.error is not None


def evaluate_policy_gates(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    current_status: str,
    to_status: str,
    current_labels: set[str],
    policy: WorkflowPolicy | None,
    bypass_gates: bool,
) -> GateOutcome:
    """Config-driven pull gates: ready label, dependency completion, testing hop."""
    # Ready hard-gate: a task must be deliberately marked `ready` before
    # it can be pulled from the backlog. icebox→in_progress is the only
    # pull edge; emergency→in_progress (the fast lane) stays exempt.
    if (
        policy is not None
        and policy.require_ready_label
        and not bypass_gates
        and current_status == "icebox"
        and to_status == "in_progress"
        and READY_LABEL not in current_labels
    ):
        return GateOutcome(
            error=(
                f"task not ready: add the '{READY_LABEL}' label before pulling "
                f"it into in_progress — `cos task-ready {task_id}` "
                f"(or escalate via emergency). Override: force=True."
            ),
            error_category="validation",
        )

    # Dependency gate: a task whose prerequisites are not yet complete cannot
    # be pulled. Same pull edge as the ready gate (icebox→in_progress);
    # emergency→in_progress (the fast lane) stays exempt so a fire never waits
    # on backlog. Category `transient` — the codebase's retryable-by-default
    # category (the canonical retryable "conflict" in the MCP envelope; a bare
    # `conflict` string is non-retryable here) — so the agent re-issues the
    # pull unchanged once the upstream task completes.
    if (
        policy is not None
        and policy.require_deps_complete
        and not bypass_gates
        and current_status == "icebox"
        and to_status == "in_progress"
    ):
        pending = incomplete_dependencies(conn, task_id)
        if pending:
            return GateOutcome(
                error=(
                    "blocked: prerequisites not complete: "
                    + ", ".join(pending)
                    + " — finish them or pass force=True"
                ),
                error_category="transient",
            )

    # Testing-before-complete gate: in_progress→complete must route
    # through `testing` so the verification choreography runs. The edge
    # stays legal in the state machine (testing→complete and forced
    # paths work); policy just blocks the shortcut.
    if current_status == "in_progress" and to_status == "complete":
        if policy is not None and policy.block_in_progress_to_complete and not bypass_gates:
            return GateOutcome(
                error=(
                    "must pass through testing: move in_progress→testing, run "
                    f"the verification matrix, then testing→complete — "
                    f"`cos task-move {task_id} --to testing`. Override: force=True."
                ),
                error_category="validation",
            )
        # config=None path (tests/migrations): keep the soft warning.
        return GateOutcome(
            skip_testing_warning=(
                "convention: in_progress→complete skipped 'testing' — "
                "Core Loop expects move-to-testing → run verification matrix → "
                "task-done. Legal but bypasses the gate; record verification in "
                "the work log if intentional."
            )
        )

    return GateOutcome()


def evaluate_transition_gates(
    *,
    task_id: str,
    to_status: str,
    target_file: Path | None,
    agent_session: str | None,
    bypass_gates: bool,
) -> GateOutcome:
    """DoR / DoD body gates. file_path=None (DB-only mode) skips the body gate."""
    if bypass_gates or target_file is None or to_status not in {"in_progress", "complete"}:
        return GateOutcome()

    gate_warnings: list[str] = []
    override_reason: str | None = None
    override_actor: str | None = None
    try:
        from board_os.transition_gates import (
            GatesConfigError,
            load_gates_config,
        )
        from board_os.transition_gates_validator import (
            validate_transition as _gate_validate,
        )

        if target_file.exists():
            body_text = target_file.read_text(encoding="utf-8")
            kind = _extract_kind_from_frontmatter(body_text) or "feature"
            # DoD inputs: read the .last-verify.json freshness signal
            # via the same helper the CLI uses (avoids drift).
            from board_os.transition_gates_cli import (
                _has_work_log_entries as _wl,
                _verify_state as _vs,
            )

            has_recent, age = _vs()
            has_work_log = _wl(body_text)

            gates_config = load_gates_config()
            gate_result = _gate_validate(
                task_id=task_id,
                kind=kind,
                body=body_text,
                new_status=to_status,
                config=gates_config,
                has_recent_verify=has_recent,
                verify_age_seconds=age,
                has_work_log=has_work_log,
                override_reason=os.environ.get("COS_OVERRIDE_REASON"),
                override_actor=os.environ.get("COS_AGENT") or agent_session,
                # Task files live at <root>/docs/tasks/<file>; the repo root is
                # three parents up. Passing it enables the Read First dead-link
                # check (WARN) — pure validator tests omit it and skip the stat.
                project_root=str(target_file.resolve().parent.parent.parent),
            )

            if gate_result.blocked:
                return GateOutcome(
                    error=(
                        "transition gate failed: "
                        + "; ".join(f"[{m.code}] {m.message}" for m in gate_result.messages)
                    ),
                    error_category="validation",
                )

            # PASS or WARN — collect override metadata for audit.
            for m in gate_result.messages:
                gate_warnings.append(f"[{m.code}] {m.message}")
            if any("[OVERRIDDEN]" in m.message for m in gate_result.messages):
                override_reason = os.environ.get("COS_OVERRIDE_REASON")
                override_actor = os.environ.get("COS_AGENT") or agent_session
    except GatesConfigError as exc:
        # Bad config — surface to retro reviewers but don't crash live work.
        gate_warnings.append(f"transition-gates config error (gate skipped): {exc}")
    except Exception as exc:
        gate_warnings.append(f"transition-gates internal error (skipped): {exc}")

    return GateOutcome(
        warnings=tuple(gate_warnings),
        override_reason=override_reason,
        override_actor=override_actor,
    )
