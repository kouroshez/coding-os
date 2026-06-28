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

import fnmatch
import json
import os
import re
import sys

from git_command_parse import (
    abbrev_resolves,
    command_groups,
    commit_flags,
    is_git_word,
    normalize,
    recover_indirect_commands,
    resolve_command,
    strip_env_vars,
    strip_git_globals,
)

# Pre-subcommand git globals, kept local for the pr-mode-specific _git_dir_target
# below (the shared tokenizer's strip_git_globals already drops them for the
# subcommand lookup; this set lets _git_dir_target read the `-C`/--work-tree target).
_GLOBAL_OPTS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
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
_GLOBAL_LONG_EQ_PREFIXES = ("--git-dir=", "--work-tree=", "--namespace=", "-c=")


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
    # Plain create form `git branch <name> [<startpoint>]` — trunk forbids new
    # branches.
    if args and not args[0].startswith("-"):
        return "branch-create", _MSG["branch-create"]
    # Force-rewrite / rename / copy / delete TARGETING the integration or a
    # protected ref (branch -f/-M/-C/-D main) corrupts the shared line — block at
    # parity with pr-mode (BG-1), reusing its refspec-normalizing blocker. Other
    # flagged forms (-d/-m/-v/--list on a feature branch) stay allowed.
    if _pr_branch_blocks(args, _trunk_protected_refs()):
        return "protected-ref-rewrite", _MSG["protected-ref-rewrite"]
    return None, None


def _check_update_ref(args: list[str]) -> tuple[str | None, str | None]:
    # `git update-ref` writes a ref directly; trunk previously had no checker for
    # it (BG-2). Block writes/deletes of the integration/protected line OR HEAD
    # (a direct HEAD move is an unguarded reset). Reuse pr-mode's blocker — it
    # fails closed on --stdin — and add the HEAD guard on top.
    positionals = _update_ref_positionals(args)
    if positionals and _unqualify_ref(positionals[0]) == "HEAD":
        return "protected-ref-rewrite", _MSG["protected-ref-rewrite"]
    if _pr_update_ref_blocks(args, _trunk_protected_refs()):
        return "protected-ref-rewrite", _MSG["protected-ref-rewrite"]
    return None, None


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
    # Path-mode reset (`-p`, `--patch`, `--pathspec-from-file`, `--` separator)
    # stages/unstages hunks — it NEVER moves HEAD, so it is always safe. git
    # resolves any unambiguous prefix, so test `--pa…`/`--pat…` etc. by resolution,
    # not a literal (`git reset --pa` → --patch was a bypass of the old `in {…}` set).
    for a in args:
        if a == "--" or a == "-p":
            return None, None
        if a.startswith("--") and (
            abbrev_resolves(a, "--patch", _RESET_LONGS)
            or abbrev_resolves(a, "--pathspec-from-file", _RESET_LONGS)
            or abbrev_resolves(a, "--pathspec-file-nul", _RESET_LONGS)
        ):
            return None, None
    # Strip ALL leading mode flags incl. abbreviations (`--har`→--hard,
    # `--so`→--soft) and any other non-positional option, so the first POSITIONAL
    # is reached — the old code stripped only a hardcoded literal set, so `--har`
    # read as the first positional, hit the `startswith("--")` path-restore arm,
    # and the HEAD-move slipped (the bypass this closes).
    rest = [a for a in args if not a.startswith("-")]
    if not rest:
        return None, None  # `git reset [--mode]` with no target — unstage, no HEAD move
    first = rest[0]
    if first == "HEAD":
        return None, None  # `reset HEAD` / `reset --mode HEAD` — HEAD does not move
    return "reset-head-rewrite", _MSG["reset"]


# `git reset`'s long options — the competitor set for prefix disambiguation. A
# mode/HEAD-mover vs a path-mode marker only needs the options that share a prefix
# with the path-mode ones, but the full short list keeps `abbrev_resolves` honest
# if git adds a colliding option (e.g. a future `--pat*`).
_RESET_LONGS = frozenset(
    {
        "--soft", "--mixed", "--hard", "--merge", "--keep", "--patch",
        "--quiet", "--no-quiet", "--refresh", "--no-refresh", "--stdin",
        "--pathspec-from-file", "--pathspec-file-nul", "--intent-to-add",
        "--recurse-submodules",
    }
)


