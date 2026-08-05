---
id: TASK-890
title: "Template go.mod placeholder breaks Go modfile parsing and GitHub dependency graph"
swimlane: templates
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-08-05
started: 2026-08-04
completed: 2026-08-04
agent_session: ses-claude-20260803-180632-5fca
depends_on: []
blocked_by: []
references: []
---
# TASK-890: Template go.mod placeholder breaks Go modfile parsing and GitHub dependency graph

---
id: TASK-890
title: "Template go.mod placeholder breaks Go modfile parsing and GitHub dependency graph"
swimlane: templates
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-890: Template go.mod placeholder breaks Go modfile parsing and GitHub dependency graph

**Outcome (one sentence):** All three Go template `go.mod` files parse with the real Go toolchain, clearing the "Dependency file checks have 1 error" banner on the public repository's security page.

## Read First
- `src/templates/{go,go-plain,go-fiber}/scaffold/src/backend/go.mod` — the three offenders
- `src/core/graph_os/toolchain.py:261` — `_GO_MODULE_RE`, which must survive the fix
- `.github/workflows/scaffold-verify.yml` — the "No leftover placeholders" gate the fix must not break

## Repro Steps
1. `cd src/templates/go/scaffold/src/backend && go mod edit -json`
2. Observe: `go: errors parsing go.mod: …:1: usage: module module/path` — `{` and `}` are token delimiters in Go's modfile lexer, so `module {{PROJECT_NAME}}` passes more than one argument to the `module` directive.
3. On GitHub the same parse failure surfaces as the only failing dependency-graph job in the repo's history (`Graph Update: go_modules …`, `dependency_file_not_parseable` ×3) and as the "1 error" banner on the Dependabot page.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the three Go stack templates,
- **When** `go mod edit -json` runs against each template file and against a project scaffolded from it,
- **Then** both parse, the template still contains the literal `{{PROJECT_NAME}}` token that `tests/test_template_scaffold.py` and the scaffold-verify placeholder gate require, and `graph_os` still extracts the module path without surrounding quotes.

## Work Log
- 2026-08-05 [claude]: Edit probe_target.py
- 2026-08-05 [claude]: Edit check_docs.py
- 2026-08-05 [claude]: Edit scan.py
- 2026-08-05 [claude]: Edit toolchain.py
- 2026-08-05 [claude]: Edit scan.py
- 2026-08-05 [claude]: Edit verify_gomod.py
- 2026-08-05 [claude]: Edit check2.py
- 2026-08-05 [claude]: Edit test_template_scaffold.py
- 2026-08-05 [claude]: Edit test_update_gap_prototype.py
- 2026-08-05 [claude]: Edit prove_cascade.py
- 2026-08-05 [claude]: Edit prove_smells.py
- 2026-08-05 [claude]: commit 3254a44dab — fix(templates): quote the go.mod module placeholder so Go can parse it
- 2026-08-05 [claude]: Root cause: braces are token delimiters in Go's modfile lexer, so `module {{PROJECT_NAME}}` passes multiple arguments…
- 2026-08-05 [claude]: Status transitioned to complete via cos task-done.
