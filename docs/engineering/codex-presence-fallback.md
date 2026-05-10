<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-25 -->
# Codex GUI Presence Fallback

> P: Workaround for the Codex GUI silently dropping `.codex/hooks.json` events, plus how the meta-repo synthesizes presence in the meantime.
> R: Diagnosing why Codex agent activity is missing from the Hub board, or before changing the presence-write path.
> S: Codex CLI usage (`codex exec`) — hooks fire normally there.
> N: [adapter-parity.md](adapter-parity.md), [hooks-reference.md](hooks-reference.md)

> Nav: [Engineering Index](./00-index.md) | [Docs Index](../00-index.md)

**Status:** workaround. Remove when upstream Codex GUI starts firing `.codex/hooks.json` reliably.

## What's broken upstream

`codex-cli` 0.124 / 0.125 — both the standalone `Codex.app` and the codex binary the Antigravity VSCode extension launches — silently ignores project-level hooks. `~/.codex/log/codex-tui.log` shows the GUI firing only the deprecated `notify=[...]` field as `hook_name=legacy_notify`, then logging:

```
WARN codex_core::session::turn: after_agent hook failed; continuing
hook_name=legacy_notify error=No such file or directory (os error 2)
```

The new event family — `pre-tool-use`, `post-tool-use`, `session-start`, `user-prompt-submit`, `permission-request` — is wired in the binary (we found the strings) but never invoked from the GUI's session loop. `codex exec` (the CLI subcommand) DOES invoke them: `.coding-os/.hooks.log` records `agent=codex` events when `codex exec` runs, never when the GUI does.

## Why coding-os cared

`core/hooks/agent-presence.sh` writes `.coding-os/codex/sessions/<sid>.json` on every Codex lifecycle event. The Hub's `_presence_state(agent)` in `core/web/routes/board.py` reads those files and decides ACTIVE / PRESENT / OFFLINE. With the GUI never firing hooks, the JSON files stay frozen at the last `codex exec` invocation (often hours ago) and the Hub UI shows Codex OFFLINE during active GUI chats — even though the user is typing into Codex on this exact project.

## The fallback

Codex DOES persist a per-turn `~/.codex/sessions/YYYY/MM/DD/rollout-<turn-id>.jsonl`. The first JSON line carries a `cwd` (or `workdir`) field with the absolute project path, and the file's mtime tracks the latest activity in that turn.

`_codex_rollout_recent_for(project_root, window_s)` in `core/web/routes/board.py:88-167` walks at most the last few `YYYY/MM/DD` shards, sorts candidates by mtime descending, short-circuits on the first match within the window. Returns True iff any rollout file's first-line cwd resolves to the same path as the project root and its mtime is within the window.

`_presence_state` calls this fallback **only** when the normal hook-based ladder yields OFFLINE for `agent="codex"`, and only promotes to PRESENT (never ACTIVE — rollouts give us no sub-30 s heartbeat). The behavior diff is therefore strictly additive: any agent that does fire hooks correctly is unaffected.

## When to remove

When Codex GUI honors `.codex/hooks.json`:

1. Verify `.coding-os/.hooks.log` shows `agent=codex` events with sub-second cadence during a real GUI chat.
2. Delete `_codex_rollout_recent_for` and the `if best == "offline" and agent == "codex"` block in `_presence_state`.
3. Remove this doc.

The hooks file (`.codex/hooks.json`) and per-event dispatchers (`.codex/hooks/codex-*-dispatch.sh`) are already correct and require no change — they are simply dormant until upstream wires them up.

## Don't be tempted to

- **Patch Codex's binary.** The strings exist; they're not the missing piece. The session loop's hook invocation is what's not happening.
- **Mirror the rollout-based detection for Claude/Cursor.** Both honor `.claude/settings.json` / `.cursor/hooks.cursor.json` correctly. Adding rollout fallbacks where they aren't needed introduces false-PRESENT readings on stale sessions.
- **Cache the rollout scan more aggressively.** It's already O(50) file stats with a sorted short-circuit. The Hub computes presence on every `/api/board/list` poll (every few seconds in the UI). If profiling shows it as a hotspot, memoize on `current_project_root()` not globally.
