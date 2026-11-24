"""Start the review of a task's testing round: the reviewer, plus the security auditor when due.

A target the session's own runtime can run as a native subagent is left to
native_review.py, which the same hook runs first.

Only the review roles run here: dispatching every role pinned to another provider
would start nine Claude roles for one move from a Codex session under the default
pins. Supervision picks where each review runs; every round is reviewed either way.

Runs detached from the hook: one codex dispatch measured 123s, and a PostToolUse
hook holding the tool call open that long would be worse than no trigger.
Contract: docs/engineering/agent-supervision.md § When dispatch fires by itself.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[3]
for _path in (_SRC / "core", _SRC, _SRC / "core" / "thinking_os"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from review_model import (
    WEIGHTY_TIMEOUT_S,
    review_weight,
    routed,
    session_review_model,
    weighted,
)
from review_verdict import cited_paths, parse_verdict, scope_verdict

from board_os.review_security import AUDITOR

logger = logging.getLogger(__name__)


def load_policy(state_dir: Path) -> dict:
    try:
        raw = json.loads((state_dir / "hub-settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    policy = raw.get("model_routing")
    return policy if isinstance(policy, dict) else {}


def known_adapters() -> set[str]:
    try:
        return {p.name for p in (_SRC / "adapters").iterdir() if (p / "adapter.yaml").is_file()}
    except OSError:
        return set()


REVIEW_ROLES = ("reviewer", AUDITOR)


def review_targets(
    policy: dict[str, Any], session_adapter: str, *, security: bool = False
) -> list[dict[str, Any]]:
    roles = policy.get("roles") if policy.get("enabled") else None
    roles = roles if isinstance(roles, dict) else {}
    adapters = known_adapters()

    def known(adapter: str) -> bool:
        # `fable` is a MODEL inside the claude adapter; a model id in an adapter
        # slot names nowhere to dispatch, so it is never guessed at.
        return bool(adapter) and (not adapters or adapter in adapters)

    targets = []
    for role in REVIEW_ROLES if security else REVIEW_ROLES[:1]:
        pin = roles.get(role)
        pin = pin if isinstance(pin, dict) else {}
        pinned = str(pin.get("adapter") or "").strip()
        model, effort = str(pin.get("model") or ""), str(pin.get("effort") or "")
        if known(pinned):
            # Effort is carried verbatim: an adapter without effort_selection
            # rejects a pinned one, so the policy is where codex keeps it empty.
            targets.append(
                {"role": role, "adapter": pinned, "model": model, "effort": effort, "pinned": True}
            )
        elif known(session_adapter):
            # A pin naming only a model is a pin too; one naming an unknown
            # adapter carries a model from a catalog the session does not have.
            own = not pinned
            targets.append(
                {
                    "role": role,
                    "adapter": session_adapter,
                    "model": model if own else "",
                    "effort": effort if own else "",
                    "pinned": own and bool(model),
                }
            )
    return targets


def adapter_timeout(adapter: str) -> float | None:
    """Wall-clock budget the adapter declares, or None to use the agent default.

    Role timeouts are calibrated on Claude (44-53s measured). Codex is materially
    slower — a successful review measured 123s against a 120s agent default and
    timed out at the finish line — so the budget is a per-adapter fact, declared
    in the descriptor rather than branched on here.
    """
    try:
        import yaml

        descriptor = _SRC / "adapters" / adapter / "adapter.yaml"
        data = yaml.safe_load(descriptor.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    declared = data.get("dispatch_timeout_s")
    return float(declared) if isinstance(declared, (int, float)) else None


def seen(marker: Path, key: str) -> bool:
    try:
        return key in marker.read_text(encoding="utf-8").split("\n")
    except OSError:
        return False


def remember(marker: Path, key: str) -> None:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open("a", encoding="utf-8") as handle:
            handle.write(key + "\n")
    except OSError:
        pass


def append_json(results_file: Path, payload: dict) -> None:
    try:
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with results_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError:
        pass


def _git_lines(project: Path, *args: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(project), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _task_files(task_id: str, db_path: str) -> set[str]:
    # What changed while the task ran: files in commits since it started plus
    # the working tree's changes. An empty set means "unknown" — the caller
    # treats unknown as no claim to test, never as a failed scope.
    if not task_id:
        return set()
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5) as conn:
            row = conn.execute(
                "SELECT started_at FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
    except sqlite3.Error:
        return set()
    if not row or not row[0]:
        return set()
    state_dir = Path(db_path).resolve().parent
    project = state_dir.parent if state_dir.name == ".coding-os" else state_dir
    committed = _git_lines(
        project, "log", f"--since=@{int(row[0])}", "--name-only", "--pretty=format:"
    )
    return {*committed, *_git_lines(project, "diff", "--name-only", "HEAD")}


VERIFY_EVIDENCE_SECONDS = 2 * 60 * 60


def review_context(state_dir: Path, task_id: str, round_no: int) -> dict:
    # The reviewer cannot run git: it reviews exactly the diff and criteria it is handed.
    from _paths import resolve_project_root

    from board_os import review_gate

    context: dict = review_gate.review_package(task_id, resolve_project_root())
    if round_no > 1:
        # A re-review checks these first instead of hunting afresh (reviewer.md).
        prior = review_gate.verdict(task_id, round_no - 1).findings
        context["previous_review_findings"] = list(prior)
    # The reviewer cannot run commands; without this it re-reports every suite it
    # could not run as an open finding, round after round.
    try:
        ledger = json.loads((state_dir / ".last-verify.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ledger = {}
    cutoff = time.time() - VERIFY_EVIDENCE_SECONDS
    evidence = []
    for suite, run in ledger.items() if isinstance(ledger, dict) else ():
        ran_at = run.get("ts") if isinstance(run, dict) else None
        # A hand-edited ledger must not stop the review from starting.
        if isinstance(ran_at, (int, float)) and ran_at >= cutoff:
            evidence.append({"suite": suite, "status": run.get("status"), "ran_at": int(ran_at)})
    if evidence:
        context["verification_evidence"] = evidence
    return context


def _dispatch_one(
    target: dict, task_id: str, session_id: str, db_path: str, context: dict | None = None
) -> dict:
    import asyncio

    from thinking_os import dispatcher as _disp
    from thinking_os.tools._dispatch_persistence import _persist_dispatch_output
    from thinking_os.tools._dispatch_request import _build_dispatch_request

    role = target["role"]
    complexity = target.get("complexity") or "COMPLICATED"
    weighty = complexity == "COMPLEX"
    timeout = adapter_timeout(target["adapter"])
    request = _build_dispatch_request(
        role,
        session_id,
        task_id,
        role,
        "full" if weighty else "standard",
        max(timeout or 0, WEIGHTY_TIMEOUT_S) if weighty else timeout,
        target["model"],
        complexity,
        db_path,
        adapter=target["adapter"],
        effort=target["effort"],
    )
    if weighty and request.max_turns:
        # A stronger model reads more before it answers (agent-supervision.md).
        request.max_turns *= 2
    if context:
        request.input_slice.update(context)
    result = asyncio.run(_disp.dispatch_request(request, db_path))
    route = {
        "adapter": request.adapter,
        "model": request.model,
        "effort": request.effort,
        "error_category": result.error_category,
        "error": result.error,
    }

    # A review that cited nothing inside the task's own files did not review
    # what it was dispatched for, whatever produced the mismatch. Observed:
    # row 63, security_auditor on a docs-only card, 40 cited paths across
    # graph_os and the ingest layer, recorded status=ok at $1.35.
    out_of_scope = None
    if result.status == "ok":
        # The task's own commits when linked; "everything since it started" only
        # as a fallback, since on trunk that also holds sibling sessions' work.
        scope = (context or {}).get("review_scope") or {}
        out_of_scope = scope_verdict(
            cited_paths(result.output_json, result.raw_transcript),
            set(scope.get("files") or []) or _task_files(task_id, db_path),
        )
    if out_of_scope:
        route["error_category"] = "out_of_scope"
        route["error"] = out_of_scope
        result.status = "fail"

    if result.output_json:
        _persist_dispatch_output(
            session_id=session_id,
            task_marker=task_id,
            persona_id=role,
            formula_id=role,
            output_json=result.output_json,
            status=result.status,
            latency_ms=result.latency_ms,
            db_path=db_path,
            raw_transcript=result.raw_transcript,
            resolved_route=route,
        )
    meta = result.output_json.get("_meta") if isinstance(result.output_json, dict) else {}
    meta = meta if isinstance(meta, dict) else {}
    verdict, findings = parse_verdict(result.output_json)
    return {
        "role": role,
        "adapter": meta.get("adapter") or target["adapter"],
        "model": meta.get("model") or request.model,
        "status": result.status,
        "cost_usd": meta.get("total_cost_usd"),
        "latency_ms": result.latency_ms,
        "error": (out_of_scope or result.error or "")[:200] or None,
        "passed": False if out_of_scope else verdict,
        "findings": findings,
        "out_of_scope": bool(out_of_scope),
    }


def dirs() -> tuple[Path, Path]:
    state_dir = Path(os.environ.get("COS_STATE_DIR") or (_SRC.parent / ".coding-os"))
    panel_dir = Path(
        os.environ.get("COS_PANEL_DIR") or os.environ.get("COS_AGENT_DIR") or state_dir
    )
    return state_dir, panel_dir


def round_plan(
    task_id: str, session_adapter: str, state_dir: Path, panel_dir: Path
) -> tuple[int, dict, str, list[dict[str, Any]]]:
    from _paths import resolve_project_root

    from board_os import review_gate, review_security

    db_path = str(state_dir / "coding-os.db")
    # The hook sees the move request, not its result: a refused move plans no review.
    if not review_gate.in_testing(db_path, task_id):
        return 0, {}, "", []
    # A task back from rework is a new round: the fix has to be reviewed too.
    round_no = review_gate.current_round(db_path, task_id)
    # Neither a package nor an audit plan that cannot be built may cost the round its review.
    try:
        context = review_context(state_dir, task_id, round_no)
    except Exception as exc:
        logger.debug("review package for %s unavailable: %s", task_id, exc)
        context = {}
    try:
        scope = context.get("review_scope") or {}
        digest = review_security.audit_digest(task_id, round_no, resolve_project_root(), scope)
    except Exception as exc:
        logger.debug("security audit plan for %s unavailable: %s", task_id, exc)
        digest = ""
    complexity = review_weight(panel_dir, bool(digest))
    policy = load_policy(state_dir)
    # Supervision on: the Hub's pins and defaults decide. Off: the session's own model.
    by_policy = routed(policy, complexity)
    session_model = os.environ.get("COS_AGENT_MODEL", "").strip()
    targets = weighted(
        review_targets(policy if by_policy else {}, session_adapter, security=bool(digest)),
        complexity,
        session_adapter,
        "" if by_policy else session_review_model(session_adapter, session_model),
    )
    return round_no, context, digest, targets


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        return 0
    task_id, session_id, session_adapter = argv[1], argv[2], argv[3]
    state_dir, panel_dir = dirs()

    from _paths import resolve_project_root
    from native_review import native_agent, request_review

    from board_os import review_gate

    db_path = str(state_dir / "coding-os.db")
    round_no, context, digest, targets = round_plan(task_id, session_adapter, state_dir, panel_dir)
    project = resolve_project_root()
    files = (context.get("review_scope") or {}).get("files") or []
    detached = []
    for target in targets:
        agent = native_agent(target, session_adapter, project)
        if agent:
            # The session's own subagent reviews it; the request is written once, by either side.
            request_review(task_id, round_no, target, agent, digest, files)
        else:
            detached.append(target)
    targets = detached

    marker = panel_dir / ".auto-dispatched"
    results_file = panel_dir / ".dispatch-results"
    due = []
    for target in targets:
        key = f"{task_id}:{target['role']}:{round_no}"
        if not seen(marker, key):
            remember(marker, key)
            due.append(target)
    # Pending before the first one runs, so the gate cannot pass between two reviews.
    for target in due:
        review_gate.record(task_id, round_no, target["role"], target["adapter"], state="running")

    for target in due:
        role, adapter = target["role"], target["adapter"]
        try:
            outcome = _dispatch_one(target, task_id, session_id, db_path, context)
        except Exception as exc:
            # A background dispatch must never surface as a crash in the parent.
            outcome = {
                "role": role,
                "adapter": adapter,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}"[:200],
            }
        append_json(results_file, outcome)
        review_gate.record(
            task_id,
            round_no,
            role,
            adapter,
            state="done" if outcome.get("status") == "ok" else "error",
            passed=outcome.get("passed"),
            findings=outcome.get("findings"),
            digest=digest if role == AUDITOR else "",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
