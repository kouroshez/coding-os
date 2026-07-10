# Thinking OS — Kernel (Always Active)

Methodology SSOT (Cognitive Cycle phases, Zoom tools, Four Laws in full): `src/core/skills/thinking_os/SKILL.md`, loaded on demand for COMPLICATED/COMPLEX. Origin spec: `src/core/docs/thinking_os-final-edition.md` (copied to `docs/workflow/thinking_os-final-edition.md` by `cos init`).

> **Golden Rule:** Never start acting before separating problem, behavior, rules, and risk. Light dimensions may skip behavior and risk once the Complexity Gate confirms low complexity.

## Complexity Gate (Before Any Work — Code, Docs, Debug, Planning, Answering)

Run for EVERY non-trivial request, not just coding.

**Q1 — Problem Nature (Cynefin):**

- **CLEAR:** Known solution → just do it, no Zoom. Signal: "standard", "CRUD", "same as before".
- **COMPLICATED:** Known type, details need analysis → Zoom cycle. Signal: "design", "architect", "integrate".
- **COMPLEX:** Unknown until tested → Zoom + experiment. Signal: "best way to", "optimize", "strategy".
- **CHAOTIC:** Broken NOW → act first, Zoom later. Signal: "down", "crash", "emergency".
- **CONFUSION:** Can't classify → decompose into pieces, classify each.

**Q2 — Dimensions:** 1 → single pass. 2-4 → standard Zoom. 5+ → full Zoom with Dimension Map. 8+ → break into separate problems.

## Cognitive Cycle (5 phases) — full detail in the SKILL

`CLASSIFY (dry) → MAP (dry) → ORIENT (read) → PLAN (think) → EXECUTE (do)`. Key principle: **think before reading, read before coding** — Classify and Map do zero file reads; Orient is the only phase that reads; Plan synthesizes; Execute implements the smallest correct change [P1, P4]. For COMPLICATED/COMPLEX, Zoom In/Out (≤3 cycles, 10 Thinking Tools) runs *within* Plan. Phase-by-phase checklists, the Four Laws (Golden / Sequence / Zoom / Evolution), and Continuous-Monitoring reframe triggers live in the SKILL.

**Progress tracking in EXECUTE — one SSOT, one scratchpad.** The task **Work Log** (`cos_work_log_append`, one bullet per meaningful checkpoint) is the *persistent* record of progress — it survives the session, shows on the board, and is what the next agent inherits; the **Acceptance (G/W/T)** lines are the Definition of Done. A runtime `TodoWrite` (or equivalent) is allowed only as an *ephemeral, in-turn scratchpad* to stay on-track across a long multi-step EXECUTE within a single turn — never a substitute for the Work Log and never a second place a fact lives (P1 SSOT). Do not build a checklist/subtask field inside tasks — Acceptance + Work Log already carry that, and duplicating it is the drift bug Rule 22 forbids.

## Record Gate (Mandatory Before Code Changes)

After the Complexity Gate, record the classification before any Write/Edit on `.py`/`.ts`/`.tsx` — a hook BLOCKs code writes until then. **Prefer `cos_classify_prompt`** (it classifies, records, traces, and returns `recorded` + a fallback command); use the raw form below only when it returns `recorded=false`:

```bash
bash .claude/hooks/write-state.sh .thinking_os-gate "CLEAR 1"
```

Replace `CLEAR 1` with the real classification + dimension count (e.g. `COMPLICATED 3`). The gate is per-PANEL and session-scoped (`$COS_PANEL_DIR/.thinking_os-gate`; `write-state.sh` auto-routes the bare basename), expiring after 120 min or on a new session. Skip for non-code work. Per-panel scope: [state-files.md](../../docs/engineering/state-files.md).

## Routing

- **CLEAR** (1 dim) → record gate, proceed directly, no skill needed.
- **COMPLICATED / COMPLEX** → record gate, invoke `Skill skill: "thinking_os"` for full methodology.
- **CHAOTIC** → act to stabilize, record gate, then Zoom cycle afterward.

## Deliberation Record (COMPLICATED+ only)

For a **COMPLICATED or COMPLEX** gate, before EXECUTE the Plan phase appends a 1–2 sentence rationale to the task work log via `cos_work_log_append` — *why this approach, and which [constitution](../../docs/governance/constitution.md) value it honors* (e.g. "chose the smallest-correct-change over a generic helper because no third caller exists yet — anti-overengineering"). This makes the *reasoning*, not just the action, a persisted, auditable artifact that also feeds the memory/learning loop — the finding behind *Teaching Claude Why*: deliberation generalizes where a demonstration alone does not.

- **CLEAR / light gates skip this** — casual-work cost discipline is preserved.
- **Guidance, not a gate** — no hook enforces it and task-close is never blocked on it (avoid rationale-theater). Reuse the existing `cos_work_log_append`; add no new tool, hook, or schema.
