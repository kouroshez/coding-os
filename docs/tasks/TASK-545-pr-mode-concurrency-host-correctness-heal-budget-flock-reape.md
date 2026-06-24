---
id: TASK-545
title: "pr-mode concurrency+host correctness: heal-budget flock + reaper cross-host false-positive death"
swimlane: core
kind: bug
epic: pr-mode-hardening
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-claude-20260624-034200-e9e7
depends_on: []
blocked_by: []
references: []
---
# TASK-545: pr-mode concurrency+host correctness: heal-budget flock + reaper cross-host false-positive death

**Outcome (one sentence):** The .pr-heal-budget.json read-modify-write is serialized by a DEDICATED per-repo flock (not the reap lock, avoiding the _reap_one re-entrancy deadlock) so concurrent agents cannot clobber heal counts; and the reaper treats a dead recorded pid as death evidence ONLY when the presence record's host matches this host, so a live agent on another host is never judged dead and force-removed.

## Read First
- src/cli/pr_commands.py
- tests/test_cli.py
- src/core/board_os/presence.py
- src/core/hooks/_helpers/presence_write.py

## Repro Steps
In src/cli/pr_commands.py, the .pr-heal-budget.json read-modify-write across pr_heal/_heal_budget_save/_heal_budget_clear is unlocked so concurrent agents clobber counts, and _reap_one (already under .pr-reap.lock) calls _heal_budget_clear so reusing the reap lock would deadlock. Separately _session_state uses pid_alive (os.kill host-local) so a live agent on host B is judged dead by a reaper on host A whose pid happens to be free, and its worktree is force-removed.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** concurrent pr heal calls on one repo, **When** each does the heal-budget read-modify-write, **Then** a dedicated .pr-heal.lock flock serializes them and the lost-update is gone; fcntl=None (Windows) degrades to a no-op.
- **Given** pr_reap holds .pr-reap.lock and _reap_one calls _heal_budget_clear, **When** the budget mutator takes its lock, **Then** it uses the dedicated lock (never .pr-reap.lock) so no deadlock occurs.
- **Given** a presence record with no ended_at and a recorded pid whose host differs from this host, **When** _session_state evaluates liveness, **Then** the foreign-host record is treated as live (fail safe) and not reaped; same-host dead pid is still reaped.
- **Given** presence records now carry host, **When** existing presence tests run, **Then** session_presence/session_inventory tests still pass.
- **Given** the matrix verify, **When** `uv run pytest tests/test_cli.py -q` runs, **Then** it passes.

## Work Log
- 2026-06-24 [claude]: Edit presence_write.py
- 2026-06-24 [claude]: Edit presence_write.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: Edit pr_commands.py
- 2026-06-24 [claude]: commit bd61a58904 — fix(pr-mode): cos-env reads git_settings via jq OR python3 (no jq hard-dep)
- 2026-06-24 [claude]: Used a DEDICATED .pr-heal.lock (never .pr-reap.lock) for the heal-budget flock because _reap_one already holds the…
- 2026-06-24 [claude]: Edit TASK-547-cos-env-claude-project-dir-gates-off-git-native-worktree-det.md
