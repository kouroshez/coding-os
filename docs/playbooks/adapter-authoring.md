<!-- domain:META | layer:playbook | ssot:true | updated:2026-05-08 -->
# Playbook — Authoring or Modifying an Adapter

> P: Procedure for adding a new agent adapter under `adapters/<id>/` or modifying an existing one (Claude / Codex / Cursor).
> R: Adding a new agent runtime, bumping an adapter's SDK floor, expanding capability declarations, or porting a hook to a new adapter.
> S: Day-to-day Claude work — see [claude-sdk.md](../adapters/claude-sdk.md) instead.
> N: [claude-sdk.md](../adapters/claude-sdk.md), [adapter-parity.md](../engineering/adapter-parity.md), [hooks-reference.md](../engineering/hooks-reference.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## The mental model

An adapter is the **mRNA layer** that translates the agent-agnostic kernel (`core/`) into a specific agent's filesystem layout. Each adapter must self-contain enough configuration that a consumer project can install and run it independently of any other adapter.

Three contracts every adapter must satisfy:

1. **`adapter.yaml`** declares the agent's identity, the directory layout it expects (`hooks_dir`, `rules_dir`, `skills_dir`, `commands_dir`), and the `hook_capabilities` list — the `(event, matcher)` pairs the runtime can actually fire.
2. **A settings template** (e.g. `adapters/claude/settings.template.json`) is GENERATED from `core/hooks/registry.yaml` by `cli/hook_renderer.py`. The renderer filters registry entries against `hook_capabilities` so an adapter never claims coverage it cannot deliver.
3. **`install.sh`** is the consumer-side entry point. It must be idempotent and source-of-truth-compatible — running it twice on the same project produces no diff.

## Steps to add a new adapter

1. **Create the adapter directory.** `adapters/<id>/` with `adapter.yaml`, `install.sh`, and the settings template stub.
2. **Fill `adapter.yaml`.** Identity, paths, capabilities. The capability list is the most important field — every absent pair becomes silent coverage gap, not a hidden bug. Be honest about what the runtime supports.
3. **Implement `install.sh`.** Symlink hooks from `core/hooks/` into the consumer's `<adapter-dir>/hooks/`, render the settings file, write any agent-specific helpers (e.g. Claude's hooks expect Skill registration; Codex doesn't).
4. **Add adapter SDK glue if needed.** A formula-dispatcher implementation (`adapters/<id>/sdk_dispatcher.py` matching the protocol in `adapters/claude/sdk_dispatcher.py`). Register it via the dispatcher factory in `core/thinking_os/cognition.py`. P8 Adapter-SDK autonomy: the kernel must NOT import an adapter SDK directly.
5. **Run the renderer.** `make regen-adapter-templates`. The first run produces a complete `adapters/<id>/settings.template.json` with only the events the adapter can deliver.
6. **Write the parity test.** `tests/test_adapter_parity.py` — at minimum, assert the rendered template matches a golden snapshot at `tests/golden/<id>_base/`.
7. **Document the gaps.** Update [adapter-parity.md](../engineering/adapter-parity.md) with the new adapter's coverage matrix and the architectural reasons for any missing pairs.

## Steps to modify an existing adapter

1. **Locate the SSOT.** SDK pin → `adapter.yaml` or `pyproject.toml`. Hook coverage → `hook_capabilities` in `adapter.yaml` plus `core/hooks/registry.yaml`. Settings shape → `cli/hook_renderer.py`.
2. **Edit the SSOT.** Never edit the generated artifact (`settings.template.json`) directly.
3. **Regenerate.** `make regen-adapter-templates`.
4. **Update golden tests.** Recapture with `uv run python scripts/capture_golden.py`. Review the diff line by line — silent coverage shifts are real bugs.
5. **Document migration.** If consumers must take action, write a short note under `docs/adapters/<id>-migration-<date>.md` and link it from the adapter's main reference.

## Acceptance

- `make regen-adapter-templates` is a no-op on a clean checkout.
- `tests/test_adapter_parity.py` and `tests/test_adapters.py` pass.
- `cos doctor` reports the adapter as healthy in a freshly scaffolded project.
- The adapter's `hook_capabilities` list matches the agent's actual runtime (verified by reading the agent's hook spec, not by guessing).
- No core code imports the adapter's SDK (P8 Adapter-SDK autonomy).

## Rollback

Adapter changes are propagated through `cos sync-all` to existing projects. To roll back: revert the commit, regenerate templates, and ask consumers to re-run `cos sync-all`. If a consumer has already pulled the change and edited their local settings, the local edits survive — only the template is rewritten.

## Anti-patterns

- Putting agent-specific imports inside `core/`. P8 violation; refuse.
- Hand-editing `settings.template.json` to add a hook the registry doesn't know about. The next regen wipes it.
- Declaring `hook_capabilities` aspirationally — claiming a matcher the runtime doesn't fire. The renderer happily emits the entry, but it's dead weight in the consumer's settings.
- Writing an `install.sh` that mutates files outside `<adapter-dir>/`. Side effects must be confined to the adapter's directory and `.coding-os/`.
