# Role Registry

11 role configs (`researcher.yaml` … `refactorer.yaml`) driving cognitive
routing. **Not** the agent prompts — those live in [../agents/](../agents/)
(separation of concerns).

> **What this does by default:** the composed chain is *single-agent role-phase
> guidance* surfaced in the banner (`roles=`), not parallel orchestration. Real
> sub-agent dispatch is opt-in and intentionally deferred — see
> [ADR: Role dispatch deferral](../../../../docs/governance/adr-role-dispatch-deferral.md).

| File           | Owns |
|----------------|------|
| `roles/<slug>.yaml` | **Routing**: when this role activates (triggers, deactivators, scoring weights, intensity defaults, prompt_prefix). Read by `cos_compose_chain` to build a chain of roles for a task. |
| `agents/<slug>.md`  | **Execution**: the actual prompt the dispatched agent sees, plus frontmatter (model_pref, tools_budget, schemas, criteria_required, intensity_steps, backtrack_triggers). |

Each `roles/<slug>.yaml` carries an `agent_file:` field that points to its
matching `agents/<slug>.md` — this is the contract that joins them. Slugs
in canonical order: `researcher · analyst · architect · documenter ·
implementer · reviewer · debugger · security_auditor · deployer · observer
· refactorer`.

## Contract

```yaml
# roles/researcher.yaml
id: researcher
role_name: "Researcher"
formula_ref: researcher
agent_file: agents/researcher.md   # ← cross-ref into agents/
activation:
  primary_triggers: [...]
  deactivators:    [...]
prompt_prefix: |
  ...
```

```markdown
<!-- agents/researcher.md -->
---
id: researcher
name: "Research & Discovery"
formula_ref: researcher
attach_phases: [MAP, CLASSIFY]
intensity_min: light
model_pref: {...}
tools_budget: [...]
input_schema: cognition.ResearcherInput
output_schema: cognition.ResearcherOutput
---

# Researcher — Research & Discovery
...prompt body...
```

## Why two files?

Routing must be cheap and stateless (read every dispatch decision); the agent
prompt is rich and only needed when that role is actually fired. Splitting
keeps `cos_compose_chain` fast and the prompt body editable without recompiling
routing logic.

Validated by `cli/doctor.py` C28 check.