# Accepts `-` (previous branch/ref) as a positional arg, plus any
# token that doesn't start with `-`.
def _first_positional(args: list[str]) -> str | None:
    for a in args:
        if a == "-":
            return a
        if not a.startswith("-"):
            return a
    return None


def _check_commit(args: list[str]) -> tuple[str | None, str | None]:
    # Trunk requires explicit-path commits: `git commit -a/--all` stages every
    # tracked modification, sweeping a concurrent session's WIP into this commit
    # (git-workflow.md § The rule). Block the -a forms; `--amend`, `--author`,
    # `--allow-empty`, `-m`, and explicit-path commits stay allowed.
    short, longs = commit_flags(args)
    if "a" in short or "--all" in longs:
        return "commit-all-sweep", _MSG["commit-all"]
    return None, None


def _check_filter(args: list[str]) -> tuple[str | None, str | None]:
    # `git filter-branch` / `filter-repo` rewrite the ENTIRE history of the
    # current branch (= main in trunk) — every published commit is replaced,
    # orphaning every peer. No safe in-place form on a shared trunk.
    return "history-rewrite", _MSG["history-rewrite"]


def _check_symbolic_ref(args: list[str]) -> tuple[str | None, str | None]:
    # `git symbolic-ref HEAD <ref>` repoints HEAD (== a branch switch) and
    # `--delete` detaches it — both move off main. A read form
    # (`symbolic-ref HEAD`, `-q`, `--short`) names no target → allowed.
    if any(a in {"-d", "--delete"} for a in args):
        return "symbolic-ref-write", _MSG["protected-ref-rewrite"]
    positionals = [a for a in args if not a.startswith("-")]
    if len(positionals) >= 2:  # <name> <new-target> → a write
        return "symbolic-ref-write", _MSG["protected-ref-rewrite"]
    return None, None


_DISPATCH = {
    "checkout": _check_checkout,
    "switch": _check_switch,
    "branch": _check_branch,
    "update-ref": _check_update_ref,
    "worktree": _check_worktree,
    "reset": _check_reset,
    "rebase": _check_rebase,
    "commit": _check_commit,
    "filter-branch": _check_filter,
    "filter-repo": _check_filter,
    "symbolic-ref": _check_symbolic_ref,
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
    "protected-ref-rewrite": (
        "BLOCKED: this rewrites the protected integration ref directly\n"
        "(git branch -f/-M/-C/-D main, git update-ref refs/heads/main or HEAD).\n"
        "In trunk mode that clobbers the shared main line and every peer's history.\n"
        "\n"
        "  To undo a published commit: 'git revert <sha>' — a new commit that\n"
        "  preserves history. Feature-branch admin must not target main.\n"
        "  See src/core/rules/git-workflow.md for the full rule."
    ),
    "commit-all": (
        "BLOCKED: 'git commit -a/--all' stages every tracked modification —\n"
        "in a multi-session checkout that sweeps another session's WIP into\n"
        "your commit. Trunk requires EXPLICIT paths.\n"
        "\n"
        "  To fix: stage what you mean, then 'git commit <explicit paths>'.\n"
        "  ('--amend', '--author', '--allow-empty', '-m' stay allowed.)\n"
        "  See src/core/rules/git-workflow.md § The rule."
    ),
    "history-rewrite": (
        "BLOCKED: 'git filter-branch' / 'filter-repo' rewrites the ENTIRE\n"
        "history of the current branch — on trunk that replaces every published\n"
        "commit on main and orphans every peer's work.\n"
        "\n"
        "  To undo specific commits: 'git revert <sha>' (new commits, history\n"
        "  preserved). A genuine history scrub is a human, force-push operation\n"
        "  done off the shared trunk. See src/core/rules/git-workflow.md."
    ),
}


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


def _evaluate_trunk(groups: list[list[str]]) -> tuple[str, str, str]:
    for g in groups:
        # resolve_command strips a `VAR=val`/`env …`/`{` prefix; is_git_word accepts a
        # path-qualified `/usr/bin/git`. `g` is already tokenized by command_groups.
        _env, tokens = resolve_command(g)
        if not tokens or not is_git_word(tokens[0]):
            continue
        tokens = strip_git_globals(tokens[1:])
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


def _trunk_protected_refs() -> set[str]:
    # The refs trunk mode refuses to force-rewrite / rename / delete: the
    # integration line (main) + any protected branch — the SAME set pr-mode
    # guards, so neither mode is weaker than the other on ref integrity (BG-1/2).
    integration = os.environ.get("COS_GIT_INTEGRATION_BRANCH", "main")
    return _protected_branches() | {integration}


