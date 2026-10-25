---
name: resume-after-pause-refresh-markers
description: "after a long pause the gate, doc-anchor, zoom and skill markers are stale; task-start on an in-progress task does not rewrite the anchor"
metadata:
  node_type: memory
  type: project
  verified: 2026-10-25
  originSessionId: d93f4805-68e9-4b2d-907b-da3320d1fbf8
  modified: 2026-10-25T00:00:00.000Z
---

Resuming TASK-1047 two days later: the reclaim sweep had moved it to icebox, and every code Edit was blocked in turn by a stale `.doc-anchor` (8h max), `.zoom-checkpoint` and skill markers (2h max). `cos task-start TASK-1047` put the task back in progress but left the anchor's mtime two days old. The same set went stale again on 2026-10-25 after a crash and a compaction.

**Why:** each block costs a round trip and reads like a broken hook; knowing the full set up front makes a resume one step.

**How to apply:** on resuming formal work after hours away, run once: `cos task-start <ID>`, then `write-state.sh` for `.thinking_os-gate`, `.doc-anchor "task:<ID> <doc> § <section>"` and `.zoom-checkpoint "PROBLEM_FRAMED ..."`, and reload the domain skills. Related: [[loading-a-skill-is-not-applying-it]].
