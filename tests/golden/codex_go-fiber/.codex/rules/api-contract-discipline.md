---
description: Anti-hallucination rule — verify response field names against the backend SSOT before writing or editing any API consumer (UI fetcher, CLI parser, script, test).
globs: "**/*"
alwaysApply: true
---

# API Contract Discipline — Don't Guess Field Names

> **Source of truth for field names is the producer, not the consumer.**
> Frontend components, CLI parsers, dashboards, and tests are consumers — they MUST verify every field they read against the producer's actual response, not against memory, naming intuition, or another consumer.

## Why this rule exists

A class of silent bugs comes from drift between the API response shape and the consumer's expectation. TypeScript happily reads `undefined` for a renamed field; Python silently returns `None`; JSON.parse never fails. The agent only notices when a human says "the page is empty." Examples already seen in this repo:

- Hub Graph tab: `cos_graph_export` returns edges with `source_uid` / `target_uid`. Frontend `graph-adapter.ts` and `ContainsTree.tsx` read `e.source` / `e.target` → every edge silently dropped → empty tree, empty canvas, zero console errors. (TASK-117)

A consumer that loosely-typed-against-undefined fails the user, not the test suite. Hooks cannot catch this. The agent must be disciplined.

## Rule (mandatory before Write/Edit on any API consumer)

Before authoring or editing **any** code that reads an API / MCP / RPC / CLI response, perform ONE of the following two checks and quote the result in your reasoning before producing the diff:

1. **Read the producer.** Open the server-side handler / Pydantic model / dataclass / SSOT type that emits the response and copy the exact field names. For coding-os, the canonical types live in `src/core/graph_os/types.py`, `src/core/board_os/types.py`, `src/core/thinking_os/tools/_shared.py`. The MCP tool docstring and `cos_graph_contracts` are NOT a substitute — read the actual emit site.
2. **Hit the live endpoint.** Run a single request (`curl`, `cos ...`, `mcp tool`) and pretty-print one item: `python3 -c "import json,sys; d=json.load(open('/dev/stdin')); print(list(d.get('data',{}).get('items',[{}])[0].keys()))"`. Use this when no SSOT type exists or you suspect the producer wraps/renames at the route layer.

Both checks are cheap. Either one alone is sufficient. **Skipping both is a critical error** — equivalent to writing code from imagination.

## Anti-patterns (reject in review, fix on sight)

- "I'll call the field `source` because that's the natural name." → No. The field is whatever the producer emits.
- Copy-pasting an interface from another project / another file in the same project as the basis for a new consumer. → That sibling consumer might be wrong. Verify against the producer.
- Inferring shape from a TypeScript / Python type alias on the consumer side. → The alias is the consumer's *expectation*, not a contract. Producers can drift.
- "The API used to return X." → Re-verify. Schema changes do not page the consumer.
- Adding a `?` / `| null` to silence a TypeScript error without checking what the producer actually emits. → That hides the drift instead of fixing it.

## Where this rule applies

| Consumer | Producer to verify against |
|---|---|
| `src/core/web/ui/src/**` (React fetch / TanStack Query / EventSource) | `src/core/web/routes/**` + the `cos_*` tool the route wraps |
| `src/cli/**` (parsing CLI output of another `cos` command) | the producing CLI's `*_commands.py` or its underlying tool |
| `tests/**` asserting envelope shape | `src/core/thinking_os/tools/_shared.py` (`ok` / `fail` envelope) |
| `src/adapters/<agent>/**` writing presence / state files | the reader hook in `src/core/hooks/` |
| External integration glue (webhooks, Slack, GitHub) | the third-party docs / a real captured payload, not your memory |

## How to spot drift after the fact

If a UI panel renders empty with no console error, or a CLI summary suddenly shows zeros, or a test passes after a backend rename — suspect contract drift first. Run the producer-side check above and diff field names. Don't add fallbacks until you've confirmed the producer's current shape.

## See also

- [docs/engineering/mcp-error-envelope.md](../../docs/engineering/mcp-error-envelope.md) — `ok` / `fail` envelope contract
- `cos_graph_contracts` MCP tool — list of HTTP/MCP/event handlers in the graph
