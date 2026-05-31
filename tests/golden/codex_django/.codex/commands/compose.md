Compose the 11-semantic-role chain for the current COMPLICATED+ task and dispatch.

Use when the thinking_os gate is `COMPLICATED` or `COMPLEX` (Q1) — the chain orchestrates researcher → analyst → architect → … → reviewer/observer per the formula composer at [src/core/thinking_os/formula_composer.py](../thinking_os/formula_composer.py). For `CLEAR` tasks skip; the composer is intentionally heavyweight.

Steps:
1. Read the active task id (`$COS_AGENT_DIR/.task-current`) and current gate (`$COS_AGENT_DIR/.thinking_os-gate`). If `$ARGUMENTS` is provided as `TASK-NNN`, use it directly.
2. Invoke `cos_compose_chain(task_id="<TASK-ID>")` (the MCP tool registered in [src/core/thinking_os/tools/cognition.py](../thinking_os/tools/cognition.py)). The envelope returns:
   - `data.chain`: ordered `RoleActivation` list (role · intensity · formula).
   - `data.signals`: the `TaskSignals` the composer extracted (complexity · domain · risk markers).
3. State the chain inline so the user sees the orchestration: `🧠 chain: researcher → analyst → … → reviewer`.
4. Execute the chain — either by dispatching each role via `cos_dispatch_formula_run` (Claude SDK extra installed) or by walking the formulas inline (no SDK extra). Each role's `EvidenceBundle` is recorded via `cos_supervise_record_output`.
5. Update the task's Work Log with `chain composed: <role list>`.

Acceptance gates:
- Skipping `cos_compose_chain` on a COMPLICATED+ task is the dead-path captured in [docs/_meta/audits/audit-roles-dead.md](../../docs/_meta/audits/audit-roles-dead.md) — that audit blames a prompt-based nudge that agents read but don't act on. `/compose` is the deterministic alternative: one keystroke, one tool call, one chain.
- The chain output is persistent — `formula_dispatches` and `persona_selections` tables grow by ≥1 row per `/compose` invocation.

Output format:
```
🧠 chain: <r1> → <r2> → … → <rN>     (complexity=<Q1>, dimensions=<Q2>)
   signals: <domain>, <risk-markers>
   formulas: <preset-id> · <preset-id> …
```
