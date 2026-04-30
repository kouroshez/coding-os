<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-07 -->
# Open Questions

Purpose: Running log of questions raised during task execution that need external resolution before the blocked task can move forward.
Read when: Investigating why a task is blocked, or clearing up resolved questions.
Skip when: You're not handling a blocked task.
Read next: The blocked task file referenced in each question.

<!-- Blocker questions are logged here automatically by `make task-block`.
     Format: each question is `Q-NNN: <question>` followed by context lines.
     Resolve a question by removing it and adding the answer to the related task or ADR. -->

## Open

### Q-001 — Defer mtime-aware header cache for `list_doc_headers` (TASK-162 #3)

- **Source:** review of TASK-155 `cos_doc_headers_by`.
- **Status:** explicitly deferred — current cost (~80 ms / 200 docs / call) is below pain threshold.
- **Trigger:** revisit when the meta-repo OR a consumer project crosses **>500 markdown docs** OR when `cos_doc_headers_by` shows up in the slow-tool log (`cos cognition trace --slow`).
- **Implementation sketch when reactivated:** persist `{path: (mtime, frontmatter, opening_block)}` JSON in `$COS_STATE_DIR/.headers-cache.json`; invalidate per-row on `os.stat().st_mtime` mismatch; rebuild lazily on first `list_doc_headers` call after `auto-reindex-docs.sh` fires.
- **Why not now:** premature optimization — the rglob walk is dominated by stat() calls that the OS page-cache already handles.
