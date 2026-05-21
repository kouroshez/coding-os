<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-13 -->
# Scaffold Boundary Contract

> P: Defines `src/templates/<stack>/scaffold-boundary.yaml` — machine-readable subtree isolation rules so multi-stack projects (`src/mobile/` + `src/backend/` + `src/ai-service/`) can never write outside their lane.
> R: Adding a new stack, debugging a `boundary mismatch` block, or auditing cross-stack import discipline.
> S: Authoring code — read the per-stack `anatomy.md` instead.
> N: [anatomy-contract.md](anatomy-contract.md), [docs-system.md](docs-system.md)

> Nav: [Governance Index](./00-index.md)

---

## File location

```
src/templates/<stack>/scaffold-boundary.yaml
```

One file per stack. Ships alongside `stack.yaml`. The aggregator merges every installed stack's boundary at `cos init` into the consumer project's `.coding-os/scaffold-boundary.yaml`.

## Schema

```yaml
version: 1
stack: <stack-id>            # MUST equal stack.yaml::id
roots:                       # Subtree(s) this stack owns. Relative to project root.
  - <path>/                  # Trailing slash required. Conventionally under src/.
file_patterns:               # Globs the stack OWNS (and only this stack may write).
  - "**/*.<ext>"
imports_from:                # Other-stack subtrees this stack MAY import from (read-only).
  - <path>/
forbids_writing_in:          # Other-stack subtrees this stack MUST NEVER write to.
  - <path>/
notes:                       # Optional free-text.
  - <one-line>
```

Every field is required EXCEPT `notes`. Empty arrays (`forbids_writing_in: []`) are accepted; missing keys are rejected by the parser.

## Field semantics

### `version`

Always `1` for now. Bump only if the schema changes incompatibly; old consumer projects pin their boundary file's version.

### `stack`

The stack id from `stack.yaml::id`. Validation: `re.fullmatch(r"[a-z0-9][a-z0-9-]{0,30}", stack)`. The aggregator rejects mismatches.

### `roots`

The directory (or directories) the stack writes into. A multi-stack project has each stack in its own root under `src/`:

```
project/
  src/mobile/        ← react-native root
  src/backend/       ← go-fiber root
  src/ai-service/    ← fastapi root
  src/shared/        ← imports_from target (cross-stack types/contracts)
```

A stack may declare multiple roots only when it legitimately produces files in disjoint trees. Two stacks claiming the same root = aggregator rejects at `cos init`.

### `file_patterns`

Globs whose match implies "this stack owns this file." `enforce-skill.sh` uses these to pick the matching skill on every Write/Edit. Typical:

| Stack | file_patterns |
|---|---|
| nextjs | `src/frontend/**/*.{ts,tsx,js,jsx}` |
| react-native | `src/mobile/**/*.{ts,tsx}` |
| django | `src/backend/**/*.py` |
| go-fiber | `src/backend/**/*.go` |
| fastapi | `src/ai-service/**/*.py` |

When two stacks could match (e.g. fastapi + django both want `**/*.py`), disambiguate with a more specific root prefix.

### `imports_from`

Whitelist of subtrees this stack's source may IMPORT from. Empty list = no cross-stack imports allowed. Standard convention:

```yaml
imports_from:
  - src/shared/        # cross-stack types / contracts
  - src/shared/types/
```

Avoid listing other stack roots here. If your react-native code needs go types, add a contract layer in `src/shared/` instead.

### `forbids_writing_in`

Hard list of subtrees this stack must never write to. PreToolUse Write/Edit hook blocks. Typical:

```yaml
# nextjs/scaffold-boundary.yaml
forbids_writing_in:
  - src/mobile/
  - src/backend/
  - src/ai-service/
```

If the agent's active stack-skill is `nextjs-react` and it tries to Write `src/backend/api.go`, the hook blocks with:

```
BLOCKED: stack 'nextjs' cannot write to src/backend/. Boundary defined at:
  src/templates/nextjs/scaffold-boundary.yaml::forbids_writing_in
Switch to the right skill or open a multi-stack task.
```

## Aggregation at `cos init`

When `cos init -t nextjs,go-fiber,react-native` runs, the CLI:

1. Reads each stack's `scaffold-boundary.yaml`.
2. Validates every `roots` entry is unique across all installed stacks.
3. Validates `imports_from` only references subtrees that exist in the merged set OR `src/shared/`.
4. Writes `.coding-os/scaffold-boundary.yaml` in the consumer project — a flat list of every stack's boundary.

The consumer project's hook reads `.coding-os/scaffold-boundary.yaml` at runtime; it does not re-read the meta-repo.

## Hook integration

`src/core/hooks/enforce-skill.sh` (PreToolUse Write|Edit) consults the consumer's `.coding-os/scaffold-boundary.yaml`:

```
on Write/Edit of <path>:
  matched_stack = first stack whose file_patterns matches <path>
  active_stack = active skill's owner stack (from .coding-os/<agent>/.role)

  if matched_stack and matched_stack != active_stack:
    if <path> in any active stack's forbids_writing_in:
      BLOCK
    else:
      WARN  # cross-stack edit allowed but flagged
```

The hook is fire-and-forget for WARN, BLOCK for forbids — never silent.

## Authoring rules

- One file per stack. Multi-stack rules belong in the consumer project's aggregated copy.
- Use forward-slash paths even on Windows hosts.
- `roots` MUST end with `/` and conventionally start with `src/`; file_patterns MUST be globs.
- Every `forbids_writing_in` entry MUST appear as a `roots` entry in another installed stack — otherwise the rule is unreachable.

## Validation

`tests/test_scaffold_boundary_contract.py` runs on every PR and asserts:

- Every `src/templates/<stack>/scaffold-boundary.yaml` parses as YAML.
- Required keys present; types match.
- `stack` field equals enclosing dir name.
- No two stacks share a root.
- No `forbids_writing_in` entry references a path no installed stack owns.

## Adding a stack

1. Drop `src/templates/<stack>/scaffold-boundary.yaml` per schema above.
2. Run `pytest tests/test_scaffold_boundary_contract.py -q` to verify.
3. Run `make manifest-regen` so `src/core/scaffold_manifest.json` picks the new stack up.
4. Run a smoke `cos init -t <stack> --debug` to confirm aggregation works.
