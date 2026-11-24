"""Start the review of a task's testing round: the reviewer, plus the security auditor when due.

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
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
for _path in (_SRC / "core", _SRC, _SRC / "core" / "thinking_os"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from board_os.review_gate import DETAIL_CHARS
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


def review_targets(policy: dict, session_adapter: str, *, security: bool = False) -> list[dict]:
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
        if known(pinned):
            # Effort is carried verbatim: an adapter without effort_selection
            # rejects a pinned one, so the policy is where codex keeps it empty.
            model, effort = str(pin.get("model") or ""), str(pin.get("effort") or "")
            targets.append({"role": role, "adapter": pinned, "model": model, "effort": effort})
        elif known(session_adapter):
            targets.append({"role": role, "adapter": session_adapter, "model": "", "effort": ""})
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


def _seen(marker: Path, key: str) -> bool:
    try:
        return key in marker.read_text(encoding="utf-8").split("\n")
    except OSError:
        return False


def _remember(marker: Path, key: str) -> None:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open("a", encoding="utf-8") as handle:
            handle.write(key + "\n")
    except OSError:
        pass


def _append(results_file: Path, payload: dict) -> None:
    try:
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with results_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError:
        pass


_PATH_RE = re.compile(r"\b(?:src|tests|docs|scripts)/[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,5}\b")


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


def _cited_paths(output_json: object, raw_transcript: str | None) -> set[str]:
    # The reviewer's own words are the evidence. Scan the transcript as well as
    # the structured output: a role that names files only in prose still told
    # us where it looked.
    haystack = json.dumps(output_json, default=str) if output_json else ""
    if raw_transcript:
        haystack = f"{haystack}\n{raw_transcript}"
    return set(_PATH_RE.findall(haystack))


def _scope_verdict(cited: set[str], allowed: set[str]) -> str | None:
    # None means "no verdict" — recorded normally. A guard that fires on the
    # absence of evidence gets routed around, so both unknowns stay silent: a
    # role that cites nothing may legitimately have no file to name, and an
    # empty allowed set is a claim we cannot test rather than one that failed.
    if not cited or not allowed:
        return None
    if cited & allowed:
        return None
    return (
        f"out of scope: cited {len(cited)} path(s), none inside the "
        f"{len(allowed)} the task changed. cited={sorted(cited)[:5]} "
        f"allowed={sorted(allowed)[:5]}"
    )


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
    request = _build_dispatch_request(
        role,
        session_id,
        task_id,
        role,
        "standard",
        adapter_timeout(target["adapter"]),
        target["model"],
        "COMPLICATED",
        db_path,
        adapter=target["adapter"],
        effort=target["effort"],
    )
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
        out_of_scope = _scope_verdict(
            _cited_paths(result.output_json, result.raw_transcript),
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
    verdict, findings = _verdict(result.output_json)
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


_FINDING_KEYS = ("review_findings", "findings", "dependency_risks")
# `detail` is the reviewer's contract key (reviewer.md), `description` the auditor's.
_TEXT_KEYS = ("description", "detail", "finding", "issue", "summary", "title", "message")


def _verdict(output_json: object) -> tuple[bool | None, list[str]]:
    # A review that ran and found nothing reads identically to a review whose
    # findings were dropped, unless the verdict travels with the route. The
    # route and the price used to be the whole message the parent got back.
    if not isinstance(output_json, dict):
        return None, []
    passed = output_json.get("passed")
    passed = passed if isinstance(passed, bool) else None

    findings: list[str] = []
    for key in _FINDING_KEYS:
        for item in output_json.get(key) or []:
            text = _finding_text(item)
            if text:
                findings.append(text)
    # Uncut: review_gate.record orders by severity before it applies the one cap.
    return passed, findings


def _finding_text(item: object) -> str:
    if isinstance(item, str):
        return item[:DETAIL_CHARS]
    if not isinstance(item, dict):
        return ""
    body = next((str(item[k]) for k in _TEXT_KEYS if item.get(k)), "")
    if not body:
        return ""
    if item.get("file"):
        line = f":{item['line']}" if item.get("line") else ""
        body = f"{item['file']}{line} — {body}"
    severity = item.get("severity")
    prefix = f"{severity}: " if isinstance(severity, str) and severity else ""
    return (prefix + body)[:DETAIL_CHARS]


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        return 0
    task_id, session_id, session_adapter = argv[1], argv[2], argv[3]
    state_dir = Path(os.environ.get("COS_STATE_DIR") or (_SRC.parent / ".coding-os"))
    panel_dir = Path(
        os.environ.get("COS_PANEL_DIR") or os.environ.get("COS_AGENT_DIR") or state_dir
    )

    from _paths import resolve_project_root

    from board_os import review_gate, review_security

    db_path = str(state_dir / "coding-os.db")
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
    targets = review_targets(load_policy(state_dir), session_adapter, security=bool(digest))

    marker = panel_dir / ".auto-dispatched"
    results_file = panel_dir / ".dispatch-results"
    due = []
    for target in targets:
        key = f"{task_id}:{target['role']}:{round_no}"
        if not _seen(marker, key):
            _remember(marker, key)
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
        _append(results_file, outcome)
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
