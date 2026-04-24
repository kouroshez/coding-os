---
id: TASK-085
title: "Hub UI: Roles tab — F1–F11 formula dispatch viewer + EvidenceBundle explorer"
swimlane: core
kind: feature
epic: hub-tab-scaffold
labels: [hub, ui, roles, cognition]
status: icebox
priority: P3
appetite: "6h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-072]
blocked_by: []
references: []
---

# TASK-085: Hub UI — Roles tab

**Outcome (one sentence):** Operators open `/roles` in the Hub, browse the 11 formula role cards (F1 Researcher … F11 Refactorer), see the **currently composed chain** (`.coding-os/<agent>/.roles`), and inspect the last N **EvidenceBundle** outputs per formula with their typed JSON schema highlighted.

## Read First

- [core/thinking_os/roles/](../../core/thinking_os/roles/) — the 11 formula YAMLs (`F1_researcher.yaml` … `F11_refactorer.yaml`) + `presets/registry.yaml`.
- [core/thinking_os/tools/cognition.py](../../core/thinking_os/tools/cognition.py) — `cos_analyze_task`, `cos_compose_chain`, `cos_supervise_record_output`.
- [core/thinking_os/tracing.py](../../core/thinking_os/tracing.py) — JSONL emission per trace event (the Cognition tab already consumes this).
- AGENTS.md §"Cognition & Tracing (Phase N.6)" — canonical role-chain contract.
- [core/web/ui/src/features/cognition/](../../core/web/ui/src/features/cognition/) — prior art: how the Cognition tab reads traces; this tab parallels it but scoped to formula-output events.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** the Roles tab is opened
  **When** it renders
  **Then** three columns appear: **left** = list of all 11 formulas with F-ID, name, current version, expected output schema (collapsible), **middle** = the currently composed chain for the selected agent (reads `.coding-os/<agent>/.roles`), with highlight on the "active" formula (from `.role` pointer), **right** = a timeline of the last 20 EvidenceBundles the selected formula produced (`cos_supervise_record_output` events filtered by `formula_id`).
- **Given** clicking an EvidenceBundle
  **When** it opens
  **Then** a drawer shows: source session_id (clickable → deep-links to Cognition tab), raw JSON output, Pydantic schema validation result (green ✓ / red ✗ with error), and "agent" + "task_id" attribution.
- **Given** no active session
  **When** rendered
  **Then** the middle column falls back to "No agent session active — composed chain will appear here when `cos_compose_chain` fires" and the right column shows global last-20 across all formulas.
- **Given** a formula schema updated in YAML
  **When** the Hub reloads (or the YAML-watch fires)
  **Then** the left-column schema refreshes without restart.
- **Tests:** `tests/test_roles_endpoint.py` asserts YAML parse, chain read, output-event filtering; Playwright `e2e/roles-browser.spec.ts` covers nav + drawer + schema validation pill.

## Implementation Notes

1. **Backend:** `core/web/routes/roles.py`:
   - `GET /api/p/<slug>/roles` → list formulas with parsed YAML.
   - `GET /api/p/<slug>/roles/<formula_id>/outputs?limit=20` → recent EvidenceBundles pulled from the cognition trace JSONL files.
   - `GET /api/p/<slug>/roles/chain?agent=<name>` → contents of `.coding-os/<agent>/.roles` + `.role`.
2. **UI:** `features/roles/RolesPage.tsx` + `<FormulaCard>` (left col) + `<ChainTimeline>` (middle) + `<EvidenceList>` (right).
3. **Schema validation:** re-use the Pydantic models from `core/thinking_os/supervisor/` on the server side — return a pre-validated `schema_ok: bool + errors[]` so the UI doesn't need Pydantic.
4. Colour convention: `--accent` for active formula, muted for idle; never use red/green semantic colours except schema-pass/fail pills (`--danger` / `--success` tokens).
5. Tab feature-flagged by `hub-config.json::roles.enabled`.
6. **Do NOT import `adapters/**` from the web routes.** Everything pipes through `core/thinking_os/tools/cognition.py` (already MCP-shaped).

## Dependencies

- **Depends on:** TASK-072 (feature flag).
- **Soft-deps:** Cognition tab exists today; this tab ships cleaner deep-links if Cognition's session URLs land first (already done).

## Work Log
