---
name: hook-authoring
tier: stack
domain: [governance]
description: Author production-grade hooks for the coding-os meta-repo — Bash scripts under src/core/hooks/ and Python helpers under src/core/hooks/_helpers/. Enforces SSOT registration in registry.yaml (Rule 10), source cos-env.sh (Rule 3), agent-agnostic env vars not hardcoded .claude/ (Rule 1, P2), proper event/matcher declaration, adapter capability filtering, and the regen pipeline. Pairs with meta-engineering, clean-code, and thinking_os.
last_reviewed: "2026-05-11"
---

# hook-authoring

Purpose: Every hook in `src/core/hooks/` propagates via live symlinks to every consumer project that registers any adapter. A buggy hook breaks N projects at once. The same shape, every time, keeps the ~50 hooks coherent.

Read when: editing files matching:
- `src/core/hooks/*.sh` — hook scripts.
- `src/core/hooks/_helpers/*.py` — Python helpers invoked by hooks.
- `src/core/hooks/registry.yaml` — the SSOT for hook registration.
- `src/adapters/<id>/adapter.yaml` (`hook_capabilities` block) — runtime capability filter.

Skip when: editing hook *tests*, runtime presence files in `.coding-os/`, generated adapter templates.

## The Three Hard Contracts

Every hook MUST satisfy:

### 1. Source `cos-env.sh` (Rule 3)

The first non-comment lines of every hook:

```bash
#!/usr/bin/env bash
# What this hook does, one line.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
```

`cos-env.sh` exports `$COS_STATE_DIR`, `$COS_AGENT`, `$COS_AGENT_DIR`, `$COS_DB_PATH`, etc. Without it, the hook will reach for hardcoded `.claude/` paths and break on Codex/Cursor.

### 2. Never hardcode `.claude/` (Rule 1, P2)

```bash
# WRONG
state_file=".claude/state/something"

# RIGHT
state_file="$COS_AGENT_DIR/something"
# or, if it's session-shared across agents:
state_file="$COS_STATE_DIR/something"
```

The `block-hardcoded-literals.sh` hook audits the diff and blocks `.claude/` literals in `src/core/**`.

### 3. Register in `registry.yaml` (Rule 10, SSOT)

A new hook file is invisible until registered. Add an entry to [src/core/hooks/registry.yaml](../../../core/hooks/registry.yaml):

```yaml
- id: my-new-hook
  script: my-new-hook.sh
  event: PreToolUse        # PreToolUse | PostToolUse | UserPromptSubmit | Stop | SessionStart | PostToolUseFailure | SubagentStart | SubagentStop
  matcher: "Write|Edit"    # tool matcher (event-specific) — empty = match-all where allowed
  phase: gate              # gate | observation | enforcement | telemetry
  category: governance     # documentation | governance | safety | telemetry | task | skill | graph | ...
  description: "One line — what the hook does."
  blocking: true           # exit 2 blocks the tool call; false = soft warn only
  adapters: ["claude", "codex", "cursor"]  # which adapters to render this hook into
```

After registry edit:

```bash
make regen-adapter-templates
```

This rewrites `adapters/{claude,codex,cursor}/settings.template.json` from the registry, filtering by each adapter's `hook_capabilities`.

## Hook Lifecycle by Phase

| Phase | What it does | When it fires | Exit code semantics |
|---|---|---|---|
| **gate** | Block disallowed actions before they happen | PreToolUse | `exit 2` = block; `exit 0` = allow |
| **observation** | Record state without blocking | UserPromptSubmit, PostToolUse | always `exit 0`; side effects are the point |
| **enforcement** | Require something before the action | PreToolUse | `exit 2` = block; emits remediation message |
| **telemetry** | Append to logs / DB without affecting flow | PostToolUse, Stop | always `exit 0` |

Mixing phases (e.g. a "gate" that also writes telemetry) is fine as long as the exit code follows the gate's contract.

## Adapter Capability Filtering

Each adapter declares its `hook_capabilities` in `src/adapters/<id>/adapter.yaml`:

```yaml
hook_capabilities:
  PreToolUse:
    matchers: [Bash, "Write|Edit", "Write|Edit|MultiEdit", Skill, Read]
  PostToolUse:
    matchers: [Bash, "Write|Edit", "Write|Edit|MultiEdit", Skill, "mcp__coding-os__cos_backtrack_log"]
  # ...
```

The renderer (`src/cli/hook_renderer.py`) skips registry entries whose `{event, matcher}` isn't in the adapter's capabilities. **Codex CLI, for instance, only has Bash-matcher PreToolUse/PostToolUse — so a `Write|Edit` hook is silently skipped for codex.** This is correct, not a gap.

If your hook needs to fire on Codex but the matcher isn't supported, two options:
1. Reformulate the matcher (e.g. wrap the Bash command instead of the Edit tool).
2. Wait for the agent to ship the matcher; declare the hook only for capable adapters.

**Don't** force a matcher into an adapter that doesn't support it — the install will validate against the YAML and refuse.

## Reading + Writing Hook Input

Hook stdin is a JSON envelope from the agent. Use the helper:

```bash
INPUT="$(cos_read_stdin_bounded 2)"      # 2 MB cap
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
PROMPT=$(echo "$INPUT" | jq -r '.user_prompt // empty' 2>/dev/null || echo "")
```

`cos_read_stdin_bounded` is sourced from `cos-env.sh`. It safely reads stdin with a size cap (protects against runaway agent output).

To **block** with a message the agent will see:

