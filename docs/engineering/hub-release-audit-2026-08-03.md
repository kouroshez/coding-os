<!-- domain:CORE | layer:engineering | ssot:false | updated:2026-08-03 -->
# Hub Web UI — Pre-Release Audit (2026-08-03, TASK-864)

> P: Tick-by-tick Playwright audit of every Hub screen before the first public release — verdict + evidence per item, fixes shipped in the same pass.
> R: Release gating, verifying a screen's behaviour was actually exercised, follow-up prioritization.
> S: Ongoing UI development — [hub-architecture.md](hub-architecture.md) is the living contract; this audit is a snapshot.
> N: [hub-architecture.md](hub-architecture.md)

Full screen-by-screen Playwright audit of the Hub (`http://127.0.0.1:9188`)
before the first public GitHub release. Every checklist row was exercised
**live in a real browser session** (Playwright MCP) against the running hub —
not inferred from code. Verdicts: ✅ works / 🔧 fixed this audit / ⚠️ known
limitation (documented, non-blocking).

## 1 · Workspace

| Item | Verdict | Evidence |
| --- | --- | --- |
| Chat tab — landing, model/effort/role pickers, quick actions | ✅ | landing renders; Send gated on empty prompt; 15-role picker |
| Chat sessions list — real chats only | 🔧 | formula-dispatch sessions (`Input slice (upstream formulas only…`) and `ses-claude-sdk-*` ids now classed as system → hidden by default; live count went 58/58 → 24/58 with 0 formula rows visible |
| Board tab — columns, WIP caps, live agent stream | ✅ | TASK-864 moved icebox→in_progress→testing→complete during the audit and every transition appeared in the SSE stream in real time |
| Search tab — function | ✅ | 4-layer fan-out returns scored hits (docs/tasks/graph verified non-empty) |
| Search tab — appearance | 🔧 | redesigned: hero empty-state with 4 layer cards, recent-query chips, icon input, solid Search button, layer-count chips on results |
| Design tab | 🔧 | removed (coming-soon placeholder has no place in a public release); `design` module id in `subsystems.yaml` untouched; old URLs redirect to chat |
| Memory tab (moved here from Diagnostics) | 🔧 | renders lessons/stats at `/workspace/memory`; `/diagnostics/memory` redirects |

## 2 · Graph

| Item | Verdict | Evidence |
| --- | --- | --- |
| Mode tabs meaning + docs | 🔧 | documented in [hub-architecture.md § Graph view modes](hub-architecture.md) — Auto = containment+dependency blend, Containment = folder→file→class→method dagre tree, Dependencies = imports/calls/inherits, Communities (was "Processes") = Louvain subsystem clusters. Pattern matches standard code-graph tooling |
| Communities view populates | 🔧 | root cause: `networkx` missing from the `cos` tool venv → detector import-guarded to `[]` → silent blank canvas. Fixed: `networkx>=3.0` promoted to base deps; verified 200 community headers + members render (738-node view) |
| Empty-state honesty | 🔧 | processes-mode zero-result now says "no communities computed — run cos graph-reindex…" instead of the generic depth message |
| budget low/med/high/max honest? | ✅ | mapping is 200/800/3000/20000 `max_nodes`; at `max` the server returned the complete noise-filtered blend (~3.5k nodes) with `result_truncated=false` — the truncation badge only appears when the clamp is real (verified at `med`: "800/800 · truncated") |
| Contains-spine, kind/edge filters, inspector | ✅ | spine expands, filter panel renders all kinds/edges, node click opens inspector |

## 3 · Cognition

