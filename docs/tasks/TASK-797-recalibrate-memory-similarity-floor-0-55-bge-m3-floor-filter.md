---
id: TASK-797
title: "recalibrate memory similarity floor \u2014 0.55 BGE-M3 floor filters genuine synonym recall (4 semantic tests red)"
swimlane: "thinking_os"
kind: bug
epic: null
labels: [ready]
status: complete
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-05
completed: 2026-07-05
agent_session: ses-claude-20260704-210156-0ee9
depends_on: []
blocked_by: []
references: []
---
# TASK-797: recalibrate memory similarity floor — 0.55 BGE-M3 floor filters genuine synonym recall (4 semantic tests red)

**Outcome (one sentence):** Semantic memory + task search finds genuine synonym matches again by lowering the BGE-M3 memory floor to a measured value that still separates signal from noise.

## Read First
- src/core/thinking_os/embeddings.py (`_MEMORY_FLOORS` / `memory_similarity_floor`)
- src/core/thinking_os/tools/memory.py (`_augment_with_semantic`)
- src/core/thinking_os/tools/tasks.py (`task_search`)

## Repro Steps
1. `uv run --extra rag pytest src/core/thinking_os/tests/test_memory.py::TestMemorySearchSemantic src/core/thinking_os/tests/test_task_tools.py::TestTaskSearchSemantic -q`
2. Semantic queries with no keyword overlap (e.g. "task scheduling background workers" for a Celery obs; "multi vendor marketplace revenue sharing" for a payment task) return `[]`.
Expected: genuine synonym rows surface via semantic augmentation.
Actual: 4 tests fail — the memory floor (0.55 for BGE-M3) sits above the real signal cosines, so every genuine match is filtered before ranking.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** the BGE-M3 memory floor and a corpus of short observation/pattern/task rows,
- **When** a semantically-related query with zero lexical overlap is searched,
- **Then** the measured signal cosine clears the floor (floor set from real signal-vs-noise measurement, not intuition), the 4 semantic tests pass, and the thinking_os matrix stays green.

## Work Log
- 2026-07-05 [claude]: Edit measure_floor.py
- 2026-07-05 [claude]: Edit faithful_floor.py
- 2026-07-05 [claude]: Edit faithful_floor.py
- 2026-07-05 [claude]: Edit embeddings.py
- 2026-07-05 [claude]: Edit test_embeddings.py
- 2026-07-05 [claude]: Edit test_memory.py
- 2026-07-05 [claude]: Edit test_memory.py
- 2026-07-05 [claude]: Edit test_memory.py
- 2026-07-05 [claude]: Root cause: E raised memory semantic threshold 0.05→memory_similarity_floor()=0.55 (borrowed from code-symbol…
- 2026-07-05 [claude]: commit 8f4b1a6ad3 — fix(memory): recalibrate BGE-M3 memory floor 0.55->0.45 to restore synonym recall
- 2026-07-05 [claude]: Status transitioned to complete via cos task-done.