def _is_worktree_path(path: str) -> bool:
    if not path:
        return False
    # Resolve symlinks AND `..` segments before comparing (Rule 5: macOS /tmp ↔
    # /private/tmp); test ONLY the resolved path — a raw arm let a spoof like
    # `.../worktrees/x/../../../realmain` (resolves INTO the shared checkout) pass.
    real = os.path.realpath(path)
    if "/.coding-os/worktrees/" in real:
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


def _worktree_scoped(groups: list[list[str]]) -> bool:
    # Worktree scope for a git op with NO explicit -C: the process cwd is a
    # worktree, or a `cd <worktree>` in the command line moved into one. An op
    # WITH -C is scoped per-op from its own target in _evaluate_pr (finding 5).
    cwd = _current_dir()
    if cwd and _is_worktree_path(cwd):
        return True
    for g in groups:
        toks = strip_env_vars(g)
        if toks and toks[0] == "cd" and len(toks) >= 2 and _is_worktree_path(toks[1]):
            return True
    return False


# In-progress merge / cherry-pick cleanup flags — these don't advance a branch.
_SAFE_SEQUENCER_FLAGS = {"--abort", "--continue", "--skip", "--quit"}


def _unqualify_ref(ref: str) -> str:
    # Map a `+force` / `refs/heads/` / `heads/` refspec to its bare branch name so
    # it can't slip past a bare-name membership test. The `heads/` shorthand is a
    # valid push destination git resolves to `refs/heads/` server-side, so it MUST
    # normalize too (`refs/tags/` left intact — it's a tag).
    ref = ref.lstrip("+")
    # Strip the ref-namespace prefix REPEATEDLY: a doubled `refs/heads/refs/heads/x`
    # (or `heads/heads/x`) must normalize to bare `x`, else the nested form slips the
    # membership test and writes a protected branch (D1).
    while True:
        if ref.startswith("refs/heads/"):
            ref = ref[len("refs/heads/"):]
        elif ref.startswith("heads/"):
            ref = ref[len("heads/"):]
        else:
            return ref


def _matches_blocked_ref(ref: str, blocked: set[str]) -> bool:
    if not ref:
        return False
    bare = _unqualify_ref(ref)
    return any(fnmatch.fnmatchcase(bare, _unqualify_ref(pattern)) for pattern in blocked)


def _push_targets(args: list[str], blocked: set[str]) -> bool:
    # `--mirror` / `--all` push every local ref → can update the integration or a
    # protected branch without naming it; treat as a protected-push (finding 15).
    if any(a in {"--mirror", "--all"} for a in args):
        return True
    for a in args:
        if a.startswith("-"):
            continue
        dst = a.rsplit(":", 1)[-1] if ":" in a else a
        if _matches_blocked_ref(dst, blocked):  # bare/+force/refs-heads forms all map here
            return True
    return False


def _push_names_explicit_dst(args: list[str]) -> bool:
    # True when the push names at least one explicit destination ref that is not
    # `HEAD` — i.e. it is provably NOT a bare/`HEAD`-only push that would advance
    # whatever branch is currently checked out. `git push [remote] [refspec...]`:
    # the first positional is the remote, the rest are refspecs.
    positionals = [a for a in args if not a.startswith("-")]
    for refspec in positionals[1:]:
        dst = refspec.rsplit(":", 1)[-1] if ":" in refspec else refspec
        if _unqualify_ref(dst) != "HEAD":
            return True
    return False


def _has_unsafe_push_default(global_tokens: list[str]) -> bool:
    # `git -c push.default=matching push` makes a bare push update every same-name
    # branch (incl. the integration line) and `current` pushes whatever is checked
    # out — both can advance a blocked branch a refspec check never sees. The `-c`
    # global is stripped before _pr_check, so it is inspected here on the raw tokens.
    i = 0
    while i < len(global_tokens):
        t = global_tokens[i]
        kv = None
        if t == "-c" and i + 1 < len(global_tokens):
            kv = global_tokens[i + 1]
            i += 2
        elif t.startswith("-c="):
            kv = t[len("-c="):]
            i += 1
        else:
            i += 1
            continue
        key, _, val = kv.partition("=")
        if key.strip() == "push.default" and val.strip() in {"matching", "current"}:
            return True
    return False


