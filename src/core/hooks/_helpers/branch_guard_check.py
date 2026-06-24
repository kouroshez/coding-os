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
import os
import re
import shlex
import sys

# git global options that take the next token as their argument.
_GLOBAL_OPTS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
# git global flags with no argument.
_GLOBAL_OPTS_NO_ARG = {
    "-p",
    "--paginate",
    "-P",
    "--no-pager",
    "--no-replace-objects",
    "--bare",
    "--no-optional-locks",
    "--literal-pathspecs",
    "--glob-pathspecs",
    "--noglob-pathspecs",
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
# reviewer surfaced.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|()&]")


def _split_segments(command: str) -> list[str]:
    return [s.strip() for s in _SEGMENT_SPLIT_RE.split(command) if s.strip()]


# Backtick command substitution `` `cmd` `` — extract inner. The negative
# lookbehind skips ESCAPED backticks (`\``), which inside a `"..."` arg are
# inert literals — bash does not execute them. This avoids false positives
# on commit messages / docs that quote shell snippets like
# `git commit -m "see \`git reset HEAD~1\` for unsafe form"`.
_BACKTICK_RE = re.compile(r"(?<!\\)`([^`]+)`")


def _extract_backticks(segments: list[str]) -> list[str]:
    extra: list[str] = []
    for seg in segments:
        for m in _BACKTICK_RE.finditer(seg):
            extra.extend(_split_segments(m.group(1)))
    return extra


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


def _check_rebase(args: list[str]) -> tuple[str | None, str | None]:
    # Cleanup / inspection of an in-progress rebase doesn't rewrite history.
    _SAFE_REBASE_FLAGS = {
        "--abort",
        "--continue",
        "--skip",
        "--quit",
        "--edit-todo",
        "--show-current-patch",
    }
    for a in args:
        if a in _SAFE_REBASE_FLAGS:
            return None, None
    # Everything else (`git rebase main`, `-i HEAD~3`, bare → upstream)
    # rewrites trunk history and breaks peers.
    return "rebase-history-rewrite", _MSG["rebase-history"]


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
    "rebase": _check_rebase,
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
        "  If the USER explicitly asked: enable pr-mode per-project (Hub →\n"
        "  Config → Git) or export COS_GIT_WORKFLOW=pr session-wide — an inline\n"
        "  'COS_GIT_WORKFLOW=pr git …' prefix does NOT work (the guard reads its\n"
        "  own process env first)."
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
        "  See src/core/rules/git-workflow.md. pr-mode is enabled per-project\n"
        "  (Hub → Config → Git) or by exporting COS_GIT_WORKFLOW=pr session-wide\n"
        "  — an inline 'COS_GIT_WORKFLOW=pr git …' prefix does NOT work."
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
        "  See src/core/rules/git-workflow.md. pr-mode is enabled per-project\n"
        "  (Hub → Config → Git) or by exporting COS_GIT_WORKFLOW=pr session-wide\n"
        "  — an inline 'COS_GIT_WORKFLOW=pr git …' prefix does NOT work."
    ),
    "switch-branch": (
        "BLOCKED: this 'git switch' moves off main — coding-os uses\n"
        "a trunk-based workflow.\n"
        "\n"
        "  Only 'git switch main' is allowed in trunk mode.\n"
        "\n"
        "  See src/core/rules/git-workflow.md. pr-mode is enabled per-project\n"
        "  (Hub → Config → Git) or by exporting COS_GIT_WORKFLOW=pr session-wide\n"
        "  — an inline 'COS_GIT_WORKFLOW=pr git …' prefix does NOT work."
    ),
    "rebase-history": (
        "BLOCKED: 'git rebase' rewrites history on the shared trunk —\n"
        "peer commits get orphaned and force-push is required.\n"
        "\n"
        "  Safe forms (cleanup of an in-progress rebase):\n"
        "    git rebase --abort | --continue | --skip | --quit\n"
        "  To integrate concurrent commits before push:\n"
        "    git pull --rebase origin main   (rebases LOCAL commits only)\n"
        "  To undo a bad commit:\n"
        "    git revert HEAD                 (new commit, history intact)\n"
        "\n"
        "  See src/core/rules/git-workflow.md. pr-mode is enabled per-project\n"
        "  (Hub → Config → Git) or by exporting COS_GIT_WORKFLOW=pr session-wide\n"
        "  — an inline 'COS_GIT_WORKFLOW=pr git …' prefix does NOT work."
    ),
}


