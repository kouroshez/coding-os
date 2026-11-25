---
description: coding-os producer paths for the api-contract-discipline rule — which emit site to read before editing a consumer in this repo.
paths:
  - "src/core/web/ui/src/**"
  - "src/cli/**/*.py"
  - "src/adapters/**/*.py"
  - "tests/**/*.py"
---

# API Contracts — coding-os Producers

The `api-contract-discipline` rule says: read the producer before editing a consumer. In this repo the producers are:

| Consumer | Producer to verify against |
|---|---|
| `src/core/web/ui/src/**` (React fetch / TanStack Query / EventSource) | `src/core/web/routes/**` + the `cos_*` tool the route wraps |
| `src/cli/**` (parsing CLI output of another `cos` command) | the producing CLI's `*_commands.py` or its underlying tool |
| `tests/**` asserting envelope shape | `src/core/thinking_os/tools/_shared.py` (`ok` / `fail` envelope — `docs/engineering/mcp-error-envelope.md`) |
| `src/adapters/<agent>/**` writing presence / state files | the reader hook in `src/core/hooks/` |

Canonical types: `src/core/graph_os/types.py`, `src/core/board_os/types.py`, `src/core/thinking_os/tools/_shared.py`. The tool docstring and `cos_graph_contracts` are not a substitute for the emit site.

The incident behind the rule: `cos_graph_export` emits `source_uid`/`target_uid`, the Hub Graph tab read `e.source`/`e.target`, and every edge was dropped with no error.
