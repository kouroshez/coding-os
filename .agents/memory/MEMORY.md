<!-- cos:generated:start — do not edit or re-import; source: coding-os DB -->
## Trusted lessons (auto-generated)

- Recurring completion gap (2 occurrences): left a task open: TASK-N is still 'testing' at session end — close it (cos task-done TASK-N), park it (cos task-move TASK-N --to blocked), or `touch .leave-open` for deliberate work-in-progress. → resolve the gap (close/park the task or submit evidence) before ending the session _(validated 170×)_
- Recurring block (18 occurrences): test-governor → satisfy the blocked rule before retrying the action _(validated 106×)_
- Recurring block (29 occurrences): branch-guard — worktree-add → satisfy the blocked rule before retrying the action _(validated 530×)_
- Recurring block (26 occurrences): block-dangerous-commands — rm-rf-critical → satisfy the blocked rule before retrying the action _(validated 364×)_
- Recurring block (5 occurrences): block-secrets — env-file → satisfy the blocked rule before retrying the action _(validated 141×)_
- Recurring block (8 occurrences): warn-destructive-edit → satisfy the blocked rule before retrying the action _(validated 9×)_
- Recurring block (6 occurrences): block-uv-heredoc — uv-run-heredoc → satisfy the blocked rule before retrying the action _(validated 50×)_
- Recurring block (5 occurrences): thinking_os-gate — gate-not-recorded → satisfy the blocked rule before retrying the action _(validated 53×)_
- Recurring backtrack root cause 'tool_failure' (30 occurrences) _(validated 56×)_
- Recurring block (15 occurrences): enforce-skill — no-domain-skill → satisfy the blocked rule before retrying the action _(validated 88×)_
- Recurring block (45 occurrences): enforce-commit-message — commit-msg-contract → satisfy the blocked rule before retrying the action _(validated 71×)_
- Recurring block (25 occurrences): enforce-verify → satisfy the blocked rule before retrying the action _(validated 32×)_
- Skill 'graph-explorer clean-code python-meta-server hook-authoring thinking_os react-vite-hub' correlates with rework (7 occurrences) _(validated 55×)_
<!-- cos:generated:end -->

# Memory Index

- [Sample-test lint-gate blind spot](sample-test-lint-gate-blindspot.md) — stack-lint only checks a sample test exists; run the stack's real `npm run lint` + `npm test` to trust it.
