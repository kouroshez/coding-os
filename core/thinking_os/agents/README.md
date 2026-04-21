# Agent Prompt Library (Phase M + N)

11 formula-agent prompts `F1_*.md … F11_*.md`. Each file is the prompt the
dispatched agent sees when its formula is fired by the supervisor. **Not** the
routing config — that lives in [../roles/](../roles/).

See [../roles/README.md](../roles/README.md) for the full split between
"when to fire" (`roles/`) and "what to say" (`agents/`).

## Frontmatter contract

```yaml
---
id: F<n>                       # F1..F11
name: "Human-readable label"
formula_ref: F<n>              # mirrors id
attach_phases: [MAP, CLASSIFY] # which Cognitive Cycle phases consume this agent
intensity_min: light           # minimum intensity at which this agent runs
model_pref:                    # per-complexity model routing
  complicated: sonnet
  complex: opus
tools_budget:                  # which MCP / built-in tools the agent may call
  - cos_search
  - Read
  - Grep
input_schema: cognition.F<n>Input    # Pydantic model for input
output_schema: cognition.F<n>Output  # Pydantic model for output (EvidenceBundle field)
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

## Body

The prompt itself — instructions to the agent, structured as numbered steps.
Step indices match `intensity_steps` keys above.

## Validated by

- `cli/doctor.py` C28 check (frontmatter has `id: F<n>`, file exists)
- `core/thinking_os/cognition.py::load_agent_registry` (parses frontmatter)
- `tests/test_codex_formula_commands.py` (frontmatter + symlinks)
