<!-- domain:ALL | layer:contract | ssot:true | updated:2026-04-26 -->
# Naming Contract

Purpose: Define the canonical names for Coding OS subsystems so paths, config,
tasks, generated fixtures, and docs do not drift between hyphen and underscore
forms.

Read when: Adding or renaming a subsystem, editing generated templates, writing
task frontmatter, changing state filenames, or touching docs that name the OS
subsystems.

Skip when: Naming ordinary CLI commands, user-facing prose that does not name a

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

subsystem, or external package names outside our control.

## Canonical Subsystem IDs

| Subsystem | Canonical ID | Display Name |
|---|---|---|
| Thinking layer | `thinking_os` | Thinking OS |
| Knowledge graph | `graph_os` | Graph OS |
| Scrumban planner | `board_os` | Board OS |

Rules:

- Use the canonical ID for paths, Python packages, imports, config keys,
  task frontmatter, swimlanes, epics, DB/artifact filenames, state filenames,
  tests, generated fixtures, and machine-readable docs.
- Use the display name for human prose headings and sentences.
- Do not introduce hyphenated aliases for these subsystems in new source,
  templates, generated fixtures, task metadata, or path-like docs.
- Legacy aliases may be read during migrations, but code must only generate
  canonical subsystem IDs.

Acceptable hyphens remain limited to ordinary CLI command words that are not
subsystem IDs, for example `task-create` and `graph-reindex`.
