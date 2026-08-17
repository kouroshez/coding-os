<!-- domain:INFRA | layer:reference | ssot:false | source:outcome_history#1085 | updated:2026-08-17 -->
# TASK-1008: SQLite's `journal_size_limit` is applied at WAL restart (first write after a completed checkpoint), never at checkpoint completion — so a size probe taken immediately after a checkpoint always shows the old high-water mark and looks like the pragma is ignored. Two consequences: a continuously-written DB stays bounded on its own, but an idle-but-pinned DB never restarts its WAL and so the cap alone can never save it — that gap needs a forced `wal_checkpoint(TRUNCATE)`. General lesson: when a prag

…[truncated]

**Date:** 2026-08-17  
**Domain:** INFRA  
**Source task:** [TASK-1008](../tasks/TASK-1008-cap-sqlite-wal-growth-journal-size-limit-sessionstart-wal-gu.md)

## Key Insight

SQLite's `journal_size_limit` is applied at WAL restart (first write after a completed checkpoint), never at checkpoint completion — so a size probe taken immediately after a checkpoint always shows the old high-water mark and looks like the pragma is ignored. Two consequences: a continuously-written DB stays bounded on its own, but an idle-but-pinned DB never restarts its WAL and so the cap alone can never save it — that gap needs a forced `wal_checkpoint(TRUNCATE)`. General lesson: when a prag

…[truncated]

## What Failed

Asserted that `PRAGMA journal_size_limit` shrinks the -wal at checkpoint completion. The test failed: after `wal_checkpoint(RESTART)` on a 42 MB WAL with a 32 MB cap, the file was still 42 MB. Read as "the pragma is being ignored" — the exact wrong conclusion that would have led to ripping out a working fix.

## What Worked

Probed the matrix empirically (PASSIVE/RESTART/TRUNCATE x sole-vs-shared connection x write-after-or-not) instead of reasoning from the docs. The cap lands at the WAL *restart* — the first write after a completed checkpoint, when the log wraps to frame 0 — not at checkpoint completion. Only `wal_checkpoint(TRUNCATE)` zeroes the file at checkpoint time.

## Links

- Pattern: `learned_patterns#378` — retrievable via `cos_details`
- History: `outcome_history#1085`
