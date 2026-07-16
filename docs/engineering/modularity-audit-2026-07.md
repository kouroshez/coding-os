<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-07-16 -->
# Modularity / Auto-Sync Audit — July 2026

> P: The SSOT register for the 2026-07 modularity/auto-sync re-audit — the verified residual gaps after the June sweep landed, their evidence, the enterprise decisions (esp. the rules-axis reconciliation), the per-artifact pruning contract, and the mapped build tasks (epic `modularity-completion`).
> R: Before touching the modularity machinery (subsystems toggle, render pipeline, per-consumer rules, doc composition, MCP gating) or picking up any `modularity-completion` task — read this and its June predecessor first.
> S: Feature work unrelated to module/skill/stack toggling.
> N: [modularity-audit-2026-06.md](modularity-audit-2026-06.md), [../governance/critical-rules.md](../governance/critical-rules.md), [../playbooks/template-authoring.md](../playbooks/template-authoring.md)

> Nav: [Engineering Index](./00-index.md) | [Docs Index](../00-index.md)

**Audited by:** Claude Code — 2026-07-16 (7-dimension adversarial workflow, 46 agents, refute-by-default verification + an independent cross-check pass).
**Scope:** modularity / auto-sync only — the module toggle cascade completeness, instruction/doc composition, MCP surface gating, `cos init` scaffold fidelity, the Hub Config UI, and toggle-path test/logging coverage. NOT a full enterprise-readiness audit.
**Relationship to June:** the June register (F1–F16) is landed (TASK-438/439/440/441/447). This pass re-audits the *result* and finds the residue is **incomplete variability resolution** — a mature product line whose derivation is partial, not a broken one.

## 1. Verdict

The architecture is a genuine, sound **registry-driven software product line**: `subsystems.yaml` is a real feature model (features + `depends_on` constraints + named profiles), toggles are dependency-validated and atomic with rollback, skills/commands cascade ref-counted, MCP tools are capability-gated (startup surface removal + per-call fail-closed), AGENTS.md fragments are conditionally rendered, and `doctor`/Hub already carry a drift-audit spine. The owner's goal — *disable a module and everything it owns leaves as if it never existed; the markdown surface auto-syncs* — is **met for tools (next session), hooks, AGENTS.md sections, skills, and commands.**

No finding is critical. The gaps cluster into five root causes, all "some surface is not re-derived when the feature model changes":
1. **Rules have no ownership axis** — a disabled module's rules still ship and command dead tools (the axis was deleted as *dead* in June; the fix is to add it back *wired*).
2. **Docs prune only at init** — a live toggle strands module-tagged docs.
3. **MCP surface removal is startup-only** — a mid-session toggle leaves tools visible until reconnect (disclosure gap).
4. **No rule/doc drift audit** — the auditability persona gets a green `doctor` while stale surface persists.
5. **Extensibility is curated-core only** — a plugin author must fork `subsystems.yaml`; no module-owned MCP-server seam.

## 2. Terminology (the owner's naming question, answered)

The precise industry names, most-fitting first:

| Concept | Term | In this repo |
|---|---|---|
| The whole model | **Software Product Line (SPL) / feature-model–driven configuration** | `subsystems.yaml` = feature model; profiles = named configurations; `depends_on` = constraints |
| One SSOT drives generated artifacts | **Registry-driven / metadata-driven codegen** | `render_agents_md`, `write_runtime_allowlist` |
| Include/exclude doc regions by a flag | **Conditional content / profiling** (DITA/Flare condition tags; "ifdef for docs") | `\| module:X` header + `<!-- if-module:X -->` markers |
| Assemble a file from conditional partials | **Transclusion / conditional includes** | `_base/fragments/*.md.tmpl` + `{% if modules.x %}` |
| Expose a capability only when its feature is on | **Feature flags / capability gating** + **dead-surface pruning** | `_gated_module`, `apply_module_tool_gating` |

One line: **a registry-driven software product line with conditional-composition and capability gating.**

## 3. Per-artifact pruning contract

The root asymmetry (rank 9): five artifact types, five "left the system" guarantees. The July target makes rules/docs first-class.

| Artifact | Disable guarantee (before July) | Mechanism | July target |
|---|---|---|---|
| hooks | shipped, runtime-gated | `write_runtime_allowlist` (allowlist) | unchanged (safety-correct) |
| MCP tools | surface-removed at startup + per-call fail-closed | `apply_module_tool_gating` + `_gated_module` | + mid-session disclosure (TASK-819) |
| skills | physically unlinked, ref-counted | `cascade_module_skills` | unchanged |
| commands | physically unlinked, ref-counted | `cascade_module_commands` | unchanged |
| AGENTS.md sections | conditionally rendered | `render_agents_md` `{% if modules.x %}` | unchanged |
| **rules** | **NOT gated — always ships** | `install-adapter.sh` unconditional symlink | **owned + cascaded + self-guard (TASK-811)** |
| **docs** | **tag-stripped at init ONLY** | `_apply_doc_conditions` | **live prune on toggle (TASK-813) + drift (TASK-812)** |
| MCP server | single kernel server, install-time | `install.sh` | optional overlay `mcp_server` seam (TASK-818) |

