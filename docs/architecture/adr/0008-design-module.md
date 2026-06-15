<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-06-15 -->
# ADR-0008: Design module — reserve a future visual design surface before it ships

> Nav: [ADR index](00-index.md)

## Status

Proposed (roadmap). The module id `design` is reserved and the Workspace
**Design** tab ships as a coming-soon screen; no behaviour is wired yet.

## Context

coding-os covers code, docs, tasks, graph and memory, but has no visual design
surface. A canvas for screens/flows, shared design tokens, and round-trip sync
between design and components is a large, separate effort. Leaving it entirely
unannounced means (a) the `design` id namespace can drift or be claimed
inconsistently, (b) there is no anchor for the vision, and (c) the first
user-visible touchpoint would appear abruptly later.

## Decision

Reserve the module now; ship the surface as coming-soon:

1. Register module id `design` in `src/core/subsystems.yaml` — `kernel: false`,
   no hooks/rules/tools, no `depends_on`. It surfaces in the Config/modules UI
   as a toggleable (but behaviour-less) subsystem.
2. Add a **Design** tab to the Hub Workspace (`WorkspacePage`) routing to a
   polished, theme-consistent coming-soon screen (`DesignComingSoon`) that names
   this ADR and the `design` module id.
3. Wire NO backend route, hook, or tool. The eventual module hangs off this id.

## Consequences

- The id `design` is stable from day one; the future module extends it without a
  rename or migration.
- The Config tab gains one roadmap row, labelled clearly as such.
- Zero runtime/contract risk: pure additive UI plus a behaviour-less module entry.

## Alternatives considered

- **Ship nothing until the module is built** — rejected: no anchor for the
  vision, and the id could be used inconsistently in the interim.
- **A feature flag instead of a module entry** — rejected: `subsystems.yaml` is
  the established SSOT for toggleable modules; a parallel flag would duplicate it
  (anti-overengineering).
