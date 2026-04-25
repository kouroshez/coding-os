# Claude adapter (mRNA layer)

- **Install:** `bash adapters/claude/install.sh` (or `make sync`).
- **Manifest:** [adapter.yaml](adapter.yaml) — hook capabilities, MCP launch metadata, optional `presence` block for Hub board pills.
- **Agent SDK:** [sdk_dispatcher.py](sdk_dispatcher.py) and other adapter-local scripts. Per **P8** in repo `AGENTS.md`, do not import adapter SDK code from `core/**`.
- **Architecture checklist:** Anthropic Certified Architect foundations guide (repo copy under `docs/code-os-core-docs/instructor_Claude+Certified+Architect+–+Foundations+Certification+Exam+Guide.md`) — hooks / MCP / session topics map to this adapter + `core/hooks/`; see [docs/engineering/adapter-parity.md](../../docs/engineering/adapter-parity.md).
