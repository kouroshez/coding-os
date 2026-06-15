<!-- domain:ALL | layer:playbook | ssot:true | updated:2026-03-13 -->
# Research & Validation Playbook

Purpose: Perform current-state technical research with source discipline and convert findings into repo-safe decisions.
Read when: The task requires up-to-date framework/package standards, compatibility checks, or external architectural validation.
Skip when: The answer is stable in local SSOT and does not depend on recent facts.
Read next: Relevant local SSOT file, then the official external source for the specific topic

> Nav: [Docs Index](../00-index.md) | [Docs System](../governance/docs-system.md)

## Source Order

1. Official framework or specification docs
2. Official package docs or package metadata
3. Primary-source repository docs / changelogs
4. Secondary sources only if primary sources are insufficient

## Research Rules

- Record concrete versions and dates when recency matters.
- Prefer official framework docs, package compatibility tables, and web standards over secondary sources.
- Treat vendor blogs, community posts, and tutorials as non-canonical unless confirmed elsewhere.
- When a finding changes architecture or workflow, move it into SSOT and cite the source in the task/change log.

## Output Rules

- Distinguish observed facts from inference.
- State why a source is trustworthy when the choice is non-obvious.
- Keep recommendations implementation-oriented, not generic.
