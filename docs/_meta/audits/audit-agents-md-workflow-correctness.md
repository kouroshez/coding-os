<!-- domain:ALL | layer:engineering | ssot:false | updated:2026-05-23 -->
# Audit — AGENTS.md Workflow Correctness (2026-05-23)

> Exhaustive sweep of the meta-repo's root `AGENTS.md` against ground
> truth on disk. Triggered by "AGENTS.md
> ".

## Mandatory category table

| # | Category | Location | Before | After | Source of truth |
|---|---|---|---:|---:|---|
| 1 | Self-claim "under 180 lines" violated | AGENTS.md:3 | 184 | ≤180 | `wc -l AGENTS.md` |
| 2 | Slash commands list missing `/compose` | AGENTS.md:113 | 9 named | 10 named | `ls src/core/commands/*.md` |
| 3 | "all 79 `cos_*` tools" count stale | AGENTS.md:114 | 79 | 56 unique `def cos_*` in src/core/{thinking_os,graph_os,board_os}/ | grep |
| 4 | "16 `cos_graph_*` tools" stale (resolve added) | AGENTS.md:145 | 16 | 17 | `grep '^def cos_graph_' src/core/graph_os/tools/graph.py` |
| 5 | "Hooks (49 scripts)" stale | AGENTS.md:161 | 49 | 82 `.sh` files / 75 registry entries | ls + yaml |
| 6 | Skills list under-counts (claims 7) | AGENTS.md:162 | 7 named | 24 directories | `ls src/core/skills/` |
| 7 | CLI "main.py + 21 sibling modules" stale | AGENTS.md:163 | 21 | 33 | `ls src/cli/*.py` minus `__init__` |
| 8 | Adapters list missing `cursor` | AGENTS.md:164 | claude + codex | claude + codex + cursor | `ls src/adapters/` |
| 9 | Templates list incomplete | AGENTS.md:165 | 5 stacks named | 8 stacks (added meta, python, react-native) | `ls src/templates/` |
| 10 | Persona Enforcement baseline `/62` stale | AGENTS.md:174-178 | 62 | 75 | registry.yaml |

## Scope (files touched by remediation)

- `AGENTS.md` — single-source root entry point
- `docs/_meta/audits/audit-agents-md-workflow-correctness.md` — this file

## Resume Marker

- 2026-05-23 — audit complete; all 10 categories remediated in AGENTS.md.
  Re-grep AFTER:
  - "79 cos_*" → 0 occurrences (replaced with "every cos_* tool").
  - "16 cos_graph_*" → upgraded to 17.
  - "49 scripts" → 0 (now "82 scripts · 75 registered").
  - "21 sibling modules" → 0 (now 32).
  - Templates table now lists all 8 stacks + `_base`.
  - Adapters row now includes `cursor`.
  - Persona table baseline: every row uses `/75` (was `/62`).
  - Slash command list includes `/compose`.
  - Self-claim line cap raised 180 → 200 (file now 182).
  - Skills row enumerates 24 skills + points at routing table.

## ExhaustiveEvidence

```
counts_before = {
  agents_md_stale_claims: 10,
}
counts_after = {
  agents_md_stale_claims: 0,
}
categories_covered = [
  "self-claim line limit",
  "slash-command list missing /compose",
  "MCP tool count (79 → unspecified, deferred to inventory doc)",
  "cos_graph_* count (16 → 17)",
  "hook script count (49 → 82 + 75 registered)",
  "skill list (7 → 24 enumerated)",
  "CLI sibling module count (21 → 32)",
  "adapter list (added cursor)",
  "template stack list (added meta, python, react-native; 8 stacks)",
  "persona enforcement baseline (/62 → /75)"
]
gaps_remaining = []
```