```bash
echo "BLOCKED: <human-readable reason + remediation>" >&2
exit 2
```

The message on stderr is shown to the agent — write it as advice, not just a complaint. Include the fix.

## Python Helpers (`src/core/hooks/_helpers/`)

When the hook needs more than ~30 lines of logic or any non-trivial parsing, write a Python helper:

```python
# src/core/hooks/_helpers/my_check.py
"""Check XYZ and emit JSON verdict to stdout."""
from __future__ import annotations
import json
import sys

def main() -> int:
    payload = json.load(sys.stdin)
    file_path = payload.get("tool_input", {}).get("file_path", "")

    if _violates_rule(file_path):
        json.dump({"verdict": "block", "message": "..."}, sys.stdout)
        return 0  # exit code 0 — the verdict in JSON is the signal

    json.dump({"verdict": "allow"}, sys.stdout)
    return 0


def _violates_rule(path: str) -> bool:
    ...


if __name__ == "__main__":
    sys.exit(main())
```

Invoke from the Bash hook:

```bash
verdict_json=$(echo "$INPUT" | python3 "$(dirname "$0")/_helpers/my_check.py")
verdict=$(echo "$verdict_json" | jq -r '.verdict')
if [ "$verdict" = "block" ]; then
    echo "$verdict_json" | jq -r '.message' >&2
    exit 2
fi
```

This pattern keeps the Bash hook thin, makes the Python testable, and centralizes stdin parsing in one place.

## State Files (`$COS_AGENT_DIR/*`)

Hooks communicate via session-scoped state files:

| File | Purpose | Lifecycle |
|---|---|---|
| `.task-current` | Active task marker | Session |
| `.thinking_os-gate` | Cynefin classification | 120 min |
| `.doc-anchor` | Doc-anchor for current edit | Single edit |
| `.graph-context-<uid>` | Graph context already loaded | Session |
| `.skill-<name>` | Skill loaded this session | Session |
| `.swimlane` | Active swimlane (frontend/backend/...) | Session |

Use `write-state.sh` to write:

```bash
bash src/core/hooks/write-state.sh "$COS_AGENT_DIR/.thinking_os-gate" "COMPLICATED 3"
```

`write-state.sh` handles atomic write + session-id prefix. Don't roll your own.

## Logging

Hooks should log every blocking decision to `make log-write`:

```bash
if [ "$verdict" = "block" ]; then
    bash src/core/scripts/log-write.sh \
        --type "hook-block" \
        --msg "block-protected-files" \
        --what "$(basename "$FILE_PATH")" \
        --files "$FILE_PATH" 2>/dev/null || true
fi
```

`|| true` so a logging failure never blocks the actual hook decision.

## Testing

Hook tests live in `tests/test_hooks_*.py`:

```python
# tests/test_my_hook.py
import json
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "core" / "hooks" / "my-new-hook.sh"


def _run_hook(payload: dict) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=5,
    )
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()


def test_blocks_disallowed_file() -> None:
    code, _, err = _run_hook({"tool_input": {"file_path": "/etc/passwd"}})
    assert code == 2
    assert "BLOCKED" in err


def test_allows_normal_file() -> None:
    code, _, _ = _run_hook({"tool_input": {"file_path": "src/main.py"}})
    assert code == 0
```

Run: `make verify-hooks` (shellcheck warn + bash -n + behavior tests).

## Anti-patterns (reject in review)

- **Hook script not in `registry.yaml`** — won't be rendered to any adapter. Silently dead.
- **Hardcoded `.claude/` path** — breaks Codex, Cursor. Use `$COS_AGENT_DIR`.
- **Missing `source cos-env.sh`** — env vars unset, hook fails silently or wrong.
- **Returning `exit 1` on a block** — must be `exit 2`. `1` means "tool errored", `2` means "blocked by policy".
- **`set -e` without `set -euo pipefail`** — partial failure modes leak.
- **Block message without remediation** — agent doesn't know how to fix it. Always include "to fix: ...".
- **Hook that always fires even when no relevant file** — wasted overhead. Filter by matcher / first lines of stdin parse.
- **Slow hook (>200ms)** — drags every tool call. Either fast-path-out for the no-op case or move logic to PostToolUse / async telemetry.
- **Python helper without test** — Python failures are harder to debug from inside Bash.

## Verification (after authoring)

```bash
# Syntax + shellcheck
make verify-hooks

# Behavior tests
uv run pytest tests/test_my_hook.py -q

# Adapter render
make regen-adapter-templates

# Live install smoke (Claude adapter)
make test-install-claude
```

Pre-merge: `make verify` + `cos doctor`.

## Tooling

Scaffold a registry-compliant hook skeleton (sources cos-env, strict mode, log calls):
`bash scripts/new_hook.sh --name my-guard --category enforcement`

## See also

- [assets/hook-checklist.md](assets/hook-checklist.md) — the authoring + registration gate.
- [Rule 3 — Hooks source cos-env.sh](../../../docs/governance/critical-rules.md#rule-3--hooks-source-cos-envsh)
- [Rule 10 — Regenerate derived artifacts](../../../docs/governance/critical-rules.md#rule-10--regenerate-derived-artifacts)
- [src/core/hooks/registry.yaml](../../../core/hooks/registry.yaml) — SSOT.
- [Hook Authoring Playbook](../../../docs/playbooks/hook-authoring.md) (if present).
- [meta-engineering](../meta-engineering/SKILL.md) — three-layer authoring discipline.
