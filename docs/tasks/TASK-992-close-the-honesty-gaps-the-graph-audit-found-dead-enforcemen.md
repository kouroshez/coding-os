---
id: TASK-992
title: "governance: close the honesty gaps the graph audit found \u2014 dead enforcement globs, doc-node reference blindness, wrong published budget, unexecutable ablation"
swimlane: infra
kind: bug
epic: null
labels: [docs-update, governance, honest-benchmark, ready]
status: "in_progress"
priority: P1
appetite: 1d
created: 2026-08-15
started: 2026-08-15
completed: null
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---

# TASK-992: governance: close the honesty gaps the graph audit found — dead enforcement globs, doc-node reference blindness, wrong published budget, unexecutable ablation

## Outcome

**Outcome (one sentence):** Every claim and guard this repo publishes about its own context cost and graph enforcement is either measured-correct or removed: no enforcement glob silently matches nothing, cos_graph_references never reports 0 for a node whose inbound edges it simply did not query, context-budget.md carries only figures a re-run reproduces, and the ablation protocol names a harness that can actually execute.

## Read First

- docs/engineering/context-budget.md
- docs/engineering/ablation-protocol.md
- .coding-os/rag-config.yaml
- src/core/graph_os/tools/_graph_references.py

## Repro Steps

1. `uv run python -c "import yaml,glob; [print('DEAD',p) for p in yaml.safe_load(open('.coding-os/rag-config.yaml'))['graph']['enforce_context_on'] if not glob.glob('src/'+p.lstrip('*'))]"` → prints 2 dead globs (`thinking_os/db.py`, `graph_os/reindex_dispatch.py`); both name files that do not exist, so three hooks silently enforce nothing on the real ones.
2. `cos_graph_references("doc:file:src/core/rules/dimension-registry.md")` → `total_count: 0`, `result_truncated: false`, despite a `contains` edge existing. 8 node kinds / 1,538 inbound edges are 100% invisible to a default call.
3. `docs/engineering/context-budget.md:97` publishes 19,977 tokens for this repo; measuring the actual `.claude/rules/` symlinks gives 15,629.

## Acceptance

- **Given** the enforcement allowlist in `.coding-os/rag-config.yaml`, **When** any glob matches no file on disk, **Then** a test fails and names the dead glob.
- **Given** a node kind whose real inbound edges are not in the code-default set, **When** `cos_graph_references` is called without `kinds`, **Then** the response is non-zero or explicitly flags that the zero came from the kind filter.
- **Given** `docs/engineering/context-budget.md`, **When** each published figure is re-derived by executing the profiler, **Then** the document and the run agree.
- **Given** `docs/engineering/ablation-protocol.md`, **When** a reader follows it, **Then** the arms run on a harness whose acceptance tests discriminate and outside the guarded working tree.

## Work Log
- 2026-08-15 [claude]: Edit rag-config.yaml
- 2026-08-15 [claude]: Edit rag-config.yaml
- 2026-08-15 [claude]: Edit test_enforcement_globs_live.py
- 2026-08-15 [claude]: Edit _graph_references.py
- 2026-08-15 [claude]: Edit _graph_references.py
- 2026-08-15 [claude]: Edit _graph_references.py
- 2026-08-15 [claude]: Edit test_references_kind_blindness.py
- 2026-08-15 [claude]: Edit test_references_kind_blindness.py
- 2026-08-15 [claude]: commit d47e838cca — fix(graph): revive two enforcement globs that matched no file
- 2026-08-15 [claude]: commit 0f64cf9f9a — fix(graph): stop reporting zero references for structural node kinds
- 2026-08-15 [claude]: Edit context_budget.py
- 2026-08-15 [claude]: Edit context_budget.py
- 2026-08-15 [claude]: Edit context-budget.md
- 2026-08-15 [claude]: Edit context-budget.md
- 2026-08-15 [claude]: Edit context_budget.py
- 2026-08-15 [claude]: commit 496ed75710 — style(graph): sort imports in the references kind-blindness test
- 2026-08-15 [claude]: Edit ablation-protocol.md
- 2026-08-15 [claude]: Edit ablation-protocol.md
- 2026-08-15 [claude]: Edit ablation-protocol.md
- 2026-08-15 [claude]: Edit ablation-protocol.md
- 2026-08-15 [claude]: Edit graph-hallucination-cures.md
- 2026-08-15 [claude]: Edit SKILL.md
- 2026-08-15 [claude]: Edit SKILL.md
- 2026-08-15 [claude]: commit 9877aa447c — docs(graph): a zero from references is a coverage signal, not just truncation
- 2026-08-15 [claude]: commit f8393e5816 — docs(eval): move the ablation onto SWE-bench Verified and name the run environment