def _all_segments(command: str) -> list[str]:
    """Expand a normalized command into every executable segment: split on shell
    separators, then unwrap nested `sh -c`/backtick subshells with bounded
    recursion. Shared by the trunk and pr-mode evaluators."""
    all_segments = _split_segments(command)
    all_segments.extend(_extract_backticks(all_segments))
    frontier = list(all_segments)
    seen = set(all_segments)
    for _ in range(8):  # depth cap — runaway recursion guard
        layer = _extract_nested_shells(frontier) + _extract_backticks(frontier)
        layer = [s for s in layer if s not in seen]
        if not layer:
            break
        seen.update(layer)
        all_segments.extend(layer)
        frontier = layer
    return all_segments


def _tokenize(seg: str) -> list[str]:
    try:
        return shlex.split(seg, posix=True)
    except ValueError:
        # Unbalanced quotes — fall back to whitespace split so the dominant
        # `git reset HEAD~1` form is still caught.
        return seg.split()


def _evaluate(command: str) -> tuple[str, str, str]:
    """Returns (verdict, reason, message). verdict is 'allow' or 'block'."""
    # Treat literal newlines as command separators BEFORE the whitespace
    # collapse below would erase them — `git status\ngit reset HEAD~1`
    # is two commands.
    command = re.sub(r"\n+", "; ", command)
    # Whitespace normalize — collapses tabs and multi-space runs that bash
    # substring match would have missed.
    command = " ".join(command.split())
    if not command:
        return "allow", "", ""

    segments = _all_segments(command)
    if os.environ.get("COS_GIT_WORKFLOW", "trunk") == "pr":
        return _evaluate_pr(segments)
    return _evaluate_trunk(segments)


def _evaluate_trunk(segments: list[str]) -> tuple[str, str, str]:
    for seg in segments:
        tokens = _strip_env_vars(_tokenize(seg))
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


# ---------------------------------------------------------------------------
# pr-mode policy (TASK-516) — COS_GIT_WORKFLOW=pr. A positive allow-list, NOT a
# guard-kill: branches and worktrees are the isolation mechanism, so they pass;
# what is BLOCKED is mutation of the SHARED integration checkout (direct commit,
# HEAD-rewrite) and any push to a protected/integration branch. HEAD-rewrites
# and commits are allowed when the command is scoped to a worktree.
# SPEC: docs/playbooks/pr-workflow.md § 5.
# ---------------------------------------------------------------------------
def _protected_branches() -> set[str]:
    raw = os.environ.get("COS_GIT_PROTECTED_BRANCHES", "production")
    return {b for b in re.split(r"[,\s]+", raw) if b}


def _is_worktree_path(path: str) -> bool:
    if not path:
        return False
    # Resolve symlinks before comparing (Rule 5: macOS /tmp ↔ /private/tmp); a
    # missing tail still resolves its existing prefix, enough for the compare.
    real = os.path.realpath(path)
    if "/.coding-os/worktrees/" in real or "/.coding-os/worktrees/" in path:
        return True
    root = os.environ.get("COS_WORKTREE_ROOT", "")
    if not root:
        return False
    root_real = os.path.realpath(root)
    return real == root_real or real.startswith(root_real.rstrip("/") + "/")


def _current_dir() -> str:
    try:
        return os.getcwd()
    except OSError:
        return ""  # cwd deleted out from under us — fall through to segment checks


def _worktree_scoped(segments: list[str]) -> bool:
    # Worktree scope for a git op with NO explicit -C: the process cwd is a
    # worktree, or a `cd <worktree>` in the command line moved into one. An op
    # WITH -C is scoped per-op from its own target in _evaluate_pr (finding 5).
    cwd = _current_dir()
    if cwd and _is_worktree_path(cwd):
        return True
    for seg in segments:
        toks = _strip_env_vars(_tokenize(seg))
        if toks and toks[0] == "cd" and len(toks) >= 2 and _is_worktree_path(toks[1]):
            return True
    return False


