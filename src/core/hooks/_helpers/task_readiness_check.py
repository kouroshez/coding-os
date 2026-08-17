"""Decide whether a task-create declares its pull-state, for enforce-task-readiness.sh.

An icebox card carrying none of `ready` / `parked` / `keep` is invisible to
cos_task_pick and cos_task_claim_next, so nothing will ever pull it. Deferral
stays available — it just has to be stated instead of defaulted into.

Reads the PreToolUse envelope on stdin, prints a JSON verdict on stdout:

    {"verdict": "allow"}
    {"verdict": "block", "message": "..."}

Exit code is always 0; the verdict, not the code, is the signal (the caller maps
`block` to exit 2). Uses only the standard library so it runs under the bare
`python3` a hook gets.
"""

from __future__ import annotations

import json
import re
import shlex
import sys

_EXEMPT_LABELS = ("parked", "keep")
_CREATE_TOOL = "mcp__coding-os__cos_task_create"
# Shell operators that start a new command; a create only counts in command
# position. Substring matching blocked `git commit -m "... cos task-create ..."`
# on its own first attempt — an enforcement hook that fires on prose about a
# command is one operators learn to route around.
_SEGMENT_SPLIT = re.compile(r"(?:\|\||&&|[;\n|&])")

_MESSAGE = """BLOCKED: this would create an icebox card with no declared pull-state.

An icebox card carrying none of `ready` / `parked` / `keep` is invisible to
cos_task_pick and cos_task_claim_next — nobody will ever pull it.

Pick one, explicitly:
  {ready}
  {parked}   deliberate long-term backlog
  {keep}   reference card, never meant to be pulled

Deferring is allowed; defaulting into invisibility is not.
Contract: docs/governance/task-lifecycle.md § Execution Rules"""

_MCP_FORMS = {
    "ready": "ready=True             queue it now, pullable",
    "parked": 'labels=["parked"]',
    "keep": 'labels=["keep"]   ',
}
_CLI_FORMS = {
    "ready": "--ready                queue it now, pullable",
    "parked": "--labels parked   ",
    "keep": "--labels keep     ",
}


def _labels_declare_deferral(labels: object) -> bool:
    if isinstance(labels, str):
        candidates = [part.strip() for part in labels.split(",")]
    elif isinstance(labels, (list, tuple)):
        candidates = [str(part).strip() for part in labels]
    else:
        return False
    return any(label.lower() in _EXEMPT_LABELS for label in candidates)


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _targets_icebox(status: object) -> bool:
    # Only un-ready *icebox* is invisible; an explicit non-icebox create is fine.
    text = str(status or "").strip().lower()
    return text in {"", "icebox"}


def _check_mcp(tool_input: dict) -> dict:
    if not _targets_icebox(tool_input.get("status")):
        return {"verdict": "allow"}
    if _is_truthy(tool_input.get("ready")):
        return {"verdict": "allow"}
    if _labels_declare_deferral(tool_input.get("labels")):
        return {"verdict": "allow"}
    return {"verdict": "block", "message": _MESSAGE.format(**_MCP_FORMS)}


def _create_invocations(command: str) -> list[list[str]]:
    # Only an argv whose command WORD is `cos` (or a path ending in it) followed
    # by `task-create` counts. `git commit -m "… cos task-create …"` and
    # `grep 'cos task-create'` carry the phrase as data, not as a command.
    found: list[list[str]] = []
    for segment in _SEGMENT_SPLIT.split(command):
        try:
            argv = shlex.split(segment)
        except ValueError:
            # Unparseable quoting — the Stop-time backstop still covers this.
            continue
        # Skip env-var assignments and `env A=b` prefixes to reach the real head.
        head = 0
        while head < len(argv) and ("=" in argv[head].split(" ")[0] or argv[head] == "env"):
            head += 1
        if head + 1 >= len(argv):
            continue
        program = argv[head].rsplit("/", 1)[-1]
        if program == "cos" and argv[head + 1] == "task-create":
            found.append(argv[head + 1 :])
    return found


def _declares_pull_state(argv: list[str]) -> bool:
    if "--ready" in argv:
        return True
    for index, token in enumerate(argv):
        if not token.startswith(("--status", "--labels")):
            continue
        value = token.split("=", 1)[1] if "=" in token else (argv[index + 1 : index + 2] or [""])[0]
        if token.startswith("--status") and not _targets_icebox(value):
            return True
        if token.startswith("--labels") and _labels_declare_deferral(value):
            return True
    return False


def _check_cli(command: str) -> dict:
    invocations = _create_invocations(command)
    if not invocations:
        return {"verdict": "allow"}
    if all(_declares_pull_state(argv) for argv in invocations):
        return {"verdict": "allow"}
    return {"verdict": "block", "message": _MESSAGE.format(**_CLI_FORMS)}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        json.dump({"verdict": "allow"}, sys.stdout)
        return 0
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}

    if tool_name == _CREATE_TOOL:
        verdict = _check_mcp(tool_input)
    elif tool_name == "Bash":
        verdict = _check_cli(str(tool_input.get("command") or ""))
    else:
        verdict = {"verdict": "allow"}

    json.dump(verdict, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