def _created_ref(subcmd: str, args: list[str]) -> str:
    # The branch ref a checkout/switch force-creates or resets via -b/-B (checkout)
    # or -b/-B/-c/-C (switch). "" when none (a plain switch onto an existing branch
    # writes no ref). Plain `git checkout main` is a read-only switch → not a ref write.
    flags = {"-b", "-B"} if subcmd == "checkout" else {"-b", "-B", "-c", "-C"}
    for i, a in enumerate(args):
        if a in flags and i + 1 < len(args):
            return _unqualify_ref(args[i + 1])
    return ""


def _worktree_add_branch(args: list[str]) -> str:
    # The branch a `git worktree add` creates (`-b/-B <name>`) or checks out (the
    # optional 2nd positional `git worktree add <path> <branch>`). "" when detached
    # or based on a remote ref. Blocking this keeps the integration/protected line
    # out of any worktree, so a worktree's HEAD is always a non-blocked branch.
    for i, a in enumerate(args):
        if a in {"-b", "-B"} and i + 1 < len(args):
            return _unqualify_ref(args[i + 1])
    positionals = [a for a in args if not a.startswith("-")]
    if len(positionals) >= 2:  # add <path> <branch>
        return _unqualify_ref(positionals[1])
    return ""


def _update_ref_positionals(args: list[str]) -> list[str]:
    # Ref operands of `git update-ref`, dropping `-m <reason>`'s value (a reflog
    # message, not a ref) so `update-ref -m main refs/heads/feature …` reads the
    # ref operand, not the message (review finding B/D).
    out: list[str] = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in {"-m", "--reflog-message"}:
            skip = True
            continue
        if not a.startswith("-"):
            out.append(a)
    return out


def _is_branch_filter_flag(arg: str) -> bool:
    # `git branch` selectors whose ref/pattern operand is a FILTER, not a ref to
    # write — present ⇒ a read-only list query, so a protected ref named as the
    # filter must NOT block (review finding C: `branch --contains/--merged main`).
    return arg.split("=", 1)[0] in {
        "--contains", "--no-contains", "--merged", "--no-merged",
        "--points-at", "--list",
    }


def _pr_branch_blocks(args: list[str], blocked: set[str]) -> bool:
    # Worktree scope is irrelevant — branch refs are shared across worktrees via
    # the common dir, so a blocked target trips even from a worktree (agents/*
    # create + `-D agents/...` cleanup still pass: only a blocked target trips).
    if any(_is_branch_filter_flag(a) for a in args):
        return False  # read-only list/filter form — the ref operand is a filter
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return False
    # Copy `-c/-C` writes only the TARGET (last positional); its source ref is
    # read, not modified — `branch -c main backup` must not trip on `main`.
    if any(a in {"-c", "-C", "--copy"} for a in args):
        return _matches_blocked_ref(positionals[-1], blocked)
    # Delete `-d/-D` and rename `-m/-M` put EVERY named ref at risk.
    if any(a in {"-d", "-D", "--delete", "-m", "-M", "--move"} for a in args):
        return any(_matches_blocked_ref(p, blocked) for p in positionals)
    # Plain / force create-or-move: only the written ref (first positional).
    return _matches_blocked_ref(positionals[0], blocked)


def _pr_update_ref_blocks(args: list[str], blocked: set[str]) -> bool:
    if "--stdin" in args:  # feeds ref commands we can't inspect → fail closed
        return True
    positionals = _update_ref_positionals(args)
    return bool(positionals) and _matches_blocked_ref(positionals[0], blocked)


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


def _evaluate_pr(groups: list[list[str]]) -> tuple[str, str, str]:
    integration = os.environ.get("COS_GIT_INTEGRATION_BRANCH", "main")
    blocked_push = _protected_branches() | {integration}
    fallback_scope = _worktree_scoped(groups)  # cwd/cd, for ops with no -C
    for g in groups:
        _env, tokens = resolve_command(g)
        if not tokens or not is_git_word(tokens[0]):
            continue
        global_tokens = tokens[1:]
        c_target = _git_dir_target(global_tokens)
        sub = strip_git_globals(global_tokens)
        if not sub:
            continue
        op_scope = _is_worktree_path(c_target) if c_target is not None else fallback_scope
        reason, message = _pr_check(sub[0], sub[1:], op_scope, blocked_push)
        if not reason and sub[0] == "push" and _has_unsafe_push_default(global_tokens):
            reason, message = "pr-protected-push", _PR_MSG["protected-push"]
        if reason:
            return "block", reason, message or ""
    return "allow", "", ""


