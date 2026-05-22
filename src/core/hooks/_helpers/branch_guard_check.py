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
"""

from __future__ import annotations

import json
import re
import shlex
import sys

# git global options that take the next token as their argument.
_GLOBAL_OPTS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
# git global flags with no argument.
_GLOBAL_OPTS_NO_ARG = {
    "-p", "--paginate", "-P", "--no-pager",
    "--no-replace-objects", "--bare", "--no-optional-locks",
    "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs",
    "--icase-pathspecs",
}
# `--key=value` long options that bundle the arg.
_GLOBAL_LONG_EQ_PREFIXES = ("--git-dir=", "--work-tree=", "--namespace=", "-c=")

# Shells whose `-c <inner>` invocations we descend into.
_NESTED_SHELLS = {"sh", "bash", "zsh", "dash"}


def _looks_like_env_assignment(token: str) -> bool:
    """`FOO=bar` (caller-set env var) — drop before reading the command name."""
    if "=" not in token:
        return False
    name = token.split("=", 1)[0]
    return bool(name) and bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))


def _strip_env_vars(tokens: list[str]) -> list[str]:
    i = 0
    while i < len(tokens) and _looks_like_env_assignment(tokens[i]):
        i += 1
    return tokens[i:]


def _strip_git_globals(tokens: list[str]) -> list[str]:
    """Drop `git`'s pre-subcommand globals so the next token is the subcommand."""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in _GLOBAL_OPTS_WITH_ARG:
            i += 2
            continue
        if t in _GLOBAL_OPTS_NO_ARG:
            i += 1
            continue
        if any(t.startswith(p) for p in _GLOBAL_LONG_EQ_PREFIXES):
            i += 1
            continue
        out.extend(tokens[i:])
        break
    return out


# Crude segmenter: split on shell separators that start a new command.
# Doesn't perfectly respect quoting, but quoted commands are recovered via
# the `sh -c <quoted>` extractor below — together they cover the cases the
# TASK-013 reviewer surfaced.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|()&]")


def _split_segments(command: str) -> list[str]:
    return [s.strip() for s in _SEGMENT_SPLIT_RE.split(command) if s.strip()]


def _extract_nested_shells(segments: list[str]) -> list[str]:
    """For each `sh -c <inner>` / `bash -c <inner>` token sequence, return the
    inner string split into its own segments. shlex unquotes the inner."""
    extra: list[str] = []
    for seg in segments:
        try:
            tokens = shlex.split(seg, posix=True)
        except ValueError:
            continue
        # Skip leading env vars so `FOO=1 sh -c '...'` still matches.
        tokens = _strip_env_vars(tokens)
        if len(tokens) < 3:
            continue
        if tokens[0] in _NESTED_SHELLS and tokens[1] == "-c":
            inner = tokens[2]
            extra.extend(_split_segments(inner))
    return extra


def _check_checkout(args: list[str]) -> tuple[str | None, str | None]:
    # Branch create (-b/-B) — caught here too for consistency.
    if any(a in {"-b", "-B"} for a in args):
        return "branch-create-checkout", _MSG["branch-create"]
    # File restore: `--` separator is present.
    if "--" in args:
        return None, None
    arg = _first_positional(args)
    if arg is None or arg in {"main", "HEAD", "."}:
        return None, None
    return "checkout-branch-switch", _MSG["checkout-switch"]


def _check_switch(args: list[str]) -> tuple[str | None, str | None]:
    if any(a in {"-c", "-C"} for a in args):
        return "branch-create-checkout", _MSG["branch-create"]
    arg = _first_positional(args)
    if arg is None or arg == "main":
        return None, None
    return "switch-branch", _MSG["switch-branch"]


def _check_branch(args: list[str]) -> tuple[str | None, str | None]:
    # Block ONLY the create form `git branch <name> [<startpoint>]`. Any
    # leading flag (-d/-D/-m/-M/-c/-C/-a/-r/-v/--list/…) means delete /
    # rename / list / copy / show — all safe and HEAD-stable.
    if not args or args[0].startswith("-"):
        return None, None
    return "branch-create", _MSG["branch-create"]


def _check_worktree(args: list[str]) -> tuple[str | None, str | None]:
    if args and args[0] == "add":
        return "worktree-add", _MSG["branch-create"]
    return None, None


