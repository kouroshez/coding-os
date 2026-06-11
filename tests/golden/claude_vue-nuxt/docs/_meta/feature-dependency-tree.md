<!-- domain:ALL | layer:reference | ssot:true | updated:2026-01-01 -->
# Feature Dependency Tree

Purpose: Visualize cross-feature dependencies so the planner knows what must ship before what.
Read when: Sequencing tasks for a release, identifying blockers, or onboarding new contributors.
Skip when: Working on a single isolated feature with no upstream/downstream impact.
Read next: `./roadmap.md`, `../tasks/`

> Nav: [Docs Index](../00-index.md) | [Roadmap](./roadmap.md)

## Format

```text
Feature
├── depends on: [feature/task ids]
├── blocks: [feature/task ids]
└── status: planning | in-progress | shipped
```

## Tree

<!-- Add features below as the project grows. Example:

User Authentication
├── depends on: schema design, secrets rotation
├── blocks: user profile, account settings, payment
└── status: planning
-->

(empty — populate as features are planned)
