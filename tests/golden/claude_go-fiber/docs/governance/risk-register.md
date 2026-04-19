<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-01-01 -->
# Risk Register

Purpose: Canonical list of active project, architecture, and workflow risks that still require mitigation or follow-up.
Read when: Planning work, reviewing blind spots, or deciding whether a task can proceed safely.
Skip when: The task is tightly scoped and all relevant risks are already captured in the task file.
Read next: Relevant ADR in `../architecture/adr/` or the domain architecture doc.

> Nav: [Docs Index](../00-index.md) | [ADR Index](../architecture/adr/00-index.md)

## Active Risks

<!-- Format: `RISK-NNN` Description (one line). Add owner and mitigation if known.
     Example:
     - `RISK-001` Backup automation needs operational owner before production.
     - `RISK-002` Monitoring stack RAM footprint may exceed VPS budget.
-->

(empty — populate as risks are identified)

## Usage Rules

- Risks stay here while active.
- Once resolved, move the resolution into the relevant ADR, architecture doc, or change log entry and remove or downgrade the risk.
- Historical risk analysis belongs in archive docs, not active architecture indexes.
- Each risk needs an ID (`RISK-NNN`), a one-line description, and ideally an owner and mitigation plan.
