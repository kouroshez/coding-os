---
id: TASK-551
title: "Document two pr-mode limitations: GitHub-only forge support + Codex shared-tree edit-isolation gap"
swimlane: docs
kind: chore
epic: pr-mode-hardening
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-24
started: 2026-06-24
completed: 2026-06-24
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-551: Document two pr-mode limitations: GitHub-only forge support + Codex shared-tree edit-isolation gap

**Outcome (one sentence):** ADR-0013 and pr-workflow.md explicitly document two audit-confirmed pr-mode limitations as runtime limitations (not bugs): (1) push/PR/merge automation is GitHub gh-CLI only — non-GitHub forges (GitLab/Gitea/Forgejo/Bitbucket/self-hosted) can use only the `local` commit-only rung today; a forge-adapter layer is deferred. (2) block-shared-tree-edit.sh (Write/Edit BLOCK) fires only on runtimes that hook Write/Edit (Claude Code yes, Codex Bash-only no), so a Codex agent can edit the shared integration checkout — partially mitigated because branch-guard runs on Bash for Codex, so a shared-tree git commit is still blocked.

## Work Log
- 2026-06-24 [claude]: Edit 0013-pr-mode-multi-agent-git-workflow-consumer-only.md
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: Edit pr-workflow.md
- 2026-06-24 [claude]: ADR-0013 Consequences: added GitHub-only forge limitation (non-GitHub = local rung, forge-adapter deferred) + Codex…
- 2026-06-24 [claude]: commit 31a82ff5dd — fix(pr-mode): git-state probe honors form-selected integration branch
- 2026-06-24 [claude]: committed b498ed39 · 2 files
