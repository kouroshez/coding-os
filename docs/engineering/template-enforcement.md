<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-18 -->
# Template Enforcement — `enforce-template.sh`

Purpose: Canonical reference for the PreToolUse hook that BLOCKS raw `Write` on four specific markdown classes, redirecting the agent to the right bootstrap flow. This is the "templates exist and must be used" policy — it does NOT touch ad-hoc docs (playbooks, engineering rules, runbook notes, session checkpoints).

Read when: a `Write` call on a markdown file is blocked · adding a new structured document class · deciding whether to add template enforcement for a new doc type.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

**Hook source:** [core/hooks/enforce-template.sh](../../core/hooks/enforce-template.sh)

## Design principle

Hard enforcement ONLY for SSOT documents — artifacts that feed the cognitive layer (`tasks.md` registry, ADR index, PRD hierarchy, `outcome_history` narratives). Everything else (engineering notes, runbooks, ad-hoc docs) is trusted to the agent's judgment. Over-enforcement on markdown creates friction without engineering value.

## Four enforced classes

| Class | Path pattern | Required bootstrap | Template source |
|---|---|---|---|
| **Task** | `docs/tasks/TASK-*.md` | `make task-create NUM=<N> TITLE="..."` | [task-detail.md](../../templates/_base/scaffold/docs/governance/templates/task-detail.md) |
| **ADR** | `docs/architecture/adr/ADR-*.md` | copy from `docs/governance/templates/adr-template.md` | project-local template |
| **PRD** | `docs/PRD/NN-*.md` | `cos setup --mode interactive` (4-Q wizard) or `--mode import-prd` | PRD classifier |
| **Breakthrough** | `docs/breakthroughs/*.md` | `cos_learn_narrative` MCP tool | written by tool |

Other markdown paths (playbooks, engineering rules, runbooks, questions.md, session checkpoints, top-level BLOG, README) are **not** enforced.

## Soft edges

- Fires only on `Write` (creation). `Edit` of an existing file is always allowed — fixing a bootstrapped task file is free.
- Fires only when the target file does **not** already exist.
- Skips internal paths: `.coding-os/**`, `.claude/**`, `.codex/**`, `tests/**`, `node_modules/**`, `.git/**`, `golden/**`.
- `00-index.md` inside any class is allowed (it's the scaffold index, hand-writable).
- If an ADR template file doesn't exist yet in the project, hook prints a soft reminder listing the required H2 sections but **allows** the write.

## Escape hatch — one-shot override

For scaffold regenerators, migration scripts, or legitimate edge cases:

```bash
touch .coding-os/.template-override
# next Write on any enforced class is allowed; the marker is consumed.
```

The hook `rm -f`s the marker after the first Write, so subsequent writes re-enforce. This is the escape valve for programmatic writes (e.g., `capture_golden.py`, template bootstrappers).

## Why these four, not "all markdown"

| Class | Why enforce |
|---|---|
| Task | `tasks.md` must stay consistent with `docs/tasks/*.md`; `make task-create` keeps them aligned. Hand-writing drifts the registry. |
| ADR | ADRs feed the doc RAG index; consistent H2 structure (`## Status`, `## Context`, `## Decision`, `## Consequences`, `## Alternatives`) makes them queryable via `cos_doc_search` |
| PRD | PRDs are multi-part by design (numbered `NN-feature-name.md`); the classifier routes sections across files. A single-file PRD is usually wrong |
| Breakthrough | Breakthrough files live alongside `outcome_history` DB rows. The MCP tool writes both atomically so they never desync |

## Extending — adding a new enforced class

Example: runbooks under `docs/runbooks/*.md` should follow a template.

1. **Create the template:** `docs/governance/templates/runbook-template.md` with required H2 sections.
2. **Add a branch** to `enforce-template.sh` following the ADR pattern:
    ```bash
    if [[ "$FILE_PATH" == *docs/runbooks/*.md ]]; then
      TEMPLATE="docs/governance/templates/runbook-template.md"
      if [[ -f "$TEMPLATE" ]]; then
        echo "BLOCKED: use the runbook template." >&2
        echo "  Template: $TEMPLATE" >&2
        exit 2
      fi
      exit 0  # allow if template absent
    fi
    ```
3. **Test:** write a new runbook without the template and confirm the block message appears in stderr.

Do NOT add a catch-all `*.md` branch. Every enforced class must justify its friction with a SSOT constraint; "consistency" alone is not enough.

## Interaction with other hooks

- `enforce-template` runs BEFORE `enforce-skill` and `enforce-doc-anchor` on the same PreToolUse event chain. If a hand-written task file is rejected here, the agent never reaches the skill or anchor checks.
- `block-protected-files` independently blocks edits to `CLAUDE.md`, `AGENTS.md`, etc. Those are orthogonal — template enforcement doesn't cover the governance docs themselves.

## Testing

- `uv run pytest tests/ -k template` — adapter-level tests that install/uninstall the hook.
- Manual: `touch /tmp/fake-task.md` then attempt `echo "# TASK-999" > docs/tasks/TASK-999-x.md` via an agent Write — should be blocked.

## Reference commits / rationale

The four classes were chosen because each has a DB mirror (`tasks` table, `document_chunks`, `outcome_history`) or a multi-file semantic (PRD). Enforcement makes the file structure a hard input contract for downstream indexing rather than a soft convention.
