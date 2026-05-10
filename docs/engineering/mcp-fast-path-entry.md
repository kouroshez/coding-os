<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-25 -->
# MCP Server Fast-Path Entry — `cos-mcp-start`

> P: Explanation of the dedicated `cos-mcp-start` entry point that skips the `cli.main` Click overhead, and when the choice between entry points matters.
> R: Editing `.mcp.json`, packaging changes to `pyproject.toml`, or diagnosing slow MCP boot.
> S: General CLI work that doesn't touch MCP server start-up.
> N: [mcp-error-envelope.md](mcp-error-envelope.md), [mcp-schema-traps.md](mcp-schema-traps.md)

> Nav: [Engineering Index](./00-index.md) | [Docs Index](../00-index.md)

## Why two entry points

`.mcp.json` historically pointed at `cos server-start`, which loads `cli.main` — a 380 ms tax for the click app to import every subcommand (`add-stack`, `doctor`, `eject`, `init`, `setup`, `update`, plus the graph_os and board_os command groups). Once the entry point ran the assignment-prefixed `os.execvpe` to `core/thinking_os/server.py`, all that work was thrown away.

That overhead doesn't matter when only one subprocess starts at session boot. It matters a lot when an MCP client opens a SECOND subprocess for auxiliary work (Anthropic VSCode extension's session-title generator, config-cache loader). Under contention — multiple agents, recovering DB locks — the duplicated startup cost was enough to push aux init past the 60 s budget the extension applies.

`cli/mcp_start.py` (registered as the `cos-mcp-start` console_script in `pyproject.toml`) is the same logic with the cli.main import skipped. Cold start drops from ~590 ms (avg over 5 runs) to ~430 ms — a 26 % cut. Under five concurrent boots the worst-case time is ~800 ms.

## What it does

Identical contract to the original `server_start()` body:

1. Resolve `cos_root = parent.parent` of `cli/mcp_start.py`.
2. Set `COS_DB_PATH` and `COS_STATE_DIR` env defaults from `Path.cwd() / .coding-os/`.
3. Sweep stale `core/thinking_os/server.py` instances bound to the same DB (parent dead OR etime > `COS_STALE_SERVER_AGE_S`, default 12 h).
4. `os.execvpe` the same Python interpreter onto `server.py`.

The orphan sweep helper `_sweep_stale_servers` is duplicated between `cli/main.py:_sweep_stale_servers` and `cli/mcp_start.py:_sweep_stale_servers` so neither file imports the other. Keep them in sync — both are simple enough that this is cheaper than a third module.

## Adapter contract

`adapters/claude/update_mcp_json.py` writes a `.mcp.json` block of:

```json
{
  "mcpServers": {
    "coding-os": {
      "command": "cos-mcp-start",
      "args": []
    }
  }
}
```

when `shutil.which("cos-mcp-start")` is truthy, else falls back to `cos server-start`, else to the editable `uv run` form. The Codex adapter (`adapters/codex/ensure_codex_mcp.py`) follows the same precedence.

`make sync` re-runs install for every adapter and rewrites `.mcp.json` to the best entry available on the host PATH at install time.

## Don't

- **Inline this logic into `core/thinking_os/server.py`.** Server.py runs as the MCP child, after exec. By the time it's executing it can't kill its own siblings or set its own env defaults — the parent already chose them.
- **Drop the orphan sweep.** Codex pools MCP children (PPID = `codex app-server`, alive for hours); without the sweep they pile up and contend on the SQLite WAL. The 12 h threshold is conservative — overnight orphans get reaped at the next morning's first agent spawn.
- **Add MCP traffic to the sweep decision.** Heartbeat-based liveness ("did this server answer in the last N seconds?") would require either probing every candidate (slow) or a shared lock file (race-prone). Etime + PPID liveness is the cheapest correct heuristic.
