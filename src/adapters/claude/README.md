# Claude adapter (mRNA layer)

- **Install:** `bash src/adapters/claude/install.sh` (or `make sync`).
- **Manifest:** [adapter.yaml](adapter.yaml) — hook capabilities, MCP launch metadata, optional `presence` block for Hub board pills.
- **Agent SDK:** [sdk_dispatcher.py](sdk_dispatcher.py) and other adapter-local scripts. Per **P8** in repo `AGENTS.md`, do not import adapter SDK code from `src/core/**`.
- **Architecture checklist:** [docs/engineering/adapter-parity.md](../../docs/engineering/adapter-parity.md) — how hook, MCP and session capabilities map onto this adapter and `src/core/hooks/`.
