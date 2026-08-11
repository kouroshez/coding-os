"""branch-guard — ref-name primitives shared by both workflow policies.

Branch refs are global: they are visible from every worktree, so a rule about
WHICH ref a command writes reads the same in trunk mode and in pr mode. This
module owns that half — the protected-ref set, refspec normalization, and the
`git branch` / `git update-ref` argument readers that decide whether a command
writes a protected name. A leaf: it imports neither policy module.
"""

from __future__ import annotations

import fnmatch
import os
import re


def _protected_branches() -> set[str]:
    raw = os.environ.get("COS_GIT_PROTECTED_BRANCHES", "production")
    return {b for b in re.split(r"[,\s]+", raw) if b}


def _trunk_protected_refs() -> set[str]:
    # The refs trunk mode refuses to force-rewrite / rename / delete: the
    # integration line (main) + any protected branch — the SAME set pr-mode
    # guards, so neither mode is weaker than the other on ref integrity (BG-1/2).
    integration = os.environ.get("COS_GIT_INTEGRATION_BRANCH", "main")
    return _protected_branches() | {integration}


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
            ref = ref[len("refs/heads/") :]
        elif ref.startswith("heads/"):
            ref = ref[len("heads/") :]
        else:
            return ref


def _matches_blocked_ref(ref: str, blocked: set[str]) -> bool:
    if not ref:
        return False
    bare = _unqualify_ref(ref)
    return any(fnmatch.fnmatchcase(bare, _unqualify_ref(pattern)) for pattern in blocked)


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
        "--contains",
        "--no-contains",
        "--merged",
        "--no-merged",
        "--points-at",
        "--list",
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
