<!-- domain:INFRA | layer:reference | ssot:ref | updated:2026-04-28 -->
# Hook Batching Proposal — PreToolUse Write|Edit super-hooks

Purpose: Design exploration for collapsing N PreToolUse Write/Edit hooks into one batched super-hook.
Read when: Considering hook performance refactors.
Skip when: Looking for the live registry — see src/core/hooks/registry.yaml.
Read next: [registry.yaml](../../src/core/hooks/registry.yaml)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)


Status: **Proposal** (not yet implemented). Drafted 2026-04-27 during the
hook-stack hardening sweep.

## Problem

`.claude/settings.json` registers **18** PreToolUse hooks on the
`Write|Edit` matcher. Each one runs as its own subprocess, reads stdin,
sources `cos-env.sh`, parses the JSON payload via `jq`, performs its
gate, and exits. Per-hook overhead alone is 30–80 ms (process start +
cos-env source + 2 `jq` invocations + 1 `cos_log_hook` write). Cumulative
**worst-case latency on a single Write is ~1.5–2.0 s** for the gates
alone, before any actual semantic work. With outliers (DB-locked,
helper subprocess wedged) the user-perceived stall can pass 5 s.

## Goal

Reduce the 18-hook serial chain to **3 super-hooks**, sharing one
stdin read + one cos-env source + one `jq` payload extraction. Target
latency: ~250 ms p50, ~500 ms p99.

## Proposed Grouping

| Super-hook | Wraps | Rationale |
|---|---|---|
| `pre-write-security.sh` | block-secrets, block-dangerous-commands, block-uv-heredoc, block-protected-files, block-migration-conflict, block-hardcoded-literals | All BLOCKING checks that can refuse the edit. Run first; fast-fail. |
| `pre-write-gates.sh` | thinking_os-gate, enforce-task-start, enforce-doc-anchor, enforce-memory-check, enforce-skill, enforce-zoom, enforce-template, enforce-anti-ambiguity | Workflow gates (state-file based). Run only if security passed. |
| `pre-write-domain.sh` | block-bad-patterns, enforce-graph-context, validate-task-frontmatter, enforce-wip-limit, enforce-task-body, warn-template-drift | Domain-specific lint / validation. Heaviest checks; run last. |

`agent-presence.sh` stays separate (lifecycle hook fired across many
events; would not benefit from being merged into Write|Edit-only batch).

## Mechanism

1. Each `pre-write-*.sh` super-hook reads stdin **once** with
   `cos_read_stdin_bounded 2`, sources `cos-env.sh` once, extracts
   `TOOL`, `FILE_PATH`, `CONTENT`, `OLD_STRING` once via a single `jq -c`.
2. Sources individual checker functions from
   `src/core/hooks/_checkers/<name>.sh`. Each checker is a function (`_check_<name>`)
   that consumes the already-parsed payload via env vars (`COS_HOOK_TOOL`,
   `COS_HOOK_FILE_PATH`, `COS_HOOK_CONTENT`, `COS_HOOK_OLD_STRING`) and
   exits the **outer hook** with 2 if it wants to block.
3. Refactor each existing hook into:
   - A thin shim at `src/core/hooks/<name>.sh` that still works standalone
     (back-compat for direct invocation, tests, ad-hoc debugging).
   - The function body extracted to `src/core/hooks/_checkers/<name>.sh` for
     reuse from the super-hook.

## Migration Plan (8h budget)

1. **Extract checker functions** (3h) — Move each gate's logic into
   `_check_<name>()` in `_checkers/<name>.sh`. Keep the existing
   `<name>.sh` script as a 5-line shim that sources the function and
   passes the parsed payload.
2. **Implement super-hooks** (1h) — Three thin orchestrators that source
   `_checkers/*.sh` files in order, pass shared env vars, fail fast on
   non-zero exit.
3. **Update `settings.json`** (15m) — Replace 18 entries with 3, gated by
   the same matcher. Set per-super-hook timeout (1500 / 1500 / 2000 ms).
4. **Test matrix** (3h) — Each existing hook's behaviour must match
   pre-refactor. New tests:
   - `tests/test_super_hooks.py` — fire each super-hook with the same JSON
     payloads existing tests use, assert identical exit codes + stderr.
   - `tests/test_hook_latency.py` — measure p50/p99 of full chain.
5. **Rollout** (45m) — Behind `COS_USE_SUPER_HOOKS=1` env var for one
   week of dogfooding before flipping default. Old per-hook entries kept
   commented in `settings.json` for fast revert.

## Risks

- **Behavioural drift**: extracting bash functions risks subtle scoping
  bugs (`local` vs global, `set -e` propagation, `exit` vs `return`).
  Mitigation: parity test with byte-identical stderr.
- **Test surface**: The 18 hooks have ~30 small ad-hoc test scripts
  scattered through `src/core/hooks/test-hooks.sh`. All must be re-pointed
  at the super-hook to keep coverage.
- **Shared `set -euo pipefail`**: One checker's `pipefail` failure
  could now kill the whole super-hook. Each `_check_*` function must
  use `local -` or `( subshell )` isolation when running brittle pipes.
- **Override semantics**: `cos_one_shot_override` is per-key. Behaviour
  unchanged — each checker still consumes its own override key.

## Why not now

Performed inline during the 2026-04-27 hardening sweep without the
parity test rig. Refactoring 18 active hooks in one push without
gold-standard parity tests is a footgun. Splitting this off lets us:

- ship the lower-risk fixes (#1–#9) immediately
- prep a parity test harness first
- run super-hooks behind a flag for a week before defaulting on

## Related work

- [hooks-reference.md](hooks-reference.md) — current hook catalogue.
- [registry.yaml](../../src/core/hooks/registry.yaml) — SSOT for hook
  registration that drives adapter template generation.
- [state-files.md](state-files.md) — session-state taxonomy referenced
  by every gate hook.
