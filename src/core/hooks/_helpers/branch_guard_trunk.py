"""branch-guard — trunk-mode policy: the ops that move HEAD or a branch ref.

One checker per git subcommand, a dispatch table keyed on the subcommand, and
the operator-facing message for each rule id. Every checker takes the arguments
AFTER the git globals are stripped and returns `(reason, message)` — `(None,
None)` means the form is one of the documented safe escape hatches.

The pr-mode module imports the reset/rebase/symbolic-ref checkers from here,
because "is this even a HEAD-mover" has the same answer in both workflows; this
module imports only the shared ref leaf, so the dependency stays one-way.
"""

from __future__ import annotations

from branch_guard_refs import (
    _pr_branch_blocks,
    _pr_update_ref_blocks,
    _trunk_protected_refs,
    _unqualify_ref,
    _update_ref_positionals,
)
from git_command_parse import (
    abbrev_resolves,
    commit_flags,
    is_git_word,
    resolve_command,
    strip_git_globals,
)


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
        "--soft",
        "--mixed",
        "--hard",
        "--merge",
        "--keep",
        "--patch",
        "--quiet",
        "--no-quiet",
        "--refresh",
        "--no-refresh",
        "--stdin",
        "--pathspec-from-file",
        "--pathspec-file-nul",
        "--intent-to-add",
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
