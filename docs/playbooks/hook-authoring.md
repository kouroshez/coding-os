<!-- domain:META | layer:playbook | ssot:true | updated:2026-05-08 -->
# Playbook — Authoring a Hook in `core/hooks/`

> P: Step-by-step guide for adding, renaming, or removing a hook in the meta-repo's hook regime.
> R: Adding a PreToolUse / PostToolUse / SessionStart / Stop / UserPromptSubmit hook, or extending an existing one with a new event/matcher.
> S: Configuring a hook in a single consumer project — that is a settings.json change, not a hook authoring task.
> N: [registry.yaml](../../core/hooks/registry.yaml), [hooks-reference.md](../engineering/hooks-reference.md), [adapter-parity.md](../engineering/adapter-parity.md), [bash-heredoc-deadlock.md](../engineering/bash-heredoc-deadlock.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## When to use this playbook

Any time you create, rename, or restructure a hook script under `core/hooks/`, register a new entry in `core/hooks/registry.yaml`, or modify the helper modules under `core/hooks/_helpers/`.

## The model

A hook is a single script that runs synchronously between the agent and the kernel. The hook regime in this repo has four invariants:

1. **`registry.yaml` is the SSOT.** Every hook entry lists its script, category, phase, timeout, and the `(event, matcher)` pairs it fires on. Adapter templates are GENERATED from this file via `make regen-adapter-templates` — never hand-edit `adapters/*/settings.template.json`.
2. **Hooks source `cos-env.sh`.** That helper resolves `$COS_AGENT_DIR`, `$COS_STATE_DIR`, and `$COS_DB_PATH` consistently across Claude / Codex / Cursor and exposes `cos_log_hook` for structured logging.
3. **Block vs warn is explicit.** A `BLOCK` hook prints to stderr and exits non-zero — the agent's tool call is rejected. A `warn` hook prints to stderr and exits zero — the agent sees the message but proceeds. Mixing the two breaks the contract.
4. **Adapter capabilities clip the registry.** Codex doesn't fire `Write|Edit` matchers; Cursor doesn't fire `Skill`. The renderer filters every `(event, matcher)` against `adapters/<id>/adapter.yaml::hook_capabilities`. A registry entry with no capable adapter is fine — it's documented intent — but it shouldn't claim coverage it can't deliver.

## Steps

1. **Decide block vs warn.** Block when the action would corrupt state or violate a hard rule. Warn when the action is suspect but recoverable. If unsure, start with warn and promote later if the misuse rate justifies it.
2. **Write the script.** Bash for fast / shell-glue work, Python via `core/hooks/_helpers/` for anything with logic, JSON parsing, or DB reads.
3. **Use the safe pattern.** Source `cos-env.sh`. Read stdin via `read -r INPUT`. Parse with `jq` or Python — never with `awk` on the JSON envelope. Avoid heredocs in the script body — see [bash-heredoc-deadlock.md](../engineering/bash-heredoc-deadlock.md) for the upstream bash 5.3.9 deadlock that bit us.
4. **Log via `cos_log_hook`.** Format: `cos_log_hook <hook-id> <verb> "key=value key=value"`. The verbs `fire`, `block`, `skip`, `dispatched`, `error` are recognized by the hook log viewer.
5. **Register in `registry.yaml`.** One row per hook, with description, category, phase, timeout, and the `events:` list. Each event entry pairs an `event` (PreToolUse / PostToolUse / SessionStart / UserPromptSubmit / Stop) with a `matcher` (Bash, Write|Edit, Skill, startup, compact|resume, etc.) and an optional `status_message`.
6. **Regenerate adapter templates.** `make regen-adapter-templates`. Verify the diff in `adapters/claude/settings.template.json` (and codex / cursor) matches your intent.
7. **Add a test if behavior is non-trivial.** `tests/test_hook_<name>.py` or extend `tests/test_hook_registry_integration.py`.
8. **Verify shell syntax.** `make verify-hooks` runs `bash -n` on every script under `core/hooks/`.

## Acceptance

- The script exits 0 on success / warn and non-zero on block.
- `make verify-hooks` passes.
- `make regen-adapter-templates` produces a clean diff.
- The hook fires on the intended event for the intended adapter, and is silently dropped on adapters that lack the capability.
- The hook never spawns long-running children (no `wait` on a backgrounded process). Hooks are synchronous; offload async work to a fire-and-forget Python helper.

## Rollback

Hook changes propagate to consumer projects via live symlinks. To roll back: revert the commit and run `cos sync-all` in any consumer that pulled the change. The rendered `adapters/<id>/settings.template.json` is regenerated; consumer-side overrides in `<project>/.claude/settings.json` are not touched.

## Anti-patterns

- Editing `adapters/*/settings.template.json` by hand. The next `make regen-adapter-templates` will overwrite it.
- A block hook with a verbose multi-line error message. Agents truncate; one terse line plus a doc link is the right shape.
- Calling `cos_log_hook` with unstructured prose ("hook ran"). Always use `key=value` so the log viewer can filter.
- A hook that reads a DB row inside a loop. Pre-fetch outside, or call a single `cos_*` tool that does the work server-side.
- A hook with no timeout. The default 1500 ms is the right ceiling for a synchronous step; if more is needed, change the design.
