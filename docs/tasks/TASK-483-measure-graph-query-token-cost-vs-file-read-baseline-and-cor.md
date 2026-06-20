---
id: TASK-483
title: "Measure graph-query token cost vs file-read baseline and correct the unproven token-reduction claim"
swimlane: "graph_os"
kind: feature
epic: null
labels: [governance, benchmark, ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: null
agent_session: ses-claude-20260620-144553-a8b6
depends_on: []
blocked_by: []
references: []
---
# TASK-483: Measure graph-query token cost vs file-read baseline and correct the unproven token-reduction claim

**Outcome (one sentence):** A committed, CI-runnable benchmark reports per-tool graph-envelope tokens vs an equivalent file-read/grep baseline (ratio + savings%), and the unmeasured "~300 tokens replaces 5-10 reads" claim is replaced with measured numbers everywhere it appears — so the graph-first value claim is provable and cannot silently drift again. (Live spot-check found the published ~300 figure is ~16x off: real ~4785.)

## Read First
- src/core/graph_os/bench/harness.py
- src/core/graph_os/bench/fixtures.py
- src/core/thinking_os/tools/_shared.py
- .claude/rules/meta-graph-first.md
- docs/engineering/graph-hallucination-cures.md
- CLAUDE.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
**Given** the existing bench fixtures + the meta.tokens_estimated already stamped on every envelope, **When** the new bench module runs (wired to `make bench` / pytest -m bench), **Then** it emits JSON {workflow, graph_tokens, naive_tokens, ratio, savings_pct} for the documented graph workflows (references, rename_plan, contracts, communities+export, detect_changes), REUSING build_python_corpus/build_mixed_corpus + run_benchmark (no parallel bench dir, no new corpus generator). **And** the false figures in CLAUDE.md, .claude/rules/meta-graph-first.md, and the graph-explorer SKILL are corrected to the measured bands in the SAME change (under a governance/docs-update task marker). **And** bands are labelled heuristic-derived (tokens_estimated is chars/4, not a real tokenizer). **And** any CI gate trips only on gross regression (>2x), never tight thresholds.

## Work Log
- 2026-06-20 [claude]: Edit token_cost.py
- 2026-06-20 [claude]: Edit test_token_cost.py
- 2026-06-20 [claude]: Edit test_token_cost.py
- 2026-06-20 [claude]: Edit meta-graph-first.md
- 2026-06-20 [claude]: Edit AGENTS.md
- 2026-06-20 [claude]: Edit graph-first.md
- 2026-06-20 [claude]: Added bench/token_cost.py (reuses fixtures+run_benchmark; emits workflow/graph_tokens/naive_tokens/ratio/savings_pct)…
