"""Run a testing round's review on the session's own runtime as its native subagent.

`plan` (PostToolUse, the move to testing) writes the running rows and tells the agent
which call to make; `guard` (PreToolUse Agent) refuses any other call; `start`
(SubagentStart) hands the subagent its package; `deliver` (PreToolUse
SubagentHandback) and `stop` (SubagentStop) record its verdict, so the verdict
reaches the ledger without passing through the main agent.
Contract: docs/engineering/agent-supervision.md § A review on the session's own
runtime runs as its native subagent.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[3]
for _path in (_SRC / "core", _SRC, _SRC / "core" / "thinking_os"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from auto_dispatch import append_json, dirs, remember, review_context, round_plan, seen
from review_model import model_tier
from review_requests import REQUESTS_NAME, claimed_by, open_for, prune
from review_verdict import cited_paths, parse_output, parse_verdict, scope_verdict

from board_os import review_gate
from board_os.review_security import AUDITOR

logger = logging.getLogger(__name__)

PACKAGES_DIR = "review-packages"
# Claude Code moves a hook string longer than 10,000 characters into a file and
# hands the model a 2,000-character preview, which would cut the package short.
CONTEXT_CHARS = 9_000
# A run that ends without output JSON is restarted once; the second is an error.
MAX_RUNS = 2
TASK_ID = re.compile(r"^TASK-[A-Za-z0-9-]*[0-9]$")
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _descriptor(adapter: str) -> dict[str, Any]:
    try:
        import yaml

        path = _SRC / "adapters" / adapter / "adapter.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.debug("adapter descriptor unreadable for %s: %s", adapter, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _review_agents(adapter: str) -> dict[str, str]:
    agents = _descriptor(adapter).get("native_review_agents")
    return {str(k): str(v) for k, v in agents.items()} if isinstance(agents, dict) else {}


def native_agent(target: dict[str, Any], session_adapter: str, project_root: Path) -> str:
    if target.get("adapter") != session_adapter:
        return ""
    name = _review_agents(session_adapter).get(str(target.get("role")))
    agents_dir = _descriptor(session_adapter).get("agents_dir")
    if not name or not agents_dir:
        return ""
    try:
        installed = (project_root / agents_dir / f"{name}.md").read_bytes()
        shipped = (_SRC / "adapters" / session_adapter / "agents" / f"{name}.md").read_bytes()
    except OSError:
        # A project not yet updated lacks the definition; the detached dispatch reviews it.
        return ""
    # The definition sets the reviewer's tools and instructions: an edited copy does not review.
    return name if installed == shipped else ""


def _role_file(role: str) -> tuple[dict[str, Any], str]:
    try:
        import yaml

        text = (_SRC / "core" / "thinking_os" / "agents" / f"{role}.md").read_text(encoding="utf-8")
        match = _FRONTMATTER.match(text)
        meta = yaml.safe_load(match.group(1)) if match else {}
    except Exception as exc:
        logger.debug("role prompt unreadable for %s: %s", role, exc)
        return {}, ""
    body = text[match.end() :] if match else text
    return (meta if isinstance(meta, dict) else {}), body


def agent_model(target: dict[str, Any], session_model: str) -> str:
    # "" means the subagent inherits the session's model.
    model = str(target.get("model") or "")
    if model and model == session_model:
        return ""
    if not model:
        meta, _ = _role_file(str(target.get("role")))
        prefs = meta.get("model_pref")
        level = "complex" if target.get("complexity") == "COMPLEX" else "complicated"
        model = str(prefs.get(level) or "") if isinstance(prefs, dict) else ""
    return model_tier(model)


def agent_call(agent: str, model: str) -> str:
    model_arg = f', model="{model}"' if model else ""
    return f'Agent(subagent_type="{agent}"{model_arg})'


def review_prompt(task_id: str, round_no: int) -> str:
    return f"Review {task_id} round {round_no}"


def plan(task_id: str, session_adapter: str) -> str:
    if not TASK_ID.match(task_id):
        return ""
    from _paths import resolve_project_root

    state_dir, panel_dir = dirs()
    round_no, context, digest, targets = round_plan(task_id, session_adapter, state_dir, panel_dir)
    project = resolve_project_root()
    session_model = os.environ.get("COS_AGENT_MODEL", "").strip()
    scope = (context.get("review_scope") or {}).get("files") or []
    marker = panel_dir / ".auto-dispatched"
    lines: list[str] = []
    calls: list[str] = []
    for target in targets:
        role, adapter = target["role"], target["adapter"]
        key = f"{task_id}:{role}:{round_no}"
        agent = native_agent(target, session_adapter, project)
        if not agent:
            # auto_dispatch.py runs it detached; the chat only learns that it began.
            if not seen(marker, f"{key}:announced"):
                remember(marker, f"{key}:announced")
                model = target.get("model") or "its default model"
                lines.append(f"🛰️ {task_id} review started — {role}@{adapter} ({model})")
            continue
        if seen(marker, key):
            continue
        remember(marker, key)
        model = agent_model(target, session_model)
        call = agent_call(agent, model)
        review_gate.record(task_id, round_no, role, adapter, state="running", native=call)
        append_json(
            panel_dir / REQUESTS_NAME,
            {
                "event": "request",
                "id": key,
                "task_id": task_id,
                "round": round_no,
                "role": role,
                "adapter": adapter,
                "agent": agent,
                "call": call,
                "model": model,
                "digest": digest if role == AUDITOR else "",
                "files": list(scope),
            },
        )
        lines.append(f"🔎 {task_id} review ready — {role} runs as subagent {agent}")
        calls.append(call)
    prune(panel_dir)
    if not lines:
        return ""
    text = f"{review_gate.BOARD_EVENTS_HEADER}\n" + "\n".join(lines)
    if calls:
        text = (
            f"Start the review of {task_id} round {round_no} now, before other work: "
            f"{' and '.join(calls)}, each with the prompt "
            f'"{review_prompt(task_id, round_no)}" and nothing else. Its review package '
            f"arrives through a hook, so do not paste the diff; its verdict is recorded by "
            f"a hook, so do not relay or restate it. task-done waits for it.\n{text}"
        )
    return _hook_output("PostToolUse", additionalContext=text)


def _hook_output(event: str, **fields: str) -> str:
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": event, **fields}}, ensure_ascii=False
    )


def _deny(reason: str) -> str:
    return _hook_output("PreToolUse", permissionDecision="deny", permissionDecisionReason=reason)


def guard(payload: dict[str, Any]) -> str:
    tool_input = payload.get("tool_input") or {}
    agent = str(tool_input.get("subagent_type") or "")
    if agent not in _review_agents(os.environ.get("COS_AGENT", "")).values():
        return ""
    _, panel_dir = dirs()
    request = open_for(panel_dir, agent)
    if request is None:
        return _deny(
            f"No review is waiting for {agent} in this session. To review a task here, "
            f"move it back to in_progress and then to testing; that plans a round here."
        )
    prompt = review_prompt(request["task_id"], int(request["round"]))
    if str(tool_input.get("prompt") or "").strip() != prompt or str(
        tool_input.get("model") or ""
    ) != str(request.get("model") or ""):
        return _deny(
            f'Start this review exactly as planned: {request.get("call", agent)} with the prompt "{prompt}" '
            f"and nothing more. The review package reaches the subagent through a hook."
        )
    return ""


def _package_text(request: dict[str, Any], package: dict[str, Any], package_file: Path) -> str:
    head = (
        f"[coding-os review] You are the coding-os {request['role']}, reviewing "
        f"{request['task_id']} round {request['round']}. Read {package_file} first: it "
        f"holds your role instructions and the whole review package. You cannot run "
        f"commands; read the files you need. Answer in composer mode: the report you "
        f"hand back is the output JSON object only, every finding in one pass."
    )
    inline = json.dumps(package, ensure_ascii=False, indent=1)
    if len(head) + len(inline) > CONTEXT_CHARS:
        scope = dict(package.get("review_scope") or {})
        scope["diff"] = f"[{len(scope.get('diff') or '')} characters; in {package_file}]"
        inline = json.dumps({**package, "review_scope": scope}, ensure_ascii=False, indent=1)
    if len(head) + len(inline) > CONTEXT_CHARS:
        inline = inline[: CONTEXT_CHARS - len(head)] + f"\n[cut; the rest is in {package_file}]"
    return f"{head}\nReview package:\n{inline}"


def _package_file(panel_dir: Path, request: dict[str, Any]) -> Path:
    name = f"{request['task_id']}-r{request['round']}-{request['role']}.md"
    return panel_dir / PACKAGES_DIR / name


def start(payload: dict[str, Any]) -> str:
    state_dir, panel_dir = dirs()
    request = open_for(panel_dir, str(payload.get("agent_type") or ""))
    if request is None or not TASK_ID.match(str(request.get("task_id"))):
        return ""
    # A restart re-claims the request: the newest start of a review owns it.
    agent_id = str(payload.get("agent_id") or "")
    append_json(
        panel_dir / REQUESTS_NAME, {"event": "claim", "id": request["id"], "agent_id": agent_id}
    )
    task_id, round_no, role = request["task_id"], int(request["round"]), request["role"]
    # A fresh running row without the call: the gate now waits instead of asking for a start.
    review_gate.record(task_id, round_no, role, request["adapter"], state="running")
    try:
        package = review_context(state_dir, task_id, round_no)
    except Exception as exc:
        logger.debug("review package for %s unavailable: %s", task_id, exc)
        package = {}
    _, instructions = _role_file(role)
    package_file = _package_file(panel_dir, request)
    try:
        package_file.parent.mkdir(parents=True, exist_ok=True)
        package_file.write_text(
            f"{instructions}\n\n## Review package\n\n```json\n"
            f"{json.dumps(package, ensure_ascii=False, indent=1)}\n```\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("review package file not written: %s", exc)
    return _hook_output(
        "SubagentStart", additionalContext=_package_text(request, package, package_file)
    )


def _finish(panel_dir: Path, request: dict[str, Any], output: dict | None, message: str) -> None:
    passed, findings = parse_verdict(output)
    out_of_scope = (
        scope_verdict(cited_paths(output, message), set(request.get("files") or []))
        if output
        else None
    )
    error = out_of_scope or ("" if output else f"no output JSON after {MAX_RUNS} runs")
    passed = False if out_of_scope else passed
    review_gate.record(
        request["task_id"],
        int(request["round"]),
        request["role"],
        request["adapter"],
        state="error" if error else "done",
        passed=passed,
        findings=findings,
        digest=request.get("digest") or "",
    )
    append_json(panel_dir / REQUESTS_NAME, {"event": "done", "id": request["id"]})
    _package_file(panel_dir, request).unlink(missing_ok=True)
    append_json(
        panel_dir / ".dispatch-results",
        {
            "role": request["role"],
            "adapter": request["adapter"],
            "model": request.get("model") or "session",
            "status": "fail" if error else "ok",
            "error": error[:200] or None,
            "passed": passed,
            "findings": findings,
        },
    )


def deliver(payload: dict[str, Any]) -> str:
    _, panel_dir = dirs()
    agent_type, agent_id = str(payload.get("agent_type") or ""), str(payload.get("agent_id") or "")
    request = claimed_by(panel_dir, agent_type, agent_id)
    if request is None:
        return ""
    message = str((payload.get("tool_input") or {}).get("message") or "")
    output = parse_output(message)
    if output is None:
        # Claude Code asks the subagent to deliver again when a hand-back is denied.
        return _deny(
            "Hand back the review as the output JSON object only, with no prose around it: "
            "the ledger records exactly that object."
        )
    _finish(panel_dir, request, output, message)
    return ""


def stop(payload: dict[str, Any]) -> None:
    _, panel_dir = dirs()
    agent_type, agent_id = str(payload.get("agent_type") or ""), str(payload.get("agent_id") or "")
    request = claimed_by(panel_dir, agent_type, agent_id)
    if request is None:
        return
    message = str(payload.get("last_assistant_message") or "")
    output = parse_output(message)
    if output is not None or request["runs"] + 1 >= MAX_RUNS:
        _finish(panel_dir, request, output, message)
        return
    # The review never arrived: ask for it again instead of closing without one.
    append_json(panel_dir / REQUESTS_NAME, {"event": "reopen", "id": request["id"]})
    review_gate.record(
        request["task_id"],
        int(request["round"]),
        request["role"],
        request["adapter"],
        state="running",
        native=str(request.get("call") or ""),
    )


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        if mode == "plan" and len(argv) >= 4:
            sys.stdout.write(plan(argv[2], argv[3]))
            return 0
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        if mode == "stop":
            stop(payload)
            return 0
        handlers = {"guard": guard, "start": start, "deliver": deliver}
        if mode in handlers:
            sys.stdout.write(handlers[mode](payload))
    except Exception as exc:
        # A review hook must never break the move or the subagent that fired it.
        logger.debug("native review %s failed: %s", mode, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
