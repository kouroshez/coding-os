"""Run a testing round's review on the session's own runtime as its native subagent.

`plan` runs inside the PostToolUse hook that sees the move to testing: it writes the
running rows and tells the agent which subagent to start. `start` (SubagentStart)
hands that subagent its review package; `stop` (SubagentStop) records its verdict,
so the verdict reaches the ledger without passing through the main agent.
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

from auto_dispatch import (
    _append,
    _cited_paths,
    _remember,
    _scope_verdict,
    _seen,
    _verdict,
    dirs,
    review_context,
    round_plan,
)
from review_model import model_tier

from board_os import review_gate
from board_os.review_security import AUDITOR

logger = logging.getLogger(__name__)

REQUESTS_NAME = ".native-reviews.jsonl"
PACKAGES_DIR = "review-packages"
# Claude Code moves a hook string longer than 10,000 characters into a file and
# hands the model a 2,000-character preview, which would cut the package short.
CONTEXT_CHARS = 9_000
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


def session_started(session_id: str) -> float | None:
    agent_dir = os.environ.get("COS_AGENT_DIR")
    if not agent_dir or not session_id:
        return None
    try:
        record = json.loads(
            (Path(agent_dir) / "sessions" / f"{session_id}.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    started = record.get("started_at") if isinstance(record, dict) else None
    return float(started) if isinstance(started, (int, float)) else None


def native_agent(
    target: dict[str, Any],
    session_adapter: str,
    project_root: Path,
    started_at: float | None = None,
) -> str:
    if target.get("adapter") != session_adapter:
        return ""
    descriptor = _descriptor(session_adapter)
    agents = descriptor.get("native_review_agents")
    name = agents.get(target.get("role")) if isinstance(agents, dict) else None
    agents_dir = descriptor.get("agents_dir")
    if not name or not agents_dir:
        return ""
    definition = project_root / agents_dir / f"{name}.md"
    # A project not yet updated lacks the definition; the detached dispatch still reviews it.
    if not definition.is_file():
        return ""
    # The runtime reads its agents when the session starts; one linked later is unknown to it.
    if started_at is not None and definition.lstat().st_mtime > started_at:
        return ""
    return str(name)


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


def plan(task_id: str, session_id: str, session_adapter: str) -> str:
    from _paths import resolve_project_root

    state_dir, panel_dir = dirs()
    round_no, context, digest, targets = round_plan(task_id, session_adapter, state_dir, panel_dir)
    project = resolve_project_root()
    started_at = session_started(session_id)
    session_model = os.environ.get("COS_AGENT_MODEL", "").strip()
    scope = (context.get("review_scope") or {}).get("files") or []
    marker = panel_dir / ".auto-dispatched"
    lines: list[str] = []
    calls: list[str] = []
    for target in targets:
        role, adapter = target["role"], target["adapter"]
        key = f"{task_id}:{role}:{round_no}"
        if _seen(marker, key):
            continue
        agent = native_agent(target, session_adapter, project, started_at)
        if not agent:
            # auto_dispatch.py runs it detached; the chat only learns that it began.
            model = target.get("model") or "its default model"
            lines.append(f"🛰️ {task_id} review started — {role}@{adapter} ({model})")
            continue
        _remember(marker, key)
        call = agent_call(agent, agent_model(target, session_model))
        review_gate.record(task_id, round_no, role, adapter, state="running", native=call)
        _append(
            panel_dir / REQUESTS_NAME,
            {
                "event": "request",
                "id": key,
                "task_id": task_id,
                "round": round_no,
                "role": role,
                "adapter": adapter,
                "agent": agent,
                "model": target.get("model") or "",
                "digest": digest if role == AUDITOR else "",
                "files": list(scope),
            },
        )
        lines.append(f"🔎 {task_id} review ready — {role} runs as subagent {agent}")
        calls.append(call)
    if not lines:
        return ""
    text = f"{review_gate.BOARD_EVENTS_HEADER}\n" + "\n".join(lines)
    if calls:
        text = (
            f"Start the review of {task_id} round {round_no} now, before other work: "
            f'{" and ".join(calls)}, each with the prompt "Review {task_id} round {round_no}". '
            f"Its review package arrives through a hook, so do not paste the diff; its "
            f"verdict is recorded by a hook, so do not relay or restate it. task-done "
            f"waits for it.\n{text}"
        )
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}},
        ensure_ascii=False,
    )


def _requests(panel_dir: Path) -> list[dict[str, Any]]:
    try:
        raw = (panel_dir / REQUESTS_NAME).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    by_id: dict[str, dict[str, Any]] = {}
    for line in raw:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or not event.get("id"):
            continue
        if event.get("event") == "request":
            by_id[event["id"]] = dict(event)
        elif event["id"] in by_id:
            by_id[event["id"]][str(event.get("event"))] = event.get("agent_id") or True
    return list(by_id.values())


def _claimable(panel_dir: Path, agent_type: str) -> dict[str, Any] | None:
    return next(
        (
            r
            # Newest first: a request from an earlier round that nobody started is stale.
            for r in reversed(_requests(panel_dir))
            if r.get("agent") == agent_type and not r.get("claim") and not r.get("done")
        ),
        None,
    )


def _claimed(panel_dir: Path, agent_type: str, agent_id: str) -> dict[str, Any] | None:
    running = [
        r
        for r in reversed(_requests(panel_dir))
        if r.get("agent") == agent_type and r.get("claim") and not r.get("done")
    ]
    return next((r for r in running if r.get("claim") == agent_id), None) or next(
        iter(running), None
    )


def _package_text(request: dict[str, Any], package: dict[str, Any], package_file: Path) -> str:
    head = (
        f"[coding-os review] You are the coding-os {request['role']}, reviewing "
        f"{request['task_id']} round {request['round']}. Read {package_file} first: it "
        f"holds your role instructions and the whole review package. You cannot run "
        f"commands; read the files you need. Answer in composer mode: your final "
        f"message is the output JSON object only, every finding in one pass."
    )
    inline = json.dumps(package, ensure_ascii=False, indent=1)
    if len(head) + len(inline) > CONTEXT_CHARS:
        scope = dict(package.get("review_scope") or {})
        scope["diff"] = f"[{len(scope.get('diff') or '')} characters; in {package_file}]"
        inline = json.dumps({**package, "review_scope": scope}, ensure_ascii=False, indent=1)
    if len(head) + len(inline) > CONTEXT_CHARS:
        inline = inline[: CONTEXT_CHARS - len(head)] + f"\n[cut; the rest is in {package_file}]"
    return f"{head}\nReview package:\n{inline}"


def start(payload: dict[str, Any]) -> str:
    state_dir, panel_dir = dirs()
    agent_id = str(payload.get("agent_id") or "")
    request = _claimable(panel_dir, str(payload.get("agent_type") or ""))
    if request is None:
        return ""
    _append(
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
    package_file = panel_dir / PACKAGES_DIR / f"{task_id}-r{round_no}-{role}.md"
    try:
        package_file.parent.mkdir(parents=True, exist_ok=True)
        package_file.write_text(
            f"{instructions}\n\n## Review package\n\n```json\n"
            f"{json.dumps(package, ensure_ascii=False, indent=1)}\n```\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("review package file not written: %s", exc)
    text = _package_text(request, package, package_file)
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": text}},
        ensure_ascii=False,
    )


def parse_output(message: str) -> dict[str, Any] | None:
    candidates = [message.strip()]
    candidates.extend(reversed(re.findall(r"```(?:json)?\s*\n(.*?)\n```", message, re.DOTALL)))
    if "{" in message and "}" in message:
        candidates.append(message[message.index("{") : message.rindex("}") + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def stop(payload: dict[str, Any]) -> None:
    _, panel_dir = dirs()
    agent_type, agent_id = str(payload.get("agent_type") or ""), str(payload.get("agent_id") or "")
    request = _claimed(panel_dir, agent_type, agent_id)
    if request is None:
        return
    message = str(payload.get("last_assistant_message") or "")
    output = parse_output(message)
    passed, findings = _verdict(output)
    files = set(request.get("files") or [])
    out_of_scope = _scope_verdict(_cited_paths(output, message), files) if output else None
    error = out_of_scope or ("" if output else "no output JSON in the subagent's last message")
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
    _append(panel_dir / REQUESTS_NAME, {"event": "done", "id": request["id"]})
    _append(
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


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        if mode == "plan" and len(argv) >= 5:
            sys.stdout.write(plan(argv[2], argv[3], argv[4]))
            return 0
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        if mode == "start":
            sys.stdout.write(start(payload))
        elif mode == "stop":
            stop(payload)
    except Exception as exc:
        # A review hook must never break the move or the subagent that fired it.
        logger.debug("native review %s failed: %s", mode, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