# In-progress merge / cherry-pick cleanup flags — these don't advance a branch.
_SAFE_SEQUENCER_FLAGS = {"--abort", "--continue", "--skip", "--quit"}


def _unqualify_ref(ref: str) -> str:
    # `+refs/heads/main` → `main`, so the fully-qualified refspec form can't slip
    # past a bare-name membership test. `+` (force) is stripped first; only the
    # branch namespace is unwrapped (a `refs/tags/` push targets a tag, not a
    # branch, so it is deliberately left intact).
    ref = ref.lstrip("+")
    if ref.startswith("refs/heads/"):
        return ref[len("refs/heads/"):]
    return ref


def _push_targets(args: list[str], blocked: set[str]) -> bool:
    # `--mirror` / `--all` push every local ref → can update the integration or a
    # protected branch without naming it; treat as a protected-push (finding 15).
    if any(a in {"--mirror", "--all"} for a in args):
        return True
    for a in args:
        if a.startswith("-"):
            continue
        dst = a.rsplit(":", 1)[-1] if ":" in a else a
        if _unqualify_ref(dst) in blocked:  # bare/+force/refs-heads forms all map here
            return True
    return False


def _pr_branch_blocks(args: list[str], blocked: set[str]) -> bool:
    # A `git branch` that creates / force-moves / deletes / renames / copies a
    # BLOCKED branch ref. agents/* create and `-D agents/...` cleanup stay allowed
    # — only a blocked-branch target trips. Worktree scope is irrelevant: branch
    # refs are shared across every worktree via the common dir.
    destructive = any(
        a in {"-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy"}
        for a in args
    )
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return False  # bare `git branch` (list) — no target
    if destructive:
        # delete / rename / copy — any named blocked branch is at risk (rename
        # ONTO main, delete main, …).
        return any(_unqualify_ref(p) in blocked for p in positionals)
    # force-move (`branch -f <b> [start]`) or bare create (`branch <b> [start]`):
    # only the first positional is the ref being written; a blocked startpoint is
    # harmless.
    return _unqualify_ref(positionals[0]) in blocked


def _pr_update_ref_blocks(args: list[str], blocked: set[str]) -> bool:
    # `git update-ref [-d] <ref> [<newvalue> [<oldvalue>]]` rewrites a ref
    # directly. `--stdin` reads ref commands we cannot inspect → fail closed.
    if "--stdin" in args:
        return True
    positionals = [a for a in args if not a.startswith("-")]
    return bool(positionals) and _unqualify_ref(positionals[0]) in blocked


def _git_dir_target(global_tokens: list[str]) -> str | None:
    # The path a git invocation is explicitly pointed at via -C / --work-tree /
    # --git-dir (None = the ambient cwd). Scope is decided per git-op from THIS
    # target, never command-globally, so `cd <wt> && git -C <main> reset` is
    # judged against <main>, not the worktree cwd (finding 5).
    i = 0
    while i < len(global_tokens):
        t = global_tokens[i]
        if t in {"-C", "--work-tree", "--git-dir"} and i + 1 < len(global_tokens):
            return global_tokens[i + 1]
        matched_eq = [p for p in ("--work-tree=", "--git-dir=") if t.startswith(p)]
        if matched_eq:
            return t[len(matched_eq[0]):]
        if t in _GLOBAL_OPTS_WITH_ARG:
            i += 2
            continue
        if t in _GLOBAL_OPTS_NO_ARG or any(t.startswith(p) for p in _GLOBAL_LONG_EQ_PREFIXES):
            i += 1
            continue
        break
    return None