def _pr_check(
    subcmd: str, args: list[str], worktree: bool, blocked_push: set[str]
) -> tuple[str | None, str | None]:
    if subcmd == "push":
        if _push_targets(args, blocked_push):
            return "pr-protected-push", _PR_MSG["protected-push"]
        # A bare / HEAD-only push from the shared checkout advances the integration
        # line (its current branch is integration), outside PR+CI. Allow only when
        # worktree-scoped (HEAD is agents/* there) or it names an explicit non-blocked
        # destination refspec — the sanctioned `cos pr submit` does both.
        if not worktree and not _push_names_explicit_dst(args):
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
        # advancing HEAD on the shared checkout lands code outside PR+CI; a
        # worktree only advances its own agents/* HEAD, so it's allowed.
        if any(a in _SAFE_SEQUENCER_FLAGS for a in args):
            return None, None  # in-progress cleanup, not an advance
        if worktree:
            return None, None
        # Sanctioned local_autonomous land (TASK-614): `cos pr land` exports COS_PR_LAND
        # into the merge subprocess's ENV, so the guard reads it from os.environ. An
        # agent's inline `COS_PR_LAND=1 git merge …` cannot forge it — resolve_command
        # strips the inline assignment into _env, never os.environ (same protection as
        # the COS_ALLOW_FORCE_PUSH_MAIN prefix guard).
        if os.environ.get("COS_PR_LAND") == "1":
            return None, None
        return "pr-shared-head-rewrite", _PR_MSG["shared-head"]
    if subcmd == "branch":
        if _pr_branch_blocks(args, blocked_push):
            return "pr-protected-ref", _PR_MSG["protected-ref"]
        return None, None  # agents/* create + delete stay allowed
    if subcmd == "update-ref":
        positionals = _update_ref_positionals(args)
        if not worktree and positionals and _unqualify_ref(positionals[0]) == "HEAD":
            return "pr-shared-head-rewrite", _PR_MSG["shared-head"]
        if _pr_update_ref_blocks(args, blocked_push):
            return "pr-protected-ref", _PR_MSG["protected-ref"]
        return None, None
    if subcmd in {"fetch", "pull"}:
        # `git fetch/pull origin x:main` / `:production` writes a blocked LOCAL ref
        # (pull is fetch+merge with identical refspec syntax); legit pr-mode fetches
        # never use a colon, so a refspec with one whose destination is blocked is the
        # leak. Refs are global → scope is moot (review finding 3).
        for a in args:
            if a.startswith("-") or ":" not in a:
                continue
            if _matches_blocked_ref(a.rsplit(":", 1)[-1], blocked_push):
                return "pr-protected-ref", _PR_MSG["protected-ref"]
        return None, None
    if subcmd in {"checkout", "switch"}:
        # -b/-B (checkout) or -b/-B/-c/-C (switch) force-create/reset a branch ref;
        # a blocked target is a protected-ref write (refs are global, like branch -f).
        if _matches_blocked_ref(_created_ref(subcmd, args), blocked_push):
            return "pr-protected-ref", _PR_MSG["protected-ref"]
        return None, None
    if subcmd == "worktree":
        # `git worktree add -b|-B <blocked>` or `... <path> <blocked>` would create or
        # check the integration/protected line out into a worktree — refuse it so a
        # worktree HEAD is always a non-blocked branch (keeps the push rule above safe).
        if (
            args
            and args[0] == "add"
            and _matches_blocked_ref(_worktree_add_branch(args[1:]), blocked_push)
        ):
            return "pr-protected-ref", _PR_MSG["protected-ref"]
        return None, None
    if subcmd in {"filter-branch", "filter-repo"}:
        # History rewrite touches the shared object db + refs even from a worktree —
        # always blocked (parity with trunk's history-rewrite guard, BG-1/BG-2).
        return "pr-shared-head-rewrite", _PR_MSG["shared-head"]
    if subcmd == "symbolic-ref":
        # Repointing a worktree's OWN HEAD is isolated; on the shared checkout it
        # is an off-integration switch outside PR+CI.
        if _check_symbolic_ref(args)[0] is None:
            return None, None
        return (None, None) if worktree else ("pr-shared-head-rewrite", _PR_MSG["shared-head"])
    # everything else: branches and worktrees are the pr-mode isolation mechanism — allowed.
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
