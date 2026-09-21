<!-- cos:generated:start — do not edit or re-import; source: coding-os DB -->
## Trusted lessons (auto-generated)

- Recurring backtrack root cause 'tool_failure' (42 occurrences) → Run cos_health to verify permissions/env vars, then retry with explicit paths. _(seen 55×)_
- Skill 'graph-explorer clean-code python-meta-server hook-authoring thinking_os react-vite-hub' correlates with rework (9 occurrences) _(seen 120×)_
- At session end, a task remains in 'in_progress' status without explicit terminal state or intentional pause marking → Before session end, resolve the task: `cos task-done TASK-N` to complete, `cos task-move TASK-N --to blocked` to park, or create `.leave-open` to mark intentional work-in-progress — Unresolved in_progress state ambiguates the next session about whether work was abandoned, risking lost context and silent work loss _(seen 105×)_
- Attempting to write or edit Python/TypeScript code without first recording a Complexity Gate classification → Call `cos_classify_prompt` before code Write/Edit to record the gate, or use `write-state.sh .thinking_os-gate` — The gate separates problem analysis from implementation; skipping it causes solutions to misalign with the actual problem _(seen 27×)_
<!-- cos:generated:end -->

# Memory Index

- [Sample-test lint-gate blind spot](sample-test-lint-gate-blindspot.md) — stack-lint only checks a sample test exists; run the stack's real `npm run lint` + `npm test` to trust it.
- [No parking actionable findings](no-parking-actionable-findings.md) — small fixable finding = fix in-session, never an icebox card; icebox stays empty.
- [Icebox parking is a structural failure](icebox-parking-structural-failure.md) — task-parking is by-design (frictionless create, no autonomous icebox→in_progress drain); keystone fix = stamp created_by_session on every card.
- [Never infer user location](never-infer-user-location.md) — verify operating country before payments/KYC guidance; never derive it from language
- [Measure per profile, never summed](measure-per-profile-never-summed.md) — publish cost/benefit per project profile with a named baseline, and state where the tool loses
- [Dry-run in the repo before trusting units](dry-run-in-repo-before-trusting-units.md) — fixtures are born consistent; run a changed `cos` command in coding-os itself and read every printed line as a claim
- [Fail-open hooks hide dead triggers](fail-open-hooks-hide-dead-triggers.md) — bare `python3` can't import the project's deps; capture the helper's rc and stamp the debounce marker only after rc==0
- [Codex as eyes when Read breaks](codex-as-eyes-when-read-breaks.md) — a saturated extension host kills Read/Edit; `codex exec -i` inspects images, each failed Read costs 20 min.
- [Generated hero banners miss the README bar](generated-hero-banners-miss-the-readme-bar.md) — 4/4 gpt-image-2 banners rejected; ship a real product screenshot as the hero.
- [Run the size gate after formatting](run-size-gate-after-formatting.md) — `ruff format` adds lines; a budget test run before it gives a false green that CI catches.
- [Run the feature, not just its tests](run-the-feature-not-just-its-tests.md) — 1599 green tests hid three defects that made dispatch unable to run at all.
- [Browser file upload is blocked via CDP](browser-file-upload-blocked-via-cdp.md) — `setFileInputFiles: Not allowed` on a real Chrome profile; hand the step back on the first failure.
- [Headless Chrome beats the Playwright extension](headless-chrome-beats-the-playwright-extension.md) — the MCP relay drops mid-task and screenshots the connect page; render via the CLI.
- [Verify generated images by reading them back](verify-generated-images-by-reading-them-back.md) — `sips -c` crops instead of scaling; open every image before sending it.
- [Fix the twin of every guard you fix](fix-the-twin-of-every-guard-you-fix.md) — a widened guard left its hand-copied sibling narrow; grep the condition, not the function.
- [Reddit per-sub karma gates](reddit-per-sub-karma-gates.md) — global karma is worthless; large subs gate on karma earned inside that sub, and only automod names the number.
- [Git path ops ignore untracked](git-path-ops-ignore-untracked.md) — `git ls-files`/`git commit <dir>` skip new files; a scan-based test goes green on a blind spot.
- [A red CI gate hides a backlog](red-ci-gate-hides-a-backlog.md) — a failing gate job skips the rest; check how long CI has been red before blaming your change.
- [Verification matrix must match CI](verification-matrix-must-match-ci.md) — two subsystems CI tested had no matrix row; grep the workflow, not just the file you touched.
- [Loading a skill is not applying it](loading-a-skill-is-not-applying-it.md) — pass 1 is suspect by default; only a receipted second pass over the finished text counts.
- [Capture the payload, never assume it](capture-the-payload-never-assume-it.md) — Claude Code sends no exit_code for Bash; the event name is the outcome.
- [Check the card premise before fixing it](check-the-card-premise-before-fixing-it.md) — an old card's root cause is a hypothesis; re-measure before building its fix.
- [Rules edits need golden capture](rules-edits-need-golden-capture.md) — src/core/rules|hooks|skills render into tests/golden; docs-lint will not tell you.
- [Test isolation that deletes is not isolation](test-isolation-that-deletes-is-not-isolation.md) — unsetting a derived env var routes tests at the live project.
- [New graph tool needs a CLI twin](new-graph-tool-needs-a-cli-twin.md) — four registrations, and the graph_os matrix row checks none of the fourth.