def _evaluate_pr(segments: list[str]) -> tuple[str, str, str]:
    integration = os.environ.get("COS_GIT_INTEGRATION_BRANCH", "main")
    blocked_push = _protected_branches() | {integration}
    fallback_scope = _worktree_scoped(segments)  # cwd/cd, for ops with no -C
    for seg in segments:
        tokens = _strip_env_vars(_tokenize(seg))
        if not tokens or tokens[0] != "git":
            continue
        global_tokens = tokens[1:]
        c_target = _git_dir_target(global_tokens)
        sub = _strip_git_globals(global_tokens)
        if not sub:
            continue
        op_scope = _is_worktree_path(c_target) if c_target is not None else fallback_scope
        reason, message = _pr_check(sub[0], sub[1:], op_scope, blocked_push)
        if reason:
            return "block", reason, message or ""
    return "allow", "", ""


def _pr_check(
    subcmd: str, args: list[str], worktree: bool, blocked_push: set[str]
) -> tuple[str | None, str | None]:
    if subcmd == "push":
        if _push_targets(args, blocked_push):
            return "pr-protected-push", _PR_MSG["protected-push"]
        return None, None
    if subcmd == "commit":
        if worktree:
            return None, None
        return "pr-shared-commit", _PR_MSG["shared-commit"]
    if subcmd in {"reset", "rebase"}:
        reason, _ = _DISPATCH[subcmd](args)
        if reason is None:  # safe form (unstage/path/HEAD, rebase --abort/...)
            return None, None
        if worktree:
            return None, None  # HEAD-rewrite is fine inside an isolated worktree
        return "pr-shared-head-rewrite", _PR_MSG["shared-head"]
    if subcmd in {"merge", "cherry-pick"}:
        # merge/cherry-pick advance the current branch's HEAD — on the shared
        # integration checkout that lands code outside the PR+CI flow. In a
        # worktree they only advance that worktree's own agents/* HEAD.
        if any(a in _SAFE_SEQUENCER_FLAGS for a in args):
            return None, None  # in-progress cleanup, not an advance
        if worktree:
            return None, None
        return "pr-shared-head-rewrite", _PR_MSG["shared-head"]
    if subcmd == "branch":
        if _pr_branch_blocks(args, blocked_push):
            return "pr-protected-ref", _PR_MSG["protected-ref"]
        return None, None  # agents/* create + delete stay allowed
    if subcmd == "update-ref":
        if _pr_update_ref_blocks(args, blocked_push):
            return "pr-protected-ref", _PR_MSG["protected-ref"]
        return None, None
    # checkout / switch / worktree / everything else: branches and worktrees are
    # the pr-mode isolation mechanism — allowed.
    return None, None


_PR_MSG = {
    "shared-commit": (
        "BLOCKED (pr-mode): direct commit on the shared integration checkout.\n"
        "  Every change must be isolated in a worktree.\n"
        "  To fix: 'cos pr open' (or 'cos pr open --adhoc' for no-task work),\n"
        "  then commit inside the worktree.\n"
        "  See docs/playbooks/pr-workflow.md § 5/§6."
    ),
    "shared-head": (
        "BLOCKED (pr-mode): HEAD-rewrite (reset/rebase/merge/cherry-pick) on the\n"
        "shared integration checkout corrupts the always-green integration line.\n"
        "  These are allowed INSIDE a worktree — scope the op with\n"
        "  'git -C <worktree>' or 'cd <worktree> && …'.\n"
        "  See docs/playbooks/pr-workflow.md § 5."
    ),
    "protected-ref": (
        "BLOCKED (pr-mode): this rewrites a protected/integration branch ref\n"
        "directly (git branch -f/-D/-m / git update-ref). Branch refs are shared\n"
        "across every worktree, so this corrupts the integration/production line\n"
        "outside the PR+CI flow — worktree scope is NO protection here.\n"
        "  Agents mutate only their own 'agents/*' branch; land changes via a PR.\n"
        "  See docs/playbooks/pr-workflow.md § 5."
    ),
    "protected-push": (
        "BLOCKED (pr-mode): push targets a protected/integration branch.\n"
        "  Agents push only to their own 'agents/*' branch, then open a PR.\n"
        "  To fix: 'git push --force-with-lease -u origin HEAD' from the\n"
        "  worktree branch, then open the PR ('cos pr open' / 'gh pr create').\n"
        "  See docs/playbooks/pr-workflow.md § 5/§11."
    ),
}


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
