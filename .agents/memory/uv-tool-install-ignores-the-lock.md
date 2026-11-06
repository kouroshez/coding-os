---
name: uv-tool-install-ignores-the-lock
description: "uv tool install resolves fresh and ignores uv.lock, so an uncapped dependency can jump a major version in the global cos venv and take the MCP server down everywhere."
metadata:
  type: feedback
---

`uv tool install --editable .` does not read `uv.lock`. On 2026-10-25 a reinstall moved `mcp` to 2.x, where `FastMCP` no longer exists, and `cos server-start` crashed at import in every project for 12 days. The repo venv stayed on 1.28, so `server.py --test` and every suite stayed green, and the only check on the delivered tool was `cos --help`.

**Why:** the global `cos` venv is a separate install from `.venv`, and the MCP server runs from it. A green suite proves the lock, not the tool.

**How to apply:** reinstall with the lock as constraints: `uv export --frozen --no-hashes --no-emit-project --extra rag --extra graph-os --extra board-os --extra codex-sdk -o c.txt`, then `uv tool install --editable '.[rag,graph-os,board-os,codex-sdk]' --force --constraint c.txt`. Afterwards run a real MCP handshake through `cos server-start`, not `--help`. Related: [[run-the-feature-not-just-its-tests]].
