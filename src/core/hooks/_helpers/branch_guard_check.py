#!/usr/bin/env python3
"""branch-guard parser — detects branch-create or HEAD-rewriting git ops
in a Bash command and emits a verdict.

Stdin:  {"tool_name": ..., "tool_input": {"command": "<bash cmd>"}}
Stdout: {"verdict": "allow"} OR
        {"verdict": "block", "reason": "<rule-id>", "message": "<stderr msg>"}
Exit:   0 always — verdict in JSON is the signal (matches the pattern
        used by other `_helpers/*.py` modules).

Why a Python helper instead of more bash: the parser must normalize
whitespace, strip git global options (`git -C path`, `git -c k=v`),
descend into nested `sh -c "..."` / `bash -c "..."`, split on shell
command separators, AND keep literal strings inside `echo`/`grep` args
from triggering — substring matching in bash slipped on all of these
(see TASK-013 reviewer probes). `shlex` handles quoting correctly.

Module layout:
  branch_guard_refs   protected-ref set + refspec normalization (shared leaf)
  branch_guard_trunk  the trunk-mode checkers, dispatch table and messages
  branch_guard_pr     the pr-mode shared-checkout policy and its messages
  this module         mode selection, shell-indirection recovery, stdin/stdout
"""

from __future__ import annotations

import json
import os
import sys

from branch_guard_pr import _evaluate_pr
from branch_guard_trunk import _evaluate_trunk
from git_command_parse import command_groups, normalize, recover_indirect_commands


def _evaluate(command: str, _recover: bool = True) -> tuple[str, str, str]:
    """Returns (verdict, reason, message). verdict is 'allow' or 'block'. Uses the
    SHARED git_command_parse tokenizer (quote-aware AND `;`-aware) — no private
    segmenter, so branch_guard and the commit/secret gates can never drift apart,
    and a `;`/`(` inside a quoted commit message no longer false-splits (TASK-572)."""
    groups = command_groups(normalize(command))
    if not groups:
        return "allow", "", ""
    if os.environ.get("COS_GIT_WORKFLOW", "trunk") == "pr":
        verdict = _evaluate_pr(groups)
    else:
        verdict = _evaluate_trunk(groups)
    if verdict[0] == "block" or not _recover:
        return verdict
    # Shell-indirection backstop: a protected op hidden inside eval / pipe-into-sh /
    # here-string / xargs is invisible to the tokenizer above. Recover each inner
    # command string and re-evaluate it against the same rules — one level, since a
    # recovered string is a plain git command.
    for recovered in recover_indirect_commands(command):
        r_verdict = _evaluate(recovered, _recover=False)
        if r_verdict[0] == "block":
            return r_verdict
    return verdict


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        json.dump({"verdict": "allow"}, sys.stdout)
        return 0
    if payload.get("tool_name") != "Bash":
        json.dump({"verdict": "allow"}, sys.stdout)
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str) or not command:
        json.dump({"verdict": "allow"}, sys.stdout)
        return 0

    verdict, reason, message = _evaluate(command)
    out: dict[str, str] = {"verdict": verdict}
    if verdict == "block":
        out["reason"] = reason
        out["message"] = message
    json.dump(out, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
