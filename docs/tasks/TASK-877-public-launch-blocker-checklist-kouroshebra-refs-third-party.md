---
id: TASK-877
title: "Public-launch blocker checklist: kouroshebra refs, third-party IP docs, README/CHANGELOG staleness, CI hardening, PyPI trusted publisher"
swimlane: core
kind: chore
epic: null
labels: [ready]
status: icebox
priority: P2
appetite: 1d
created: 2026-08-04
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-877: Public-launch blocker checklist: kouroshebra refs, third-party IP docs, README/CHANGELOG staleness, CI hardening, PyPI trusted publisher

## Outcome
All launch blockers found in the TASK-874 audit are cleared before flipping the repo public. Grouped:

**Identity/links (trivial, do first):** replace `kouroshebra` → `kouroshez` in CODEOWNERS, SECURITY.md:22, NOTICE:5, CHANGELOG.md:121-122, .github/ISSUE_TEMPLATE/config.yml:4,7, README.md:610; fix CONTRIBUTING.md:37-38 issue-template filenames (bug_report.yml/feature_request.yml) and :303-307 workflow name (release-please.yml); decide github.com/coding-os (existing User account) vs kouroshez/coding-os and align the website Star button.

**IP/content:** remove or license-annotate docs/code-os-core-docs/ third-party material (Anthropic exam guide + skills guide, Fielding dissertation PDF+md, 6.9MB silicon-valley.png); decide fate of 3 untranslated Persian docs (formulas-v2.md has an English sibling); remove 2 absolute /Users/ciro/...streamos paths (ADR-0012:44, TASK-490:29); untracked root PNGs (adapters-kb-topic.png, qa-solved-thread.png) must not be committed.

**Docs truth:** refresh ~11 stale README numbers; fix README:497-503 Codex citation (point to adapter-parity.md, not workflow-audit-2026-04-25.md); retract CHANGELOG Bash-only/Cursor claims; resolve CHANGELOG-edit contradiction (CONTRIBUTING:248 + PR template:47 vs release-process.md hard rule); fix CONTRIBUTING:152-156 COS_GIT_WORKFLOW=pr instruction (unsupported on mother repo); history note README:620-623 (archive refs don't exist — fix note or actually archive); add coding-os.dev link to README.

**CI hardening (pre-public):** SHA-pin pypa/gh-action-pypi-publish (branch-pinned today) + other mutable-tag actions; job-scope release-please permissions; `if: github.event_name != 'schedule'` on test-python nightly dup; cancel-in-progress for push; timeout-minutes on ci-pass + release-please jobs; verify fork-PR approval setting (Require approval for all outside collaborators); move pull_request.base.sha interpolation to env.

**Post-flip:** add main ruleset (block force-push/deletion, require PR + CI for non-admin); register PyPI trusted publisher (env name `pypi`); merge release PR #29 → first public release; pyproject author email decision (personal gmail → role address).

## Read First
- TASK-874 work log (full audit evidence)
- docs/governance/release-process.md

## Acceptance
- **Given** the four pre-flip groups above, **When** each item is done and verified, **Then** the repo flips public with zero 404 links, no third-party IP, truthful docs, and hardened CI.
- **Given** the post-flip group, **When** the repo is public, **Then** main has a ruleset, the PyPI trusted publisher is registered, and release PR #29 is merged as the first public release.

## Work Log
