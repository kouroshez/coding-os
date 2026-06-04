<!-- domain:META | layer:playbook | ssot:true | updated:2026-06-04 -->
# Playbook — Authoring a Rich Skill in `src/core/skills/` and `src/templates/<stack>/skills/`

> P: The canonical standard for what a coding-os skill *is* — anatomy, frontmatter, script discipline, version-pinning, cross-skill linking, and the 10/10 scoring rubric. This is the SSOT every skill is measured against.
> R: Creating a skill, enriching a thin one (SKILL.md only) to rich, reviewing a skill, or auditing the skill library for gaps/duplication.
> S: Routing a skill to a glob — that is `skill_enforcement:` in `src/templates/<stack>/stack.yaml` (regen target), not a skill-content task.
> N: [how-to-write-skills.md](../code-os-core-docs/how-to-write-skills.md), [skill-enforcement.md](../../src/core/rules/skill-enforcement.md), [hook-authoring.md](./hook-authoring.md), [anti-overengineering.md](../../src/core/rules/anti-overengineering.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Why this exists

A skill that is a lone `SKILL.md` is a hint, not a capability. The whole point of the skill system is **progressive disclosure + offloaded operations**: the model loads a thin trigger, pulls deep knowledge only when relevant, and runs a *script* instead of re-deriving a multi-step operation token-by-token every session. A thin skill forces the agent to improvise the operation each time — the exact cost we built skills to remove. This playbook makes "rich" the floor, not the ceiling.

The skill library is also a **knowledge chain**: improving one skill must lift its neighbours. A new recipe in `security-web` that the backend touches should be linked from `backend-fundamentals`, not duplicated into it. Skills are SSOT; cross-links (the `N:` nav line, `Pairs with …` in the description) are how the chain stays coherent without drift.

## Anatomy — the four directories (the floor)

```
skill-name/                  # kebab-case, matches frontmatter name
├── SKILL.md                 # REQUIRED — frontmatter + body (progressive disclosure L1+L2)
├── scripts/                 # executable, data-driven operations the agent runs instead of improvising
├── references/              # deep knowledge, loaded on demand (L3), dated + version-pinned
└── assets/                  # checklists / templates the skill emits or verifies against
```

A skill is **rich** when it ships at least: `SKILL.md` + one real `scripts/` entry + one real `references/` entry + one `assets/` checklist or template. A skill is **thin** (non-conformant) when it is `SKILL.md` alone. Exceptions are allowed but must be justified in review (see Rubric §6).

### Three-level progressive disclosure → where each lives

| Level | Loaded | Lives in | Budget |
|---|---|---|---|
| L1 — trigger | always (system prompt) | YAML `description` | ≤ ~1024 chars, must include *what* + *when* (trigger phrases) |
| L2 — method | when skill is relevant | `SKILL.md` body | tight; the *how*, decision gates, the one canonical recipe |
| L3 — depth | only when needed | `references/*.md` | unbounded; the exhaustive tables, edge-cases, per-stack variants |

Rule: anything the agent needs *every* time → L2. Anything needed *sometimes* → L3 (a one-line pointer from L2). Never inline an L3 table into L2 — that taxes every load.

## Frontmatter contract

```yaml
---
name: skill-name                 # kebab-case, == folder name, no "claude"/"anthropic", no < >
tier: layer|quality|architecture|stack|meta|cross-cutting   # taxonomy slot (see §Taxonomy)
domain: [backend|frontend|mobile|infra|db|universal|meta|...]
description: >                   # L1 — WHAT it does + WHEN to use (trigger phrases) + key capabilities. ≤1024 chars.
globs: "<consumer-relative glob or empty for manual>"
paths: ["<glob>", ...]           # data-driven enforcement target; consumer-relative, never an absolute path
last_reviewed: "YYYY-MM-DD"
versions_ref: versions.json      # OPTIONAL — present when references pin tool versions (see §Version-pinning)
---
```

- `description` is the single most important field — it decides whether the skill loads at all. Lead with concrete user phrases. Name the skills it pairs with so the chain is discoverable.
- `globs`/`paths` are **consumer-relative** (`backend/**/*`, `src/frontend/**/*.tsx`) — never hardcode `.claude/`, never an absolute machine path. The same skill renders into every adapter and every consumer project unchanged (P2 agent-agnostic).

## `scripts/` contract — data-driven, robust, token-thrifty

Every script a skill ships is an *operation the agent would otherwise improvise*. It MUST be production-grade per the `shell-scripting` skill:

1. **Data-driven, never hardcoded.** Inputs via flags with sane defaults — `argparse` (Python) / `getopts` (Bash). Paths default to consumer-relative roots (`--root src/backend`), never a literal machine path. Read config from the chain `$COS_STATE_DIR/domain-config.json` → repo fallback when a project root is needed (Rule 4).
2. **Fail-closed error handling.** Bash: `set -euo pipefail` + `trap` cleanup. Python: explicit exits, typed return. No silent failure; non-zero exit on any unmet precondition.
3. **Idempotent.** Re-running is safe — refuse to overwrite (or `--force`), short-circuit when already done.
4. **Observable.** Progress to stderr for long ops; a final machine-readable line (or `--json`) so the agent parses one line instead of scraping prose. Quiet by default, `--verbose` opt-in.
5. **Algorithmically honest.** No O(n²) scans where a set/index works; stream large inputs; bound memory. State the complexity in the header when non-obvious.
6. **Token-thrifty for the agent.** The script's *job* is to collapse a 10-call improvised operation into one call with a compact result. Emit the minimum the agent needs to decide the next step — not a transcript.

Header block (every script):
```
PURPOSE / INPUT / OUTPUT / DEPENDENCIES / NOTES
```
Stdlib-only when possible (portability across consumer projects). No network calls inside scaffold scripts unless that *is* the operation (e.g. the version-refresh tool).

## `references/` contract

- One file per coherent subtopic. Open with the doc-header `<!-- domain:X | layer:reference | ssot:true | updated:YYYY-MM-DD -->` and a `> P/R/S/N` nav block (match the house format).
- **Version-pinned.** Any version-sensitive claim ("React 19", "Go 1.x", "Postgres 17") carries the version inline and the file's `updated:` date. The version-refresh tool (below) rewrites these from a manifest — never let a reference assert a stale "latest".
- L3 only: the depth the agent pulls *sometimes*. If every load needs it, it belongs in `SKILL.md`.

Every recipe in `SKILL.md` and `references/` that shows code is **bad→good**: a one-line *why*, the `# Wrong` block + the failure it causes, the `# Correct` block + why it wins. Prose-only advice the agent can't anchor to a diff is weak — show the failure and the fix side by side.

## `assets/` contract

A checklist (`*-checklist.md`) or output template the skill verifies against or emits. This is what turns advice into a gate ("before finalizing, every box ticked"). Where a skill's value is a copy-paste artifact (a `.golangci.yml`, a CI workflow, a `Dockerfile`, a migration template), ship the real file in `assets/` — the agent copies it, it does not retype it.

## Optional power-ups (earn them — rule-of-three, don't add by default)

These lift a skill above the floor; add only when the skill's shape demands it:

- **`rules/` directory** — one rule per file (`title` + `impact: LOW|MEDIUM|HIGH|CRITICAL` + `tags` frontmatter, then bad→good). Use when a skill has **8+ discrete, independently-cited practices** (e.g. a per-stack performance or security skill). Below that threshold, keep them as sections in `SKILL.md`/`references/` — a `rules/` dir for three rules is overengineering. A `_template.md` in `rules/` documents the shape for future additions.
- **`evals/evals.json`** — trap-based assertions: `{prompt, trap (what the model tends to get wrong), assertions[]}`. Use for skills whose advice the model reliably ignores under pressure (low-cardinality logging, parameterized queries, fail-closed auth). This is how a skill proves it changes behaviour, not just vibes. Wire into CI when present.
- **`metadata.json`** — machine-readable discovery (abstract, version, capability tags) for higher-order tooling (skill recommender, version negotiation). Add when a skill participates in such tooling, not preemptively.

## Version-pinning mechanism (freshness without rot)

Reference docs rot the moment a framework ships. Mechanism:

- A skill whose references pin versions ships `versions.json` (a flat `{ "<ecosystem-or-pkg>": {"version": "x.y.z", "source": "<registry-url>", "checked": "YYYY-MM-DD"} }`).
- References cite the pinned version; `last_reviewed` + per-line `updated:` make staleness visible.
- `src/core/scripts/refresh-skill-versions.py` walks every skill's `versions.json`, queries the authoritative registry per ecosystem (one canonical command each — `go list -m -versions`, `npm view <pkg> version`, `pip index versions <pkg>`, Docker Hub API, …), and reports/rewrites drift. Run it in CI / `make skills-refresh-versions` to keep the library current with a single command instead of hand-editing N references.

This is the **better method** the agent reaches for instead of trusting a frozen "latest" written months ago.

## Cross-skill chain (no duplication)

- A capability lives in exactly **one** skill (SSOT). Neighbours **link**, never copy.
- When enriching skill A you discover a rule that belongs to B → add it to B and link from A's `N:`/description. Improving one skill lifts the chain.
- The `description`'s "Pairs with …" clause and each reference's `N:` nav line are the chain edges. Keep them bidirectional where it matters.

## The 10/10 rubric (review gate)

| # | Criterion | 0 | 1 |
|---|---|---|---|
| 1 | Anatomy: SKILL.md + scripts/ + references/ + assets/ all present & real | thin | rich |
| 2 | Description triggers on real user phrases (L1) | vague | specific + pairs-with |
| 3 | L2/L3 split correct — no L3 table inlined in body | bloated | disciplined |
| 4 | Scripts data-driven, fail-closed, idempotent, token-thrifty | improvised | production-grade |
| 5 | References dated + version-pinned to the current year | stale/undated | pinned + refreshable |
| 6 | Justified exceptions (a missing dir is argued, not forgotten) | silent gap | reasoned |
| 7 | Cross-links present; zero duplication with neighbours | drift risk | chained |
| 8 | Agent-agnostic + data-driven paths (no `.claude/`, no abs path) | hardcoded | portable |
| 9 | Anti-overengineering — earns every file, rule-of-three for splits | bloat | minimal-correct |
| 10 | Verifies (`make verify-hooks`/syntax) + regen stays green | red | green |

A skill ships only at 10/10. Anything less is a draft.

## Taxonomy — where a skill slots

| tier | meaning | examples |
|---|---|---|
| `cognitive` | the coding-os kernel itself | thinking_os, graph-explorer, search, agent-memory, task-driver |
| `quality` | universal craft, every change | clean-code, testing-strategy, observability, **shell-scripting**, **technical-writing** |
| `architecture` | cross-stack design | hexagonal-architecture, api-design, db-design, **sql-authoring**, state-management, performance |
| `layer` | backend/frontend/mobile generic | backend-fundamentals, frontend-fundamentals, mobile-fundamentals |
| `security` | hardening | security-web, security-mobile, auth-patterns |
| `infra` | run it in production | deployment-cicd, **docker**, **linux-sysadmin**, **redis**, incident-response |
| `stack` | one language/framework | python-django, python-fastapi, go-patterns, go-fiber, nextjs-react, react-native-*, **typescript**, **node**, **php/wordpress**, **supabase** |
| `meta` | authoring coding-os itself | meta-engineering, hook-authoring, mcp-tool-authoring, graph-os-authoring, python-meta-server, claude-sdk-integration, react-vite-hub |

## Authoring workflow

1. **Reconcile** — does the capability already live in a skill? (anti-overengineering: extend, don't duplicate.) Pick the tier.
2. **Scaffold** — `scripts/new_skill.py --name <name> --tier <tier> --root src/core/skills` lays the four dirs + frontmatter stub (data-driven, idempotent).
3. **Write L2** — the canonical recipe + decision gates in `SKILL.md`. Push depth to `references/`.
4. **Ship a script** — the operation the agent would otherwise improvise, per the scripts contract.
5. **Ship a reference + asset** — version-pinned depth + a checklist.
6. **Wire enforcement** (stack skills) — add the glob to `src/templates/<stack>/stack.yaml::skill_enforcement`, then `make regen-rules` (regenerates `skill-enforcement.md` + `dimension-registry.md` — never hand-edit those).
7. **Score** against the rubric; iterate to 10/10.
8. **Verify** — `make verify-hooks` (scripts), `make docs-lint` (references), regen green.
9. **Commit** one skill per commit.

## Anti-overengineering for skills

- Don't split one stack into two skills until **three** divergent concerns demand it (rule-of-three). `react-native-mobile` + `react-native-patterns` is two where one would do — merge unless each earns its keep.
- Don't add a script "for testability" with no operation behind it.
- Don't create a skill for a stack with zero current consumer demand — file a task.
- A reference that restates `SKILL.md` is dead weight; cut it.

## See also

- [how-to-write-skills.md](../code-os-core-docs/how-to-write-skills.md) — the upstream guide this standard is built on.
- [skill-enforcement.md](../../src/core/rules/skill-enforcement.md) — generated routing table (regen target).
- [anti-overengineering.md](../../src/core/rules/anti-overengineering.md) — Rule 22, applied to skills.
