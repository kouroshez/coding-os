---
id: TASK-969
title: "Close the hook parser/stdin fail-open class: perl-free stdin, discipline gates on cos_json_field, degraded-parser tests"
swimlane: core
kind: bug
epic: null
labels: [hooks, fail-closed, P0, ready]
status: complete
priority: P0
appetite: 1d
created: 2026-08-14
started: 2026-08-14
completed: 2026-08-14
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-969: Close the hook parser/stdin fail-open class: perl-free stdin, discipline gates on cos_json_field, degraded-parser tests

**Outcome (one sentence):** Every enforcement hook reaches the same verdict whether or not `jq`/`perl` are on PATH, so a missing parser can never turn a BLOCK into a silent allow.

## Read First
- docs/engineering/observability-eye.md § 5 (I3, I8)
- src/core/hooks/_cos_env_io.sh
- tests/test_hooks_fail_closed.py

## Repro Steps
Sandbox PATH = every real PATH entry symlinked minus `jq` (python3 + perl present):

| hook | payload | no-jq | with-jq |
|---|---|---|---|
| `enforce-doc-anchor.sh` | Write `src/core/thinking_os/zz.py` | 0 | 2 |
| `enforce-skill.sh` | same | 0 | 2 |
| `enforce-task-start.sh` | same | 0 | 2 |
| `branch-guard.sh` | `git checkout -b feature/x` | 127 | 2 |

Second, orthogonal repro — PATH minus `perl` (jq + python3 present):
`block-dangerous-commands.sh` on `git push --force origin main` exits **0**, because
`cos_read_stdin_bounded` is perl-only and its `|| true` turns "no perl" into "empty payload".

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a PATH without `jq` (python3 present), **When** each blocking hook runs on a payload it blocks with jq, **Then** it exits 2 with the same message.
- **Given** a PATH without `perl`, **When** any hook reads its stdin envelope, **Then** it still receives the payload and reaches its with-perl verdict.
- **Given** a PATH without `jq`, `perl` **and** `python3`, **When** a harm gate runs, **Then** it exits 2 (the I8 no-parser floor), overridable only by `COS_ALLOW_MISSING_DEPS=1`.
- **Given** `cos doctor --bootstrap`, **When** it runs, **Then** the JSON/stdin parser prerequisite is reported alongside bash/git/python/sed/uv.
- **Given** `tests/test_hooks_fail_closed.py`, **When** it runs, **Then** it covers the degraded matrix (no-jq, no-perl, no-parser), not only the no-jq-AND-no-python3 floor.

## Work Log
- 2026-08-14 [claude]: Edit observability-eye.md
- 2026-08-14 [claude]: Edit read_stdin.py
- 2026-08-14 [claude]: Edit _cos_env_io.sh
- 2026-08-14 [claude]: Edit list_blocking_rawjq.py
- 2026-08-14 [claude]: Edit list_blocking_rawjq.py
- 2026-08-14 [claude]: Edit migrate_jq.py
- 2026-08-14 [claude]: Edit _cos_env_io.sh
- 2026-08-14 [claude]: Edit test_hooks_fail_closed.py
- 2026-08-14 [claude]: Edit test_hooks_fail_closed.py
- 2026-08-14 [claude]: Edit _cos_env_io.sh
- 2026-08-14 [claude]: Edit _cos_env_io.sh
- 2026-08-14 [claude]: Edit msg1.txt
- 2026-08-14 [claude]: commit caabfce692 — fix(hooks): degrade stdin read perl -> python3 -> cat so gates never fail open
- 2026-08-14 [claude]: Closed the perl-only stdin fail-open (caabfce6): cos_read_stdin_bounded now degrades perl -> python3 -> cat. Proven…
- 2026-08-14 [claude]: Edit branch-guard.sh
- 2026-08-14 [claude]: Edit migrate_jq2.py
- 2026-08-14 [claude]: Edit enforce-graph-context.sh
- 2026-08-14 [claude]: Edit warn-destructive-edit.sh
- 2026-08-14 [claude]: Edit enforce-doc-sync.sh
- 2026-08-14 [claude]: Edit json_field.py
- 2026-08-14 [claude]: Edit _cos_env_io.sh
- 2026-08-14 [claude]: Edit _cos_env_io.sh
- 2026-08-14 [claude]: Edit test_hooks_fail_closed.py
- 2026-08-14 [claude]: Edit block-dangerous-commands.sh
- 2026-08-14 [claude]: Edit check_git_destructive.py
- 2026-08-14 [claude]: Edit check_git_destructive.py
- 2026-08-14 [claude]: Edit test-governor.sh
- 2026-08-14 [claude]: Edit test-governor.sh
- 2026-08-14 [claude]: Edit test-governor.sh
- 2026-08-14 [claude]: Edit test-governor.sh
- 2026-08-14 [claude]: Edit test_hooks_fail_closed.py
- 2026-08-14 [claude]: Edit test_hooks_fail_closed.py
- 2026-08-14 [claude]: Edit msg2.txt
- 2026-08-14 [claude]: commit 54de3709ef — fix(hooks): stop every blocking gate from flipping its verdict when jq is absent
- 2026-08-14 [claude]: Edit doctor_checks_bootstrap.py
- 2026-08-14 [claude]: Edit doctor_checks_bootstrap.py
- 2026-08-14 [claude]: Edit README.md
- 2026-08-14 [claude]: Edit doctor-checks.md
- 2026-08-14 [claude]: Edit msg3.txt
- 2026-08-14 [claude]: commit b2bbf53ae1 — feat(doctor): report whether the hook layer has a JSON/stdin parser at all
- 2026-08-14 [claude]: Migrated all 19 blocking gates off raw jq to cos_json_field (54de3709) and added bootstrap.hook_parsers to cos doctor…
- 2026-08-14 [claude]: Status transitioned to complete via cos task-done.
