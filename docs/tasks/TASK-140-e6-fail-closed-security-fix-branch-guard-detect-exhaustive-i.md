---
id: TASK-140
title: "E6: fail-closed security fix — branch-guard + detect-exhaustive-intent capture helper crashes (no silent fail-open)"
swimlane: infra
kind: security
epic: observability-eye
labels: [observability, hooks, fail-closed, ready]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-05
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-140: E6: fail-closed security fix — branch-guard + detect-exhaustive-intent capture helper crashes (no silent fail-open)

**Outcome (one sentence):** branch-guard.sh stops silently allowing on helper crash — it captures the helper stderr to the eye (cos_say error) and fails CLOSED (the command is already known git-related via the fast-skip) instead of defaulting to allow; detect-exhaustive-intent.sh logs helper crashes at error level instead of a silent skip.

## Read First
- docs/engineering/observability-eye.md
- src/core/hooks/branch-guard.sh
- src/core/hooks/_helpers/branch_guard_check.py
- src/core/hooks/cos-env.sh

## Threat Model
A PreToolUse:Bash guard gating branch-creation / HEAD-rewriting git ops (protects trunk integrity + peer-session commits across every consumer via live symlink). Pre-fix failure mode: if branch_guard_check.py crashes (corrupt helper, missing python3, dep break), the hook piped stderr to /dev/null and defaulted to verdict=allow — a security control silently stopped guarding with the crash recorded nowhere, letting branch sprawl / peer-HEAD-clobbering commands through unnoticed. Trigger is operational (a helper regression), not adversarial; impact is silent loss of a git-safety control fleet-wide. The fix is fail-closed-and-loud: the helper only runs for git commands (post fast-skip), so failing closed has no non-git blast radius.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** branch_guard_check.py exits non-zero (simulated via a failing python3 on PATH) for a git command
- **When** branch-guard.sh evaluates that command
- **Then** the hook fails CLOSED (exit 2) with an actionable remediation message and emits a cos_say error carrying the captured helper stderr (never /dev/null); a non-git Bash command still exits 0 (no DoS); detect-exhaustive-intent.sh emits a cos_say error on helper crash instead of a silent skip; and make verify-hooks passes

## Work Log
- 2026-06-05 [claude]: Fixed fail-OPEN inversion: branch-guard.sh now captures helper stdout+stderr, fails CLOSED (exit 2) on helper crash for 
