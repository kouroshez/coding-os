# API Contract Discipline — Don't Guess Field Names

> **Source of truth for field names is the producer, not the consumer.**
> Frontend components, CLI parsers, dashboards, and tests are consumers — they MUST verify every field they read against the producer's actual response, not against memory, naming intuition, or another consumer.

Drift between producer shape and consumer expectation is a silent bug: TS reads `undefined`, Python returns `None`, `JSON.parse` never fails — the agent only notices when a human says "the page is empty." Hooks can't catch it. Canonical example: `cos_graph_export` emits `source_uid`/`target_uid`, but the Hub Graph tab read `e.source`/`e.target` → every edge silently dropped, empty canvas, zero errors (TASK-117).

## Rule (mandatory before Write/Edit on any API consumer)

Before authoring or editing **any** code that reads an API / MCP / RPC / CLI response, perform ONE of the following two checks and quote the result in your reasoning before producing the diff:

1. **Read the producer.** Open the handler / Pydantic model / dataclass / SSOT type that emits the response and copy the exact field names. Canonical types: `src/core/graph_os/types.py`, `src/core/board_os/types.py`, `src/core/thinking_os/tools/_shared.py`. The tool docstring and `cos_graph_contracts` are NOT a substitute — read the emit site.
2. **Hit the live endpoint.** Run one request (`curl`/`cos`/`mcp tool`) and pretty-print one item's `.keys()`. Use when no SSOT type exists or the route layer wraps/renames.

Both checks are cheap. Either one alone is sufficient. **Skipping both is a critical error** — equivalent to writing code from imagination.

## Anti-patterns (reject in review, fix on sight)

- Naming a field by intuition ("`source` is natural") — it's whatever the producer emits.
- Copy-pasting an interface from a sibling consumer — that consumer might be wrong; verify against the producer.
- Inferring shape from a consumer-side type alias — the alias is the *expectation*, not the contract.
- "The API used to return X" — re-verify; schema changes don't page the consumer.
- Adding `?` / `| null` to silence a TS error without checking the producer — that hides drift instead of fixing it.

## Where this rule applies

| Consumer | Producer to verify against |
|---|---|
| `src/core/web/ui/src/**` (React fetch / TanStack Query / EventSource) | `src/core/web/routes/**` + the `cos_*` tool the route wraps |
| `src/cli/**` (parsing CLI output of another `cos` command) | the producing CLI's `*_commands.py` or its underlying tool |
| `tests/**` asserting envelope shape | `src/core/thinking_os/tools/_shared.py` (`ok` / `fail` envelope) |
| `src/adapters/<agent>/**` writing presence / state files | the reader hook in `src/core/hooks/` |
| External integration glue (webhooks, Slack, GitHub) | the third-party docs / a real captured payload, not your memory |

**Spotting drift after the fact:** a UI panel empty with no console error, a CLI summary suddenly showing zeros, or a test passing after a backend rename → suspect contract drift first. Run the producer check and diff field names; don't add fallbacks until you've confirmed the producer's current shape.

## See also

- [docs/engineering/mcp-error-envelope.md](../../docs/engineering/mcp-error-envelope.md) — `ok` / `fail` envelope contract
- `cos_graph_contracts` MCP tool — list of HTTP/MCP/event handlers in the graph
- [test-discipline.md § Run the deliverable](test-discipline.md) — the runtime/behaviour sibling of this rule (Critical Rule 26: don't guess a *behaviour* contract — verify by executing, not by reading)
