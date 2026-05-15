#!/usr/bin/env bash
# DEPRECATED 2026-04-25 — kept as a no-op stub.
#
# WHY THIS WAS REMOVED:
#   When invoked as a SessionStart hook the script iterated over every
#   running `src/core/thinking_os/server.py` instance and ran a `python3 -c
#   "$(cat <<'PY' ... PY)" "$etime"` per match to parse elapsed time. On
#   Homebrew bash 5.3.9 the heredoc deadlock that the wider codebase
#   defends against re-emerged in this loop body — sample(1) showed bash
#   stuck in heredoc_write on the 4th-or-5th iteration. The hook was
#   therefore the direct cause of "Subprocess initialization did not
#   complete within 60000ms" errors at session start, the very symptom
#   it was added to defeat.
#
# WHAT REPLACES IT:
#   The orphan sweep now lives ONLY in the MCP entrypoints:
#     • src/cli/mcp_start.py   — fast-path `cos-mcp-start`
#     • src/cli/main.py:server_start — legacy `cos server-start`
#   Both run `_sweep_stale_servers` BEFORE booting their server.py child.
#   Every MCP boot therefore reaps stale siblings automatically, with no
#   per-tool-call hook overhead and no chance of bash 5.3.9 deadlocking
#   inside a SessionStart timer.
#
# WHY THIS FILE STILL EXISTS:
#   Existing project installs may have `.claude/settings.json` /
#   `.codex/hooks.json` referencing this script before they re-run
#   `cos sync-doctor --repair`. Hitting a missing file would surface as
#   a hook error in the agent log. Exiting 0 immediately is the cleanest
#   bridge until those projects refresh their settings.
#
# DO NOT REINTRODUCE THIS HOOK to registry.yaml. The orphan-sweep logic
# belongs in the entrypoints, not in a hook fired on every session start.
exit 0