def _check_reset(args: list[str]) -> tuple[str | None, str | None]:
    # Strip leading reset flags.
    rest: list[str] = []
    seen_non_flag = False
    for a in args:
        if not seen_non_flag and a in {"--soft", "--mixed", "--keep", "--patch", "--hard"}:
            continue
        seen_non_flag = True
        rest.append(a)
    if not rest:
        return None, None
    first = rest[0]
    if first == "--" or first.startswith("--"):
        return None, None  # path-restore form
    if first == "HEAD":
        return None, None  # HEAD or HEAD <path>
    if first.startswith(("HEAD~", "HEAD^", "HEAD@")):
        return "reset-head-rewrite", _MSG["reset"]
    return "reset-head-rewrite", _MSG["reset"]


# Accepts `-` (previous branch/ref) as a positional arg, plus any
# token that doesn't start with `-`.
def _first_positional(args: list[str]) -> str | None:
    for a in args:
        if a == "-":
            return a
        if not a.startswith("-"):
            return a
    return None


_DISPATCH = {
    "checkout": _check_checkout,
    "switch": _check_switch,
    "branch": _check_branch,
    "worktree": _check_worktree,
    "reset": _check_reset,
}

_MSG = {
    "branch-create": (
        "BLOCKED: coding-os uses a trunk-based git workflow — commit\n"
        "directly to main, do not create branches or worktrees.\n"
        "\n"
        "  To fix: edit files, then 'git commit <explicit paths>' and\n"
        "  'git pull --rebase origin main && git push origin main'.\n"
        "\n"
        "  See src/core/rules/git-workflow.md for the full rule.\n"
        "  If the USER explicitly asked for this, re-run with\n"
        "  COS_GIT_WORKFLOW=pr set for that command."
    ),
    "reset": (
        "BLOCKED: this 'git reset' would move HEAD — in trunk mode\n"
        "moving HEAD off a published commit clobbers peer work.\n"
        "\n"
        "  Safe forms: 'git reset' (unstage), 'git reset --mixed HEAD',\n"
        "  'git reset -- <path>' (unstage one path).\n"
        "  To undo the last commit: 'git revert HEAD' (new commit,\n"
        "  preserves history).\n"
        "\n"
        "  See src/core/rules/git-workflow.md. Override:\n"
        "  COS_GIT_WORKFLOW=pr."
    ),
    "checkout-switch": (
        "BLOCKED: this 'git checkout' switches branches — coding-os\n"
        "uses a trunk-based workflow (main only).\n"
        "\n"
        "  To restore a file: 'git restore <path>' or\n"
        "  'git checkout -- <path>' (note the '--' separator).\n"
        "  To restore everything in cwd: 'git checkout .' is allowed.\n"
        "  To go to main: 'git switch main'.\n"
        "\n"
        "  See src/core/rules/git-workflow.md. Override:\n"
        "  COS_GIT_WORKFLOW=pr."
    ),
    "switch-branch": (
        "BLOCKED: this 'git switch' moves off main — coding-os uses\n"
        "a trunk-based workflow.\n"
        "\n"
        "  Only 'git switch main' is allowed in trunk mode.\n"
        "\n"
        "  See src/core/rules/git-workflow.md. Override:\n"
        "  COS_GIT_WORKFLOW=pr."
    ),
}


def _evaluate(command: str) -> tuple[str, str, str]:
    """Returns (verdict, reason, message). verdict is 'allow' or 'block'."""
    # Whitespace normalize — collapses tabs and multi-space runs that bash
    # substring match would have missed.
    command = " ".join(command.split())
    if not command:
        return "allow", "", ""

    segments = _split_segments(command)
    segments.extend(_extract_nested_shells(segments))

    for seg in segments:
        try:
            tokens = shlex.split(seg, posix=True)
        except ValueError:
            # Unbalanced quotes — fall back to whitespace split so we can
            # still catch the dominant `git reset HEAD~1` form.
            tokens = seg.split()
        tokens = _strip_env_vars(tokens)
        if not tokens or tokens[0] != "git":
            continue
        tokens = _strip_git_globals(tokens[1:])
        if not tokens:
            continue
        subcmd, args = tokens[0], tokens[1:]
        checker = _DISPATCH.get(subcmd)
        if checker is None:
            continue
        reason, message = checker(args)
        if reason:
            return "block", reason, message or ""
    return "allow", "", ""


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
