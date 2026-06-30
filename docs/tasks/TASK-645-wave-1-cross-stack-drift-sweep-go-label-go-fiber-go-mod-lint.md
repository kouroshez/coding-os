---
id: TASK-645
title: "Wave-1 cross-stack drift sweep \u2014 go label, go-fiber go.mod+lint, node-express verify display, svelte comment"
swimlane: templates
kind: chore
epic: stack-completeness-v2
labels: [drift, wave-1, multi-stack, ready]
status: complete
priority: P2
appetite: 1d
created: 2026-06-30
started: 2026-06-30
completed: 2026-06-30
agent_session: ses-claude-20260630-012042-78c9
depends_on: []
blocked_by: []
references: []
---
# TASK-645: Wave-1 cross-stack drift sweep — go label, go-fiber go.mod+lint, node-express verify display, svelte comment

**Outcome (one sentence):** Five shipped-artifact contradictions removed so each stack's label/manifest/comment/verify-display matches its real scaffold: go label drops the unimplemented 'chi'; go-fiber go.mod is bumped to a current Go and its makefile lint matches verify (go vet, no orphan golangci-lint); node-express VERIFY_BACKEND display matches the real verify command; svelte +layout comment matches the Svelte-5 render mechanism.

## Work Log
- 2026-06-30 [claude]: Edit +layout.svelte
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit scaffold-boundary.yaml
- 2026-06-30 [claude]: Edit SKILL.md
- 2026-06-30 [claude]: Edit anatomy.md
- 2026-06-30 [claude]: Edit anatomy.md
- 2026-06-30 [claude]: Edit go.mod
- 2026-06-30 [claude]: Edit go.mod
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: Edit new_endpoint.py
- 2026-06-30 [claude]: Edit new_endpoint.py
- 2026-06-30 [claude]: Edit stack.yaml
- 2026-06-30 [claude]: go: chi→net/http across label/boundary/SKILL/anatomy/generator + go.mod 1.25; go-fiber: label v2→v3 + go.mod 1.25 +…
- 2026-06-30 [claude]: stack-lint go/go-fiber/svelte PASS; scaffold suite 82/83 (sole fail was angular collision in 647, fixed there).…
