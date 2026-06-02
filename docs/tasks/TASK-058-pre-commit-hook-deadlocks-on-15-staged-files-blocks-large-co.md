---
id: TASK-058
title: "pre-commit hook deadlocks on ~15+ staged files — blocks large commits + holds index.lock"
swimlane: core
kind: bug
epic: null
labels: []
status: testing
priority: P1
appetite: "1d"
created: 2026-06-01
started: 2026-06-01
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-058: pre-commit hook deadlocks on ~15+ staged files — blocks large commits + holds index.lock

**Outcome (one sentence):** A multi-file commit (15+ staged files) completes without hanging; .git/hooks/pre-commit → pre_commit_batch.py never deadlocks or holds .git/index.lock indefinitely.

## Read First
- src/core/hooks/_helpers/pre_commit_batch.py
- src/scripts/install-git-hooks.sh
- src/core/hooks/cos-env.sh
- docs/tasks/audits/audit-roles-selection-panelscope.md

## Repro Steps
1. Stage 15+ files in one commit (e.g. a regen that touches many golden fixtures + adapter templates): `git commit <18 paths> -m "…"`.
2. The git-level `.git/hooks/pre-commit` runs `_helpers/pre_commit_batch.py`, which spawns 2 subprocess hooks per staged file (`block-bad-patterns.sh`, `block-migration-conflict.sh`), each sourcing `cos-env.sh`.
Expected: pre-commit scans all files and the commit completes in a few seconds.
Actual: the `git commit` process hangs in the pre-commit hook (observed: PID alive, CPU ≈ 0.00, frozen indefinitely), leaving `.git/index.lock` held — which then blocks every subsequent commit AND `git push` in the shared checkout until the hung process is killed and the stale lock removed. Workaround used in TASK-057: split into batches of ≤12 files (each batch passes). `git commit --no-verify` is NOT a workaround — `block-secrets.sh` (PreToolUse) blocks `--no-verify`.

Observed during TASK-055/057: an 18-file commit (`b6jf1rpe1`) and a 12-file codex-golden commit both hung in `pre-commit`; the same symptom was initially misattributed to a "concurrent peer session" before being traced to the hook itself.

## Hypotheses (verify before fixing)
1. **subprocess pipe deadlock:** `_run_hook` uses `subprocess.run(..., input=envelope, capture_output=True, timeout=15)`. If a delegate hook (or `cos-env.sh` sourced inside it) spawns a grandchild that inherits and holds the stdout/stderr pipe open, `capture_output` can block past the 15s timeout, or the timeout's SIGTERM doesn't reach the grandchild → parent waits forever. The file's own docstring claims this replaced a bash fork-bomb, but the Python rewrite may still inherit the same grandchild-pipe issue.
2. **cos-env.sh cost × N:** each of the 2N subprocesses re-sources `cos-env.sh` (panel-id resolution, env detection). At N=18 that's 36 cold bash+source invocations; if any does blocking I/O (e.g. reads stdin, waits on a lock, or calls git) under the commit's restricted hook env, it can serialize/deadlock.
3. **git invocation under hook env:** if any sourced helper runs a `git` command while the index.lock is held by the parent commit, it blocks waiting for the lock the parent will never release → classic self-deadlock.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** 20+ staged files (mix of .py/.sh/.md/.json), **When** `git commit` runs the pre-commit hook, **Then** it completes in <10s and never leaves `.git/index.lock` behind.
- **Given** a delegate hook that would block on stdin/grandchild pipe, **When** `pre_commit_batch.py` runs it, **Then** the 15s timeout actually terminates the whole process group (no orphaned grandchild holding the pipe).
- **Given** the root cause is identified, **Then** a regression test (or a documented manual repro) exercises a 20-file commit and asserts no hang.
- **Given** the fix, **Then** `make verify-hooks` clean and a real 20-file commit in this repo succeeds end-to-end.

## Work Log
- 2026-06-02 [claude]: Root cause = subprocess pipe-inheritance deadlock in _run_hook (hypothesis 1): capture_output pipe held open by backgrou
