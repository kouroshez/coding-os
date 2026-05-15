---
description: Rule for authoring shell hooks under src/core/hooks/. Enforces SSOT registration, $COS_* env discipline, fail-closed exception handling, shellcheck compliance, and the regen pipeline that propagates a new hook to every adapter.
globs: "src/core/hooks/*.sh,src/core/hooks/_helpers/*.py,src/core/hooks/registry.yaml"
alwaysApply: false
---

# Hook Authoring Rule

Source of truth: [src/core/hooks/registry.yaml](../../../core/hooks/registry.yaml) (SSOT).
Pattern reference: any existing hook in `src/core/hooks/` (e.g. `enforce-graph-context.sh`).

## Anatomy of a compliant hook

```bash
#!/usr/bin/env bash
# <name>.sh (Phase X) — <one-line purpose>.
#
# <2-3 line description: what events fire this, what it does, what
#  state it reads/writes, debounce strategy, fail-open vs fail-closed.>
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook <hook-id> enter || true

# 1. Read stdin (Claude/Codex/Cursor pass tool_input as JSON).
INPUT="$(cos_read_stdin_bounded 2)"

# 2. Extract via jq with safe defaults.
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")

# 3. Use $COS_AGENT_DIR / $COS_STATE_DIR — NEVER hardcode .claude/.
MARKER="${COS_AGENT_DIR}/.<hook-id>-marker"

# 4. Decide; warn vs block.
if [[ <bad-condition> ]]; then
  echo "warning: <message>" >&2          # exit 0 → warn
  cos_log_hook <hook-id> warn || true
  exit 0
fi

# Or, for strict block:
# echo "BLOCKED: <reason>" >&2; exit 2

cos_log_hook <hook-id> ok || true
exit 0
```

## Mandatory steps

1. **Drop the script** in `src/core/hooks/<name>.sh`. Make executable: `chmod +x`.
2. **Source `cos-env.sh`** at the top — gives you `$COS_AGENT_DIR`, `$COS_STATE_DIR`, `$COS_DB_PATH`, `cos_log_hook`, `cos_read_stdin_bounded`. (Rule 3.)
3. **Register in `src/core/hooks/registry.yaml`** with: `id`, `script`, `description`, `category` (safety|enforcement|observability|reminder|cognition|retrieval|meta), `phase`, `timeout`, and `events: [{event, matcher, status_message}, …]`.
4. **Re-render adapter templates**: `make regen-adapter-templates`.
5. **Re-render this repo's `.claude/`**: `bash src/adapters/claude/install.sh` (or `make dogfood-full` for all adapters).
6. **For Codex**: if your event/matcher pair is in the dispatcher (Codex coalesces UserPromptSubmit / Stop / SessionStart), add the script to `src/adapters/codex/adapter.yaml::hook_dispatchers[event].delegates` AND to the `codex-<event>-dispatch.sh` for-loop.

## Hard rules

- **Never hardcode `.claude/`** in `src/core/hooks/**` (Rule 1, P2). Use `$COS_AGENT_DIR`. The audit hook `block-hardcoded-literals.sh` flags violations.
- **MUST use `set -euo pipefail`** at the top — fail loud, not silent.
- **`grep -oE` returns 1 on no match** — wrap with `{ ... || true; }` so `pipefail` doesn't kill the hook on zero matches.
- **bash 5.3.9 deadlock** on `$(python3 - <<HEREDOC)` patterns — extract to `_helpers/<name>.py` (Rule 8).
- **Exit codes**: `0` = pass / warn (printed to stderr). `2` = BLOCK (Claude shows the message, edit cancelled). Never use other non-zero codes.
- **Path resolution**: always `Path(...).resolve()` before `relative_to()` on macOS (`/tmp` vs `/private/tmp`) — Rule 5.
- **Fail-open vs fail-closed**: enforcement / safety = fail-closed (BLOCK). Observability / reminders / capture = fail-open (always exit 0 even on internal error; log to `.coding-os/.<hook>.log`).

## Debounce + idempotency

- **Per-session marker**: file in `$COS_AGENT_DIR/.<hook-id>-marker` (cleared by `session-context.sh` at SessionStart).
- **Per-input marker**: hash of the input → file in `$COS_AGENT_DIR/.<hook-id>/<sha1>` (e.g. `enforce-graph-context.sh`).
- **Time debounce**: `src/core/hooks/check-state.sh` exposes `check_state <file> <ttl-seconds>`.

## Verification

- `make verify-hooks` — runs `bash -n` syntax + shellcheck warning level on every hook.
- `make test-hooks` (or `bash src/core/hooks/test-hooks.sh`) — full hook smoke suite.
- Manual smoke: pipe a synthetic JSON input and assert exit code + stderr.
