---
id: TASK-458
title: "pass-3 code-review fixes: overlay opt-in, panel-gate capture, fail-soft OSError, dry-run validation"
swimlane: cli
kind: bug
epic: null
labels: [modularity-audit-pass3, code-review-fix, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-20
started: 2026-06-19
completed: 2026-06-19
agent_session: ses-claude-20260619-063923-1c50
depends_on: []
blocked_by: []
references: []
---
# TASK-458: pass-3 code-review fixes: overlay opt-in, panel-gate capture, fail-soft OSError, dry-run validation

**Outcome (one sentence):** Address the CONFIRMED findings from the max-effort review of the pass-3 diff: (1) B-7 overlay default-resolve leaked community stacks/adapters into checked-in SSOT (generate_manifest/regen_rules/init-validation/tests) — revert overlay_dirs default to () opt-in, keep the tested machinery, defer consumer-discovery wiring. (2) B-4 _read_gate_file never reaches the panel subdir and only strips known id prefixes — add panels-glob + robust level-based prefix skip so MCP-path complexity capture works. (3) adapter/stack overlay fail-soft caught only ManifestError not OSError — catch OSError too. (4) cos init --dry-run returned before --disable-module validation — hoist validation + scope the preview honestly. (5) _envelope declares no 403 though module_disabled/permission return 403.

## Read First
- src/cli/stack_registry.py
- src/cli/adapter_registry.py
- src/cli/main.py
- src/core/thinking_os/record_outcome.py
- src/core/web/_envelope.py

## Repro Steps
make manifest-regen with a ~/.coding-os/templates/foo/stack.yaml present folds 'foo' into scaffold_manifest.json; cos init --dry-run --disable-module bogus prints a full preview + exit 0 while the real init exits 2.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a dev with ~/.coding-os/templates runs make manifest-regen **When** regen runs **Then** scaffold_manifest.json has NO community section. - **Given** a bare-UUID-prefixed gate **When** _read_gate_file **Then** the UUID is not read as the complexity level. - **Given** an unreadable community adapter.yaml in the overlay **When** load_adapter_registry **Then** it is skipped, not raised. - **Given** cos init --dry-run --disable-module bogus **When** run **Then** it exits non-zero. - **Given** the registry/overlay/record_outcome/web tests **When** run **Then** green.

## Work Log
- 2026-06-20 [claude]: Edit stack_registry.py
- 2026-06-20 [claude]: Edit stack_registry.py
- 2026-06-20 [claude]: Edit adapter_registry.py
- 2026-06-20 [claude]: Edit adapter_registry.py
- 2026-06-20 [claude]: Edit test_stack_registry.py
- 2026-06-20 [claude]: Edit record_outcome.py
- 2026-06-20 [claude]: Edit record_outcome.py
- 2026-06-20 [claude]: Edit test_record_outcome.py
- 2026-06-20 [claude]: Edit main.py
- 2026-06-20 [claude]: Edit main.py
- 2026-06-20 [claude]: Edit main.py
- 2026-06-20 [claude]: Edit main.py
- 2026-06-20 [claude]: Edit _envelope.py
- 2026-06-20 [claude]: Edit block-hardcoded-literals.sh
- 2026-06-20 [claude]: Edit stack_registry.py
- 2026-06-20 [claude]: Edit adapter_registry.py
- 2026-06-20 [claude]: Edit test_init_dry_run_preview.py
- 2026-06-20 [claude]: Edit test_stack_registry.py
- 2026-06-20 [claude]: committed 50b5ea8c · 9 files
