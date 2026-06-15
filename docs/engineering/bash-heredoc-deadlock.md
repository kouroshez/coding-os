<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-25 -->
# Bash 5.3.9 + Heredoc Deadlock — Forensics & Discipline

> P: Why hooks running on Homebrew bash 5.3.9 deadlock on heredoc input, and the discipline every hook author must follow until brew ships a fix.
> R: Authoring or debugging any `src/core/hooks/*.sh` script that uses heredocs or pipelines to subprocesses.
> S: Pure Python helpers — the bug only affects bash subshells.
> N: [hooks-reference.md](hooks-reference.md), [mcp-fast-path-entry.md](mcp-fast-path-entry.md)

> Nav: [Engineering Index](./00-index.md) | [Docs Index](../00-index.md)

**Status:** active. The bug is in upstream Homebrew bash 5.3.9 (the binary `#!/usr/bin/env bash` resolves to on macs with `/opt/homebrew/bin` first on PATH). System `/bin/bash` 3.2 is unaffected. Until brew ships a fix, every hook author has to follow the pattern below.

## Symptom

When the user opens Claude Code on a coding-os project, the **first message hangs**. Anthropic VSCode extension logs:

```
Superseded spawn failed (on channel <id>): Subprocess initialization
did not complete within 60000ms — check authentication and network
connectivity
Failed to load config cache: <same error>
```

After ~10 seconds the chat is killed. The MCP servers Claude already booted (graph-indexer, context7, playwright, coding-os, gmail, gcal) all close cleanly.

## Root cause

Two distinct things, only one of which the user can see directly:

1. **Anthropic VSCode extension spawns auxiliary subprocesses** (config-cache loader, session-title generator) shortly after the main chat subprocess. These auxiliaries do a full Claude Code init — including launching every MCP server again — and have a ~10 s budget.

2. **Hook execution leaks zombie bash children.** Every Claude tool call fires the agent-presence.sh hook. That hook (and several other hot-path hooks) used to contain the pattern

   ```bash
   python3 - "$ARG1" "$ARG2" <<'PY'
   import json, os, sys
   ...
   PY
   ```

   On bash 5.3.9 this pattern **sporadically (~20 %) deadlocks before forking python3**. `sample(1)` shows the bash child stuck in `do_redirections → heredoc_write → write` — bash is trying to write the heredoc body to the pipe set up for the child's stdin, but the child has not been forked yet, so nothing is reading. Each deadlock orphans one bash process; over a workday a session accumulates dozens.

The combination is fatal: the auxiliary subprocess from (1) starts while the system is full of zombie hooks from (2), and its 10-second budget runs out before MCP init finishes.

A reproduction with `for i in {1..30}; do echo '{}' | bash agent-presence.sh & done` reliably leaves 5–8 zombies in the dangerous `python3 - <<HEREDOC` form, zero in either of the safe forms below.

## The discipline

### NEVER write this in a hook, installer, or any script invoked frequently

```bash
python3 - "$arg1" <<'PY'
import sys
print(sys.argv[1])
PY
```

### Safe form A — `python3 -c "$(cat <<'PY' ... PY)" args`

```bash
python3 -c "$(cat <<'PY'
import sys
print(sys.argv[1])
PY
)" "$arg1"
```

`cat` reads the heredoc into a string, the command-substitution captures it, and `python3 -c <string>` receives the program as a regular argument. No stdin pipe is ever set up for the child, so the bash bug cannot fire. **Use this for short scripts.**

### Safe form B — extract to `_helpers/<name>.py`

```bash
HELPER="$(_cos_helpers_dir)/<name>.py"   # resolver sourced from cos-env.sh
python3 "$HELPER" "$arg1" "$arg2"
```

Best for hot-path hooks (agent-presence, session-context). The Python file lives in `src/core/hooks/_helpers/` and is invoked as a normal subprocess. Resolve the dir with the shared `_cos_helpers_dir` (in `cos-env.sh`) — it readlink-walks the symlink chain to the source tree. Do NOT use a bare `$(dirname "$0")/_helpers/`: consumer installs symlink each hook `.sh` but not the `_helpers/` subdir, so that path lands in `.claude/hooks/` (no `_helpers/` there) and the helper silently no-ops.

### Why not `python3 -c "literal string"`?

You can, for one-liners. For multi-line code with shell variables or quotes, escaping turns the script unreadable. Forms A and B keep the script as plain Python.

## Programmatic enforcement

`src/core/hooks/block-bad-patterns.sh` rejects Write/Edit on `*.sh` files under `src/core/hooks/`, `src/adapters/*/install*`, `src/adapters/*/hooks/`, or `.{claude,codex}/hooks/` when the diff contains the dangerous regex `python3? +- +.*<<`. Bypass requires editing that hook (which is itself caught by `block-protected-files.sh` unless an active `governance` task is open).

## Related artifacts (this incident)

| File | What changed |
|---|---|
| `src/core/hooks/agent-presence.sh` | Inlined `python3 - <<PY` blocks → `_helpers/presence_write.py` + `_helpers/presence_gc.py` invocations. Added readlink-walk to resolve `_helpers/` from the symlinked install path. |
| `src/core/hooks/_helpers/presence_write.py` (new) | JSON merge + atomic write for presence files. |
| `src/core/hooks/_helpers/presence_gc.py` (new) | Stale presence file GC. |
| `src/core/hooks/auto-task-sync.sh` `check-capture-worked.sh` `cleanup-stale-mcp.sh` `enforce-graph-context.sh` `enforce-wip-limit.sh` `session-context.sh` `validate-task-frontmatter.sh` `capture-work-log.sh` | All converted to safe form A. |
| `src/adapters/claude/install.sh` | Removed `shopt -s nullglob` (alone enough to trigger the bug on the script's own `python3 - <<PY` for .mcp.json). Heredoc moved to `src/adapters/claude/update_mcp_json.py` (mirroring Codex's existing workaround in `src/adapters/codex/ensure_codex_mcp.py`). |
| `src/core/hooks/block-bad-patterns.sh` | Added the regex guard above. |

## Operational note

If you ever see "first message hangs" again on a project that uses coding-os hooks:

```bash
ps -ef | grep -E "src/core/hooks/.*\.sh" | grep -v grep | wc -l
```

If that number is non-trivial (more than 2–3) you have leaked hook zombies. `pkill -9 -f "src/core/hooks/.*\.sh"` clears them. Then audit:

```bash
grep -rE "python3? +- +.*<<" src/core/hooks/*.sh src/adapters/*/install* src/adapters/*/hooks/*.sh
```

Anything that returns is a regression.