## 4. Finding register (F-A … F-H) — verified, mapped to tasks

Severity: 🟡 medium · 🟢 low. All CONFIRMED by adversarial verification + independent cross-check.

| ID | Sev | Finding | Evidence | Task |
|---|---|---|---|---|
| F-A | 🟡 | Rules have no module-ownership axis — `memory.md`/`graph-first.md` ship + command dead tools under lean profiles | `subsystems.py:31-44` (no `rules` field); `install-adapter.sh:149-156` unconditional symlink; `memory.md:14/26` names `cos_search`/`cos_learn_*` | TASK-811 |
| F-B | 🟡 | Live disable strands module-tagged docs — `_apply_doc_conditions` runs only at init | `main.py:882` (init) vs `module_commands.py:27-75` (toggle omits docs); `update.py:454` never touches docs | TASK-813 |
| F-C | 🟡 | Module disable doesn't shrink the RUNNING MCP surface until reconnect (disclosure only) | `server.py:3117` startup-only `apply_module_tool_gating`; `_shared.py:843-848` comment concedes | TASK-819 |
| F-D | 🟡 | No `rule_drift`/`doc_drift` audit — green `doctor` while stale surface persists | `doctor.py:1034/1101/1150` (only consistency/skill/command); grep `rule_drift\|doc_drift` empty | TASK-812 |
| F-E | 🟡 | Hub ModulesTab under-discloses: `Owns` omits commands + identities, refusal reason tooltip-only, no confirm; `tasks→docs` "why" unreachable | `module_commands.py:265` (no commands count); `ConfigPage.tsx:1179` (title-only reason); `subsystems.yaml:106-109` (reason is a comment) | TASK-814 |
| F-F | 🟡 | Extensibility curated-core only — a plugin author must fork `subsystems.yaml`; no module MCP-server seam | `subsystems.py:28` single fixed path; `_shared.py:800` hardcoded; overlay covers only stacks/adapters (`_resources.py:55`) | TASK-818 |
| F-G | 🟢 | No E2E test proving all surfaces shed in one cascade; toggle path emits no `logging_os` signal | `test_cli.py:2300` asserts 2 surfaces; `module_commands.py:246-247` unasserted seam | TASK-816 |
| F-H | 🟢 | Doc-condition tagging is opt-in, incomplete, unlinted — untagged scaffold docs name disabled-module tools/commands | 3/38 docs tagged; `workflow-guide.md:98` names `/memory-search` untagged | TASK-815 |
| — | 🟢 | MCP surface honesty: `graph_query`/`graph_search` overlap; 4 un-gateable tools with false `kernel tools:[]` | `server.py:2256/2494`; `subsystems.yaml:87` | TASK-817 |
| — | 🟢 | Consistency: kernel over-pin (rank 10), `cos_log_query` gated while `logging_os` writes (rank 12), fail-open relative state path (rank 15), dry-run under-reports `.claude` (rank 16), HooksTab no inertness badge (rank 17), meta-repo can't dogfood cascade (rank 18) | see workflow synthesis | TASK-819 |

## 5. Decision — the rules axis (reconciliation with June)

June **deleted** `Module.rules` / `Module.doc_tags` under the Raptor principle: they were *declared-but-dead* (zero readers, never wired). That was correct — a half-wired axis is worse than none.

**July re-adds `Module.rules`, but fully wired.** This is not a reversal: the whole point of the June deletion was "don't keep half-wired things," and a wired cascade (`cascade_module_rules` + drift audit + self-guard defense-in-depth) is a *different artifact* than the dead field they removed. The trigger for building it now is that the owner's north-star is "leave the system as if it never existed" — a self-guarded-but-still-shipped rule (the `model-routing.md` pattern) is *present-but-inert*, which still burns a lean profile's context tokens and so does not meet the goal. Physical removal via the feature model does; self-guard is retained as the mid-toggle-window defense. Best-practice for SPL is **total variability resolution**, reusing the proven `cascade_module_skills` pattern — no new engine (Rule 22).

## 6. Roadmap — epic `modularity-completion`

