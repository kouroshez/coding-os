# Stability Contract — what 1.0 freezes

The concrete surface behind the six
[1.0 cut criteria](release-process.md#100-cut-criteria-task-079): what a
consumer may depend on, what stays experimental, and how a frozen surface is
ever allowed to change. On `0.x` nothing below is guaranteed yet — this doc is
the promise we are ratcheting toward, and every `!` commit is measured against
it.

## Frozen at 1.0 (the public surface)

| Surface | Contract |
|---|---|
| `cos` CLI | Command names, required args, and exit-code semantics of the documented commands (`init`, `update`, `doctor`, `task-*`, `board`, `pr *`, `hub start`, `graph-reindex`). New flags may appear; existing ones keep meaning. |
| `cos_*` MCP tools | Tool names, argument names/types, and the `ok(data)` / `fail(category, message, retryable)` envelope ([mcp-error-envelope.md](../engineering/mcp-error-envelope.md)). New optional args and new `meta` keys are non-breaking. |
| `$COS_*` environment | `COS_STATE_DIR`, `COS_AGENT_DIR`, `COS_PANEL_DIR`, `COS_DB_PATH`, `COS_PROJECT_ROOT` names and meaning. |
| Scaffold shape | `cos init` output tree (`AGENTS.md`, `Makefile`, `.coding-os/`, docs roots) as pinned by `tests/golden/**`. |
| Hook contract | Hook event names, `registry.yaml` schema, exit-code semantics (0 pass / 2 block), and the `cos-env.sh` sourcing convention. |
| Adapter contract | `adapter.yaml` schema (`hook_capabilities`, entrypoint declarations). |
| Graph uid grammar | `code:function:<path>::<name>` et al. ([graph_os types](../../src/core/graph_os/types.py)) — memories and docs reference uids, so the grammar never changes shape. |
| Board lifecycle | Task statuses (`icebox → in_progress → testing → complete`, `blocked`, `archive`) and the four axes (swimlane · kind · epic · labels). |
| DB schema direction | Migrations stay append-only (Rule 9); a released migration is never edited. |

## Explicitly NOT frozen (may change in any minor)

- Internal module layout (`_mcp_*`, `doctor_checks_*`, `_graph_*` siblings) —
  import from the public facades, never from private siblings.
- Hub HTTP routes and UI (`src/core/web/**`) — the UI is versioned with the
  server it ships with.
- Prompt/rule/skill wording — `cos update` re-renders them by design.
- Heuristics: complexity scores, graph edge confidence, retrieval ranking,
  token estimators.
- Anything under `docs/engineering/` describing internals.

## Deprecation policy (criterion 6)

Post-1.0, a frozen surface changes only through this ladder, spread over **at
least two minor releases**:

1. **Deprecate (minor N):** the old form keeps working; using it emits a
   runtime warning naming the replacement; CHANGELOG + the release notes call
   it out; docs update to the new form.
2. **Warn (minor N+1):** warning becomes prominent (stderr on every use);
   migration notes ship in the release.
3. **Remove (major):** the old form is deleted — only in a major version.

Accelerated removal is allowed solely for security fixes, and the release
notes must say so. Pre-1.0, breaking changes need only a `feat!:` /
`BREAKING CHANGE:` commit marker (release-please then bumps the minor).

## Verification hooks

- Scaffold freeze: `tests/golden/**` + `uv run pytest tests/test_template_scaffold.py`.
- Envelope freeze: `tests/**` asserting against `_shared.py` (Rule 13) + `python src/core/thinking_os/server.py --test`.
- Signature freeze: `docs/governance/mcp-tool-inventory.md` is regenerated —
  a diff on a released tool's signature is a review-blocking event.

## See also

[release-process.md](release-process.md) · [ci-gates.md](../engineering/ci-gates.md) ·
[KNOWN_LIMITATIONS.md](../../KNOWN_LIMITATIONS.md) · [GOVERNANCE.md](../../GOVERNANCE.md)
