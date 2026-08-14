"""branch-guard — pr-mode policy: protect the SHARED checkout, not the branch.

A positive allow-list, not a guard-kill. Branches and worktrees are the pr-mode
isolation mechanism, so creating them passes; what is blocked is mutation of the
shared integration checkout (direct commit, HEAD-rewrite) and any push to a
protected or integration branch. HEAD-rewrites and commits pass when the command
is scoped to a worktree — decided per git-op from that op's own `-C` target, not
command-globally. SPEC: docs/playbooks/pr-workflow.md § 5.
"""

from __future__ import annotations

import os

from branch_guard_refs import (
    _matches_blocked_ref,
    _pr_branch_blocks,
    _pr_update_ref_blocks,
    _protected_branches,
    _unqualify_ref,
    _update_ref_positionals,
)
from branch_guard_trunk import _DISPATCH, _check_symbolic_ref
from git_command_parse import is_git_word, resolve_command, strip_env_vars, strip_git_globals

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
            kv = t[len("-c=") :]
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
            return t[len(matched_eq[0]) :]
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
        # Sanctioned local_autonomous land: `cos pr land` exports COS_PR_LAND
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