| Order | Task | Sev | Effort |
|---|---|---|---|
| 1 | TASK-811 — rules ownership axis + cascade + self-guard (F-A) | 🟡 | M |
| 2 | TASK-812 — `doctor` rule_drift + doc_drift + Hub banner (F-D) | 🟡 | S |
| 3 | TASK-814 — Hub ModulesTab disclosure + explain-refusal (F-E) | 🟡 | M |
| 4 | TASK-813 — live-toggle doc prune / re-materialize (F-B) | 🟡 | M |
| 5 | TASK-819 — mid-session tool-surface disclosure + consistency cleanups (F-C + ranks 10/12/15/16/17/18) | 🟡/🟢 | M |
| 6 | TASK-815 — docs-lint module-tag coverage (F-H) | 🟢 | M |
| 7 | TASK-816 — E2E cascade test + toggle `logging_os` wiring (F-G) | 🟢 | S |
| 8 | TASK-817 — MCP surface honesty (graph tool overlap + kernel floor) | 🟢 | S |
| 9 | TASK-818 — extensibility overlay + pruning-contract spec (F-F) | 🟡 | L |

**Strengths (credit, re-verified):** feature-model SSOT; dependency-validated atomic toggles with rollback; ref-counted skill/command cascade; fail-closed per-call MCP gating + startup surface removal; fully-modular AGENTS.md; the reusable `_apply_doc_conditions` engine; the `doctor`+Hub drift spine; and a self-aware, documented anti-over-engineering posture (June's Raptor deletions).

## 7. Out-of-core module overlay (TASK-818)

A plugin author registers a toggleable **subsystem module** without forking the kernel: drop a `<id>.yaml` with a `modules:` block into `$COS_USER_MODULES_DIR` (default `~/.coding-os/modules.d/`). `cli.subsystems.load_subsystems` merges it over the core registry — mirroring the existing stack/adapter/skill overlays (`cli._resources`) — and the module then flows through the same `toggle_and_regen` cascade (hooks/skills/commands/rules/docs).

**Merge contract (conservative + fail-open):** the bundled core **always wins** on an id collision; an overlay module that claims `kernel: true`, has an unresolved `depends_on`, or lives in a malformed/unreadable file is skipped — a bad overlay never breaks the core registry. Overlay merging runs only for the real registry (`load_subsystems()` with no explicit `path`), so tests that pass a manifest path stay overlay-free.

**Deferred (noted follow-ups):** (a) the MCP tool-gate reader (`tools/_shared._tool_module_map`) does not yet honor the overlay, so an overlay module that ships its own `tools:` gates them only via the CLI path, not the running server — secondary, since a plugin cannot register new `cos_*` tools without server code anyway; (b) an optional `mcp_server` field + `.mcp.json` register/deregister step for a module that brings its own MCP server.

## 8. Consistency cleanups (TASK-819) — decisions + deferrals

Per TASK-819's DoD (each low-sev item is *closed* or *documented with a one-line rationale*):

- **rank 16 — dry-run fidelity (DONE):** `cos init --dry-run` now prints a note (text + JSON) that the `.claude/` agent surface (hooks/skills/commands/rules) is adapter-installed and NOT previewed, so an adopter no longer treats the file list as authoritative.
- **rank 10 — kernel granularity (DECISION: keep):** the kernel deliberately pins the enforcement-discipline set as always-on; a lean profile keeps the guardrails (`enforce-skill`/`enforce-verify`/`enforce-zoom`/`test-governor`) by design (per June audit §5). No safety-vs-discipline split — the discipline gates are the product's value, not ceremony.
- **rank 12 — `cos_log_query` ownership (DECISION: keep gated):** stays `observability`-owned; when observability is off the MCP tool is gated but `cos hooks-log` / CLI log access still works and `logging_os` keeps writing (recording is surface-independent by design). Documented, not moved.
- **rank 15 — tool-gate reader path (DEFER):** `tools/_shared._disabled_modules` fail-open + relative `COS_STATE_DIR` default is a documented lean-surface (not a security boundary) choice; the normal launch sets an absolute path. Follow-up: resolve absolute + WARN (not silent debug) when the state file is expected-but-unreadable.
- **rank 17 — HooksTab inertness badge (DEFER):** `/api/hooks/list` + `HookRow` do not yet carry a hook's owning module + gated state, so a module-gated hook still renders as live DNA. Follow-up: emit ownership + badge "inert (module <id> disabled)". Informational; the fact is available on the Modules tab.
- **rank 18 — in-repo dogfood coverage (DEFER):** the cascade is guard-skipped in the meta-repo (`is_coding_os_source_tree`), so live in-repo coverage needs the pr-mode consumer fixture (ADR-0013) to exercise a module disable/enable round-trip. Follow-up in the pr-mode fixture harness.
