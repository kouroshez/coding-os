<!-- cos:generated:start — do not edit or re-import; source: coding-os DB -->
## Trusted lessons (auto-generated)

- Recurring block (44 occurrences): test-governor → satisfy the blocked rule before retrying the action _(seen 121×)_
- Recurring backtrack root cause 'tool_failure' (36 occurrences) → Run cos_health to verify permissions/env vars, then retry with explicit paths. _(seen 20×)_
- Recurring block (40 occurrences): block-dangerous-commands — force-push-main → satisfy the blocked rule before retrying the action _(seen 10×)_
- Recurring block (6 occurrences): block-dangerous-commands — rm-rf-critical → satisfy the blocked rule before retrying the action _(seen 415×)_
- Recurring block (6 occurrences): block-secrets — env-file → satisfy the blocked rule before retrying the action _(seen 163×)_
- Recurring block (6 occurrences): block-uv-heredoc — uv-run-heredoc → satisfy the blocked rule before retrying the action _(seen 65×)_
- Recurring block (17 occurrences): thinking_os-gate — gate-not-recorded → satisfy the blocked rule before retrying the action _(seen 68×)_
- Recurring block (38 occurrences): enforce-skill — no-domain-skill → satisfy the blocked rule before retrying the action _(seen 111×)_
- Recurring block (39 occurrences): enforce-commit-message — commit-msg-contract → satisfy the blocked rule before retrying the action _(seen 125×)_
- Recurring block (29 occurrences): branch-guard — worktree-add → satisfy the blocked rule before retrying the action _(seen 636×)_
- Skill 'graph-explorer clean-code python-meta-server hook-authoring thinking_os react-vite-hub' correlates with rework (8 occurrences) _(seen 85×)_
- Recurring block (28 occurrences): branch-guard — reset-head-rewrite → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (6 occurrences): branch-guard — checkout-branch-switch → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (12 occurrences): branch-guard — rebase-history-rewrite → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (23 occurrences): branch-guard — pr-shared-head-rewrite → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (28 occurrences): branch-guard — pr-protected-push → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (32 occurrences): branch-guard — pr-protected-ref → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (20 occurrences): branch-guard — protected-ref-rewrite → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (10 occurrences): branch-guard — commit-all-sweep → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (7 occurrences): branch-guard — branch-create-checkout → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (213 occurrences): block-secrets — no-verify → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (18 occurrences): block-dangerous-commands — force-push-main-refspec → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (19 occurrences): block-dangerous-commands — reset-hard → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (48 occurrences): block-dangerous-commands — git-clean-force → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (15 occurrences): enforce-skill — graph-explorer-required → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (61 occurrences): enforce-verify → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (4 occurrences): branch-guard — history-rewrite → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (4 occurrences): branch-guard — switch-branch → satisfy the blocked rule before retrying the action _(seen 9×)_
- Recurring block (12 occurrences): enforce-doc-anchor → satisfy the blocked rule before retrying the action _(seen 9×)_
<!-- cos:generated:end -->

# Memory Index

- [Sample-test lint-gate blind spot](sample-test-lint-gate-blindspot.md) — stack-lint only checks a sample test exists; run the stack's real `npm run lint` + `npm test` to trust it.
- [No parking actionable findings](no-parking-actionable-findings.md) — small fixable finding = fix in-session, never an icebox card; icebox stays empty.
- [Icebox parking is a structural failure](icebox-parking-structural-failure.md) — task-parking is by-design (frictionless create, no autonomous icebox→in_progress drain); keystone fix = stamp created_by_session on every card.
- [Never infer user location](never-infer-user-location.md) — verify operating country before payments/KYC guidance; never derive it from language
