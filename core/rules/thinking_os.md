---
description: Thinking OS Kernel — cognitive operating system for structured problem solving
globs: "**/*"
alwaysApply: true
---

# Thinking OS — Kernel (Always Active)

Source of truth: `core/docs/thinking_os-final-edition.md` (meta-repo) — copied to `docs/workflow-docs/thinking_os-final-edition.md` in consumer projects by `cos init` (see `cli/main.py::_copy_workflow_docs`). Full methodology summary loaded on demand from `core/skills/thinking_os/SKILL.md` (rendered as `.claude/skills/thinking_os/SKILL.md` per adapter).

> **Golden Rule:** Never start acting before separating problem, behavior, rules, and risk. Applies to Deep dimensions. Light dimensions may skip behavior and risk after Complexity Gate confirms low complexity.

## Complexity Gate (Before Any Work — Code, Docs, Debug, Planning, Answering)

Run this gate for EVERY non-trivial request — not just coding. Writing documentation, debugging issues, planning features, answering architectural questions, and proposing solutions ALL benefit from classification before action.

**Q1 — Problem Nature (Cynefin):**

- **CLEAR:** Known solution → Just do it. No Zoom cycle needed. Signal: "standard", "CRUD", "same as before"
- **COMPLICATED:** Known type, details need analysis → Zoom cycle. Signal: "design", "architect", "integrate"
- **COMPLEX:** Unknown answer until tested → Zoom cycle + experiment. Signal: "best way to", "optimize", "strategy"
- **CHAOTIC:** Broken NOW → Act first, Zoom later. Signal: "down", "crash", "emergency"
- **CONFUSION:** Can't classify → Decompose into pieces, classify each.

**Q2 — Dimensions:** 1 → single pass. 2-4 → standard Zoom. 5+ → full Zoom with Dimension Map. 8+ → break into separate problems.

## Cognitive Cycle (5 Phases)

```
CLASSIFY → MAP → ORIENT → PLAN → EXECUTE
(dry)      (dry)  (read)   (think)  (do)
```text
CLASSIFY → MAP → ORIENT → PLAN → EXECUTE
(dry)      (dry)  (read)   (think)  (do)
```

Key principle: **think before reading, read before coding.** Classify and Map are dry (zero file reads). Orient is the only phase that reads docs. Plan synthesizes findings. Execute only implements.

### Classify (dry)

- Complexity Gate (Q1 Cynefin + Q2 dimensions)
- Record gate
- Domain route (which playbook?)

### Map (dry)

- Dimension Map (what aspects? what depth?)
- Unknowns List (what don't I know?)
- Read List (which files, with reason?)

### Orient (targeted read)

- Read ONLY files from Read List [P3]
- Memory check (thinking_os MCP)
- Repo search (existing code?)
- Model update (new dimensions? reframe?)

### Plan (deep think — no new reads)

- Per dimension: current → target → gap → risk
- Action plan with ordered steps
- Assumption review
- For COMPLICATED/COMPLEX: Problem Framing (PROBLEM, ACTORS, BOUNDARY, CONSTRAINTS, SUCCESS, ASSUMPTIONS)

### Execute (implement only)

- Smallest correct change [P1, P4]
- On-demand reads ONLY if new questions arise
- Continuous monitoring

For COMPLICATED/COMPLEX tasks, Zoom In/Out cycles operate WITHIN the Plan phase (up to 3 cycles), using the 10 Thinking Tools. The Cognitive Cycle is the outer loop; Zoom is the inner loop within Plan.

## Four Laws

1. **Golden Rule:** Diverge (Tools 1-6: problem, behavior, rules, risk) before Converge (Tools 8-10: filter, build)
2. **Sequence Rule:** Think dry first, then read targeted, then build. Reading too early = wasted context.
3. **Zoom Rule:** Zoom Out before first In. Orient before every In. Zoom Out between every In. Final Zoom Out before done. All Zoom happens within Plan phase.
4. **Evolution Rule:** Don't reinvent commodity. Don't shortcut novel. (Wardley: commodity → best practice, novel → deep analysis)

## Record Gate (Mandatory Before Code Changes)

After running the Complexity Gate, record your classification before any Write/Edit on code files (.py/.ts/.tsx). A programmatic hook will BLOCK code writes until this is done. All state files are **session-scoped** — a new session invalidates previous state.

```bash
bash .claude/hooks/write-state.sh .claude/.thinking_os-gate "CLEAR 1"
```

Replace `CLEAR 1` with your actual classification and dimension count (e.g., `COMPLICATED 3`, `COMPLEX 5`). The gate expires after 120 minutes or when a new session starts. Skip for non-code work (docs, config).

## Routing

- **CLEAR** (1 dim) → record gate, proceed directly, no skill needed
- **COMPLICATED / COMPLEX** → record gate, invoke `Skill skill: "thinking_os"` for full methodology
- **CHAOTIC** → act to stabilize, record gate, then Zoom cycle afterward

## Continuous Monitoring

During work: "Am I guessing or do I have facts?" · "Did I discover a new state/rule/actor/risk?" · "Am I biased toward/against something?" · Reframe Trigger: if problem redefined, actor missing, boundary changed, or constraint changed → STOP → re-frame with Tool 1.
