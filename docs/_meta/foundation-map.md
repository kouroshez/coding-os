<!-- domain:ALL | layer:reference | ssot:true | updated:2026-05-10 -->
# Foundation Map (`REF:*` Shortcodes)

> P: Compact canonical reference map for task `Read First` sections and inter-doc links — meta-repo edition.
> R: Adding a `Read First` entry, citing a canonical doc from a task or playbook, or building a tight cross-link.
> S: Direct relative links are clearer than a shortcode; one-off references; deep links to a heading anchor.
> N: `./00-index.md`, `./governance/docs-system.md`, `./governance/docs-first-protocol.md`

> Nav: [Docs Index](../00-index.md)

<!--
  Format contract — DO NOT BREAK:
    - `REF:<NAME>` → `./relative/path.md`
  The path MUST be the first backtick-wrapped value after the `→` arrow.
  Parsed by src/core/scripts/ref-resolve.sh (sed) and src/core/scripts/docs-lint.sh.
  Markdown links `[text](path)` here will BREAK the resolver — keep paths
  as plain backtick-wrapped strings.
-->

## Core Navigation

- `REF:AGENTS` → `../AGENTS.md`
- `REF:CLAUDE` → `../CLAUDE.md`
- `REF:DOCS-INDEX` → `./00-index.md`
- `REF:CHANGES` → `../changes.log`
- `REF:QUESTIONS` → `./questions.md`

## Governance (always-active rules + procedures)

- `REF:DOCS-SYSTEM` → `./governance/docs-system.md`
- `REF:DOC-FIRST` → `./governance/docs-first-protocol.md`
- `REF:CRITICAL-RULES` → `./governance/critical-rules.md`
- `REF:AGENT-WORKFLOW` → `./governance/agent-workflow.md`
- `REF:TASK-LIFECYCLE` → `./governance/task-lifecycle.md`
- `REF:ANATOMY` → `./governance/anatomy-contract.md`
- `REF:BOUNDARY` → `./governance/scaffold-boundary-contract.md`
- `REF:WRAPPER-DERIVE` → `./governance/wrapper-derivation.md`
- `REF:MCP-INVENTORY` → `./governance/mcp-tool-inventory.md`
- `REF:DECISIONS` → `./governance/decision-records.md`
- `REF:RISK-REG` → `./governance/risk-register.md`
- `REF:DOC-CHEAT` → `./governance/templates/doc-cheat-sheet.md`
- `REF:GDPR` → `./governance/gdpr-compliance.md`

## Architecture

- `REF:ARCH-INDEX` → `./architecture/00-index.md`
- `REF:META-ARCH` → `./architecture/meta-project.md`

## Engineering (SSOT references)

- `REF:ENG-INDEX` → `./engineering/00-index.md`
- `REF:MCP-ENVELOPE` → `./engineering/mcp-error-envelope.md`
- `REF:MCP-TRAPS` → `./engineering/mcp-schema-traps.md`
- `REF:GRAPH-QUERIES` → `./engineering/graph_os-queries.md`
- `REF:GRAPH-CURES` → `./engineering/graph-hallucination-cures.md`
- `REF:GRAPH-USES` → `./engineering/graph-use-cases.md`
- `REF:HOOKS-REF` → `./engineering/hooks-reference.md`
- `REF:HOOK-REGISTRY` → `../core/hooks/registry.yaml`
- `REF:ADAPTER-PARITY` → `./engineering/adapter-parity.md`
- `REF:HUB-ARCH` → `./engineering/hub-architecture.md`
- `REF:STATE-FILES` → `./engineering/state-files.md`
- `REF:NAMING` → `./engineering/naming-contract.md`
- `REF:BOARD-COUPLING` → `./engineering/board-thinking-os-coupling.md`
- `REF:TEMPLATES-LOC` → `./engineering/templates-location-analysis.md`
- `REF:TEMPLATE-ENFORCE` → `./engineering/template-enforcement.md`
- `REF:SKILL-ARCH` → `./engineering/skill-architecture.md`
- `REF:RULES-LOADING` → `./engineering/rules-loading.md`
- `REF:BASH-DEADLOCK` → `./engineering/bash-heredoc-deadlock.md`

## Adapters

- `REF:ADAPTERS-INDEX` → `./adapters/00-index.md`
- `REF:CLAUDE-SDK` → `./adapters/claude-sdk.md`

## Playbooks (also loadable as skills)

- `REF:PB-MCP-AUTHOR` → `./playbooks/mcp-tool-authoring.md`
- `REF:PB-HOOK-AUTHOR` → `./playbooks/hook-authoring.md`
- `REF:PB-ADAPTER-AUTHOR` → `./playbooks/adapter-authoring.md`
- `REF:PB-TEMPLATE-AUTHOR` → `./playbooks/template-authoring.md`
- `REF:PB-SECURITY-REVIEW` → `./playbooks/security-review.md`

## Source References

- `REF:CORE-DOCS` → `./code-os-core-docs/`

## Live (non-file) references

- `cos board` — live Scrumban view, DB-mirrored from `docs/tasks/`. Not a REF because it's a command, not a path.
- `cos board --web` — Hub UI Board panel.
- `docs/tasks/TASK-NNN-slug.md` — per-task SSOT file (use the path directly; no REF code needed).

---

## Authoring rules

- Every REF code maps to **one** canonical path. Duplicate REF codes are rejected by `docs-lint`.
- REF codes are UPPERCASE kebab-style (e.g. `REF:DOC-FIRST`).
- Add a new REF code when a doc is referenced from ≥3 task / playbook files. One-off references stay as direct relative links.
- Removing a REF code requires migrating every consumer first — `grep -rn 'REF:OLD-CODE' docs/` must return zero.
- The `REF:` prefix is reserved; never reuse it for non-foundation-map shortcodes.
- Path values MUST be backtick-wrapped on the same line as the arrow. Markdown link syntax breaks `src/core/scripts/ref-resolve.sh`.

## See also

- `./governance/docs-system.md` — Navigation Rules, when to use REF vs. relative link.
- `../core/scripts/ref-resolve.sh` — CLI resolver for `REF:*` → path (`make ref REF=DOC-FIRST`).
- `../core/scripts/docs-lint.sh` — REF validation pass (Check 4 fires when foundation-map exists).
