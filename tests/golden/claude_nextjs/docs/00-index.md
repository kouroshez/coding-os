<!-- domain:ALL | layer:index | ssot:true | updated:2026-01-01 -->
# cos-golden-fixture — Master Index

> A software project managed by coding-os

Purpose: Primary navigation hub for SSOT documentation across product, architecture, governance, and playbooks.
Read when: You need to route to the canonical file for the active task.
Skip when: `AGENTS.md` or a playbook has already routed you to the exact target file.
Read next: The relevant playbook or domain doc below.

## Core Navigation

- [AGENTS](../AGENTS.md)
- Active tasks — run `cos board` (Scrumban; task files under `./tasks/`)
- [Questions Log](./_meta/questions.md)
- [Change Log](../changes.log)
- [Foundation Map](./_meta/foundation-map.md)
- [Roadmap](./_meta/roadmap.md)
- [Feature Tree](./_meta/feature-dependency-tree.md)

## Governance

- [Docs System](./governance/docs-system.md)
- [Agent Workflow](./governance/agent-workflow.md)
- [Task Lifecycle](./governance/task-lifecycle.md)
- [Risk Register](./governance/risk-register.md)
- [Decision Records](./governance/decision-records.md)
- [Wrapper Derivation](./governance/wrapper-derivation.md)
- [MCP Tool Inventory](./governance/mcp-tool-inventory.md)
- [Workflow Guide](./workflow/workflow-guide.md)

## Product and Content

- [PRD Index](./prd/00-index.md)
<!-- Add when nextjs/web template installed: - [Content Specs Index](./pages-content-spec/00-index.md) -->

## API Contracts

- [API Contracts Index](./api-contracts/00-index.md)
- [Error Format](./api-contracts/error-format.md)

## Engineering and Delivery

- [Architecture Index](./architecture/00-index.md)
- [ADR Index](./architecture/adr/00-index.md)
- [Ops Index](./ops/00-index.md)
- [Insights](./insights/00-index.md)
<!-- Add when stack-specific design system installed: - [Design Index](./design/00-index.md) -->

## Quick Routing

<!-- Routing entries are stack-specific. The CLI populates this section based on installed templates. -->
- UI / component task → [Frontend UI Playbook](./playbooks/frontend-ui.md)
- Content / SEO / metadata task → [Content & SEO Playbook](./playbooks/content-seo.md)
- Docs / workflow / AGENTS task → [Docs Governance Playbook](./playbooks/docs-governance.md)
