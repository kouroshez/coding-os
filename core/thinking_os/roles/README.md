# Role Registry (Phase N)

11 role configs `F1_*.yaml … F11_*.yaml` driving cognitive routing. **Not** the
agent prompts — those live in [../agents/](../agents/) (separation of concerns).

| File         | Owns                                                                         |
|--------------|------------------------------------------------------------------------------|
| `roles/F*.yaml`  | **Routing**: when this formula activates (triggers, deactivators, scoring weights, intensity defaults, prompt_prefix). Read by `cos_compose_chain` to build a chain of formulas for a task. |
| `agents/F*.md`   | **Execution**: the actual prompt the dispatched agent sees, plus frontmatter (model_pref, tools_budget, schemas, criteria_required, intensity_steps, backtrack_triggers). |

Each `roles/F<n>_*.yaml` carries an `agent_file:` field that points to its
matching `agents/F<n>_*.md` — this is the contract that joins them.

## Contract

```yaml
# roles/F1_researcher.yaml
id: F1
role_name: "Researcher"
formula_ref: F1
agent_file: agents/F1_research.md   # ← cross-ref into agents/
activation:
  primary_triggers: [...]
  deactivators:    [...]
prompt_prefix: |
  ...
```

```markdown
<!-- agents/F1_research.md -->
---
id: F1
name: "Research & Discovery"
formula_ref: F1
attach_phases: [MAP, CLASSIFY]
intensity_min: light
model_pref: {...}
tools_budget: [...]
input_schema: cognition.F1Input
output_schema: cognition.F1Output
---

# F1 — Research & Discovery
...prompt body...
```

## Why two files?

Routing must be cheap and stateless (read every dispatch decision); the agent
prompt is rich and only needed when that role is actually fired. Splitting
keeps `cos_compose_chain` fast and the prompt body editable without recompiling
routing logic.

Validated by `cli/doctor.py` C28 check.
