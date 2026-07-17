<!-- cos:generated:start — do not edit or re-import; source: coding-os DB -->
## Trusted lessons (auto-generated)

- Recurring block (26 occurrences): test-governor → satisfy the blocked rule before retrying the action _(seen 114×)_
- Recurring block (29 occurrences): branch-guard — worktree-add → satisfy the blocked rule before retrying the action _(seen 636×)_
- Recurring block (4 occurrences): block-dangerous-commands — rm-rf-critical → satisfy the blocked rule before retrying the action _(seen 408×)_
- Recurring block (4 occurrences): block-secrets — env-file → satisfy the blocked rule before retrying the action _(seen 156×)_
- Recurring block (4 occurrences): block-uv-heredoc — uv-run-heredoc → satisfy the blocked rule before retrying the action _(seen 58×)_
- Recurring block (7 occurrences): thinking_os-gate — gate-not-recorded → satisfy the blocked rule before retrying the action _(seen 61×)_
- Recurring block (23 occurrences): enforce-skill — no-domain-skill → satisfy the blocked rule before retrying the action _(seen 104×)_
- Recurring block (25 occurrences): enforce-commit-message — commit-msg-contract → satisfy the blocked rule before retrying the action _(seen 118×)_
- Recurring backtrack root cause 'tool_failure' (33 occurrences) → Run cos_health to verify permissions/env vars, then retry with explicit paths. _(seen 6×)_
- Skill 'graph-explorer clean-code python-meta-server hook-authoring thinking_os react-vite-hub' correlates with rework (8 occurrences) _(seen 71×)_
- Recurring error (3 occurrences): left a task open: TASK-N is still 'in_progress' at session end — close it (cos task-done TASK-N), park it (cos task-move TASK-N --to blocked), or `touch .leave-open` for deliberate work-in-progress. → fix the failing precondition before retrying _(seen 15×)_
- Recurring error (5 occurrences): ### Error → fix the failing precondition before retrying _(seen 5×)_
- Recurring block (3 occurrences): codex-pretool-dispatch → satisfy the blocked rule before retrying the action _(seen 3×)_
<!-- cos:generated:end -->

# Memory Index

- [Sample-test lint-gate blind spot](sample-test-lint-gate-blindspot.md) — stack-lint only checks a sample test exists; run the stack's real `npm run lint` + `npm test` to trust it.
- [No parking actionable findings](no-parking-actionable-findings.md) — small fixable finding = fix in-session, never an icebox card; icebox stays empty.
