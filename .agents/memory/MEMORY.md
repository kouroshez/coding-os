<!-- cos:generated:start — do not edit or re-import; source: coding-os DB -->
## Trusted lessons (auto-generated)

- Recurring block (2 occurrences): test-governor → satisfy the blocked rule before retrying the action _(seen 123×)_
- Recurring block (4 occurrences): warn-destructive-edit → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring backtrack root cause 'tool_failure' (38 occurrences) → Run cos_health to verify permissions/env vars, then retry with explicit paths. _(seen 26×)_
- Recurring block (49 occurrences): block-dangerous-commands — force-push-main → satisfy the blocked rule before retrying the action _(seen 12×)_
- Recurring block (9 occurrences): enforce-skill — py-skill-required → satisfy the blocked rule before retrying the action _(seen 3×)_
- Recurring block (43 occurrences): block-dangerous-commands — rm-rf-critical → satisfy the blocked rule before retrying the action _(seen 417×)_
- Recurring block (9 occurrences): block-secrets — env-file → satisfy the blocked rule before retrying the action _(seen 165×)_
- Recurring block (9 occurrences): block-uv-heredoc — uv-run-heredoc → satisfy the blocked rule before retrying the action _(seen 67×)_
- Recurring block (23 occurrences): thinking_os-gate — gate-not-recorded → satisfy the blocked rule before retrying the action _(seen 69×)_
- Recurring block (26 occurrences): enforce-skill — no-domain-skill → satisfy the blocked rule before retrying the action _(seen 112×)_
- Recurring block (9 occurrences): enforce-commit-message — commit-msg-contract → satisfy the blocked rule before retrying the action _(seen 127×)_
- Recurring block (3 occurrences): branch-guard — worktree-add → satisfy the blocked rule before retrying the action _(seen 638×)_
- Skill 'graph-explorer clean-code python-meta-server hook-authoring thinking_os react-vite-hub' correlates with rework (9 occurrences) _(seen 91×)_
- Recurring block (69 occurrences): branch-guard — reset-head-rewrite → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (12 occurrences): branch-guard — checkout-branch-switch → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (18 occurrences): branch-guard — rebase-history-rewrite → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (36 occurrences): branch-guard — pr-shared-head-rewrite → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (60 occurrences): branch-guard — pr-protected-push → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (54 occurrences): branch-guard — pr-protected-ref → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (30 occurrences): branch-guard — protected-ref-rewrite → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (15 occurrences): branch-guard — commit-all-sweep → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (15 occurrences): branch-guard — branch-create-checkout → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (198 occurrences): block-secrets — no-verify → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (24 occurrences): block-dangerous-commands — force-push-main-refspec → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (21 occurrences): block-dangerous-commands — reset-hard → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (48 occurrences): block-dangerous-commands — git-clean-force → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (6 occurrences): enforce-skill — graph-explorer-required → satisfy the blocked rule before retrying the action _(seen 10×)_
- Recurring block (3 occurrences): enforce-verify → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (6 occurrences): branch-guard — history-rewrite → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (9 occurrences): branch-guard — switch-branch → satisfy the blocked rule before retrying the action _(seen 11×)_
- Recurring block (14 occurrences): enforce-doc-anchor → satisfy the blocked rule before retrying the action _(seen 10×)_
<!-- cos:generated:end -->

# Memory Index

- [Sample-test lint-gate blind spot](sample-test-lint-gate-blindspot.md) — stack-lint only checks a sample test exists; run the stack's real `npm run lint` + `npm test` to trust it.
- [No parking actionable findings](no-parking-actionable-findings.md) — small fixable finding = fix in-session, never an icebox card; icebox stays empty.
- [Icebox parking is a structural failure](icebox-parking-structural-failure.md) — task-parking is by-design (frictionless create, no autonomous icebox→in_progress drain); keystone fix = stamp created_by_session on every card.
- [Never infer user location](never-infer-user-location.md) — verify operating country before payments/KYC guidance; never derive it from language
