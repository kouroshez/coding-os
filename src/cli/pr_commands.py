"""cos pr — pr-mode multi-agent git executor (TASK-517).

Thin, idempotent subcommands the agent drives from its OWN turn loop (never a
kernel daemon — hooks can't loop, MCP polling blocks the server):

    cos pr preflight   — capability check (remote + gh + required CI); degrade signal
    cos pr open        — isolate: claim/derive a session, create a worktree + agents/* branch
    cos pr submit      — publish: rebase onto FETCH_HEAD, sha-pinned lease push, PR, auto-merge
    cos pr status      — list this repo's pr-mode worktrees / branches / open PRs
    cos pr cleanup     — remove the worktree + delete the branch + prune

All gh-coupled code lives here in src/cli (P2/P8 — src/core stays agent/host
agnostic; it reaches every consumer via live symlinks). When a capability is
missing the executor degrades to the trunk publish path instead of failing
mid-loop. SPEC: docs/playbooks/pr-workflow.md.

This module is the facade. Importing it registers every subcommand on the
group, which is why the five command modules are imported for their side
effect and never referenced by name.
"""

from __future__ import annotations

from cli import _pr_cleanup, _pr_inspect, _pr_open, _pr_publish, _pr_reap  # noqa: F401
from cli._pr_shared import pr_group

__all__ = ["pr_group"]
