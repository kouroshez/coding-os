# Role Prompt Library (Phase M + N)

11 role-agent prompts (`researcher.md` … `refactorer.md`). Each file is the
prompt the dispatched agent sees when its role is fired by the supervisor.
**Not** the routing config — that lives in [../roles/](../roles/).

Catalog (canonical order, per the formulas-en.md spec — citation-only,
*never* used as runtime IDs):

| File                  | Role               |
|-----------------------|--------------------|
| `researcher.md`       | Research & Discovery |
| `analyst.md`          | Problem Decomposition & Analysis |
| `architect.md`        | Architecture & System Design |
| `documenter.md`       | Technical Documentation |
| `implementer.md`      | Implementation |
| `reviewer.md`         | Testing, Code Review & Performance |
| `debugger.md`         | Debugging |
| `security_auditor.md` | Security Audit |
| `deployer.md`         | Deployment & DevOps |
| `observer.md`         | Monitoring & Observability |
| `refactorer.md`       | Refactoring & Technical Debt |

See [../roles/README.md](../roles/README.md) for the full split between
"when to fire" (`roles/`) and "what to say" (`agents/`).

## Frontmatter contract

```yaml
---
id: <role-slug>                # researcher | analyst | architect | …
name: "Human-readable label"
formula_ref: <role-slug>       # mirrors id
attach_phases: [MAP, CLASSIFY] # which Cognitive Cycle phases consume this role
intensity_min: light           # minimum intensity at which this role runs
model_pref:                    # per-complexity model routing
  complicated: sonnet
  complex: opus
tools_budget:                  # which MCP / built-in tools the role may call
  - cos_search
  - Read
  - Grep
input_schema: cognition.<Role>Input    # Pydantic model for input
output_schema: cognition.<Role>Output  # Pydantic model for output (EvidenceBundle field)
max_tokens_in: 4000
max_tokens_out: 2000
timeout_s: 120
intensity_steps:               # which prompt steps run at each intensity tier
  light:    [1, 2, 3]
  standard: [1, 2, 3, 4, 5]
  full:     [1, 2, 3, 4, 5, 6]
backtrack_triggers: []         # conditions that demand re-dispatch upstream
criteria_required:             # acceptance criteria per step
  step_1: [scoped, observable]
  ...
---
```

`<Role>` in `input_schema` / `output_schema` is CamelCase — `Researcher`,
`Analyst`, `Architect`, …, `SecurityAuditor`, …, `Refactorer`.

## Body

The prompt itself — instructions to the role, structured as numbered steps.
Step indices match `intensity_steps` keys above.

## Validated by

- `cli/doctor.py` C28 check (frontmatter has `id: <role-slug>`, file exists)
- `core/thinking_os/cognition.py::load_agent_registry` (parses frontmatter)
- `tests/test_role_registry.py` (slug ↔ filename consistency)