| Item | Verdict | Evidence |
| --- | --- | --- |
| Live view | ✅ | streams real hook events (verified against this session's own hooks) — but it duplicated Diagnostics › Observability › Hook stream |
| Traces view | ⚠️ | lists sessions but 0 events for CLI/VSCode sessions — trace events are only written on the SDK dispatch path. Reachable via Diagnostics › Sessions ("replay its cognition trace") and Overview quick-links. Follow-up: emit classify/hook traces from panel sessions |
| Roles view | ✅/⚠️ | formula registry (11 roles) + chain + evidence panels render with honest empty-state copy; populates only when `cos_compose_chain`/dispatch runs |
| Verdict | 🔧 | **removed from primary nav** (duplication + dispatch-only views); all routes stay deep-linkable — verified `/p/coding-os/cognition` still renders post-change and HubHome/Overview links work |

## 4 · Config

| Item | Verdict | Evidence |
| --- | --- | --- |
| Stacks — list, Add stack catalog | ✅ | installed stack + Remove; Add stack expands 26-stack catalog (install not exercised on the meta-repo — mutating the mother repo is out of scope by rule) |
| Skills — toggle applies instantly? | ✅ | disabled `incident-response` from the UI → `.coding-os.yaml::disabled_skills` written + `.claude/skills/incident-response` symlink removed **immediately**; re-enable restored both. No reinstall needed |
| MCP Servers — list + Add server | ✅ | reads `.mcp.json`; Add opens vetted first-party catalog (Fetch/Git/Sequential Thinking…) |
| Adapters — list + Add adapter | ✅ | installed Claude adapter with model roster; Add expands Codex CLI (roadmap) entry |
| Hooks — registry view | ✅ | 115 hooks grouped by category; page states safety hooks can never be disabled |
| Modules — disable takes effect instantly? | ✅ | disabled `cognition` from the UI → `subsystems-state.json` updated + `cos_role_info` returned `module_disabled` on the next MCP call, **no restart**; re-enable restored it. Dependency guard verified: docs module's Disable is blocked with "Required by tasks — disable it first" |
| Kernel-only profile viable? | ✅ | kernel row is locked always-on (37 hooks · 4 tools); every other module is opt-out with dependency guards; covered by `tests/test_module_gating_smoke.py` (incl. profile resolution + per-module tool gating) |
| Git — pr-mode presets | ✅ | correctly read-only-disabled on the meta-repo per ADR-0013, editable presets shown |
| Settings (merged here) | 🔧 | hub-level settings (budget cap, trace rotation, model routing, auto-spawn, auth, maintenance) now the 8th Config tab; `/diagnostics/settings` + legacy `/settings` redirect |

## 5 · Diagnostics

| Item | Verdict | Evidence |
| --- | --- | --- |
| Tab count | 🔧 | 7 → 5: Overview · Doctor · Logs · Observability · Sessions (Memory → Workspace, Settings → Config) |
| Overview | ✅ | tiles (agents live / cost / WIP / blocked) show real data; quick actions navigate correctly (Live hook stream → cognition live view verified); it is the diagnostics landing, placement correct |
| Doctor › Overview / Maintenance / Backend / sqlite | ✅ | real graph-doctor + `/health` + DB row counts (nodes 79 554, edges 146 507, tables enumerated); Maintenance lists repair commands + working quick links |
| Doctor › Health & charts "fake live stats" | 🔧 | counters were real Prometheus data but dominated by the SPA's own polling (`presence.*` at #1). Charts now **exclude self-polling routes by default** (opt-in checkbox to include); verified post-fix: Top routes shows only real work (graph.export etc.), presence.* gone |
| Logs | ✅ | tails `.cos.log.jsonl`; level filter verified (error → 0 events, info → 200 events); scope/substring/window inputs present |
| Observability (Hook stream / registry / Timeline / Board standup) | ✅ | all four sub-tabs render live data (registry 115 hooks, timeline 200 events, standup rollup) |
| Sessions | ✅ | presence table accurate (this session `active` with correct task/model); "History (0)" reads disk only while the DB holds 202 summaries — follow-up noted |

## 6 · Activity / Notifications

| Item | Verdict | Evidence |
| --- | --- | --- |
| Activity feed | 🔧 | bell subscribed only to `dispatch-completed` (never fires in normal use) → feed was always empty. Now also subscribes `task-updated`; verified live: closing TASK-864 put "TASK-864 → complete" in the feed in real time |
| Enable notifications | ✅ | requests browser `Notification` permission; stays gracefully in "Enable notifications" state until granted (OS prompt can't be auto-granted under automation — code path verified, no crash) |
| Tab badge / favicon dot | ✅ | unread badge + favicon dot logic only escalates when `document.hidden` (unit-tested in `lib/attention`) |

## 7 · Cross-cutting

| Item | Verdict | Evidence |
| --- | --- | --- |
| Primary nav | 🔧 | Workspace · Graph · Config · Marketplace(soon) · Diagnostics — Cognition removed; Marketplace kept as the single roadmap anchor (Config › MCP copy references it) |
| Global (unscoped) routes | ✅ | `/workspace/*` shows the project-required picker with the new 4 tabs; redirects for all legacy flat routes |
| Light/dark theme | ✅ | toggle flips instantly, both themes render cleanly (screenshot-verified) |
| Console errors | ✅ | zero JS console errors across every audited screen |
| Dead code | 🔧 | `DesignComingSoon.tsx` (+test) deleted; orphan `.coding-os/skill-overrides.json` (zero readers) deleted. `RolesPage.tsx` kept — it is the Roles view inside CognitionPage, not dead |

## Verification run (Rule 26 — executed, not read)

`tsc --noEmit` clean · vitest **214/214** across 46 files · `make ui-build`
rebuilt the served bundle · `make docs-lint` OK · every changed screen
re-exercised live via Playwright after the rebuild.

## Known follow-ups (non-blocking, operator to prioritize)

1. Trace events for panel (CLI/VSCode) sessions — kernel-side emit so Cognition › Traces populates outside the SDK dispatch path.
2. Sessions › History should read `session_summaries` (202 rows) instead of disk only.
3. `set_project_skill` round-trips `.coding-os.yaml` through `yaml.dump`, destroying file comments — needs a comment-preserving writer.
4. Board standup rollup shows duplicate task ids with em-dash gaps — cosmetic.

## Post-audit operator revisions (TASK-868, same day)

Two verdicts above were overturned by operator decision after review:

- **Workspace Design tab restored** — the coming-soon surface returns as the
  `design` module's roadmap anchor (audit §1 had removed it).
- **Overview moved out of Diagnostics into Workspace** as its first tab
  (`/workspace/overview`); Diagnostics now lands on Doctor with four tabs, and
  `/diagnostics/overview` + legacy `/dashboard` redirect to the new home
  (audit §5 had kept it under Diagnostics).

[hub-architecture.md](hub-architecture.md) reflects the final IA.
