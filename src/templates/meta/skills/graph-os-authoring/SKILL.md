---
name: graph-os-authoring
description: Author the graph_os knowledge-graph internals — extractors, backends, indexers, queries. Use when adding a new node/edge type, writing a new extractor (Python AST, doc-headings, etc.), evolving the SQLite backend, or modifying the reindex dispatcher. Enforces idempotency on uid, append-only file_index_state, backend-agnostic tool layer, confidence-scoring discipline. Pairs with graph-explorer (which queries the graph this skill builds), python-meta-server, and mcp-tool-authoring (for `cos_graph_*` tools).
last_reviewed: "2026-05-11"
---

# graph-os-authoring

Purpose: The graph is the third retrieval layer. Authoring it correctly — idempotent extraction, backend-neutral query layer, honest confidence scores — is what makes `cos_graph_*` tools faster + more accurate than grep. Getting any one of those wrong corrupts the graph silently, and the agent starts trusting hallucinations.

Read when: editing files matching:
- `src/core/graph_os/backends/*.py` — SQLite (single backend today; Kuzu retired 2026-05-18 after benchmark showed SQLite p99 < 30 ms on 5-hop @ 1M nodes).
- `src/core/graph_os/extractors/*.py` — Python AST / doc / config extractors.
- `src/core/graph_os/tools/*.py` — the `cos_graph_*` MCP tools (also see [mcp-tool-authoring](../mcp-tool-authoring/SKILL.md)).
- `src/core/graph_os/tools/reindex_dispatch.py` — incremental reindex orchestration.
- `src/core/graph_os/types.py` — node + edge type definitions (the contract).

Skip when: only querying the graph (use [graph-explorer](../../../core/skills/graph-explorer/SKILL.md) for that).

## The Five Hard Contracts

### 1. UID scheme (immutable across rebuilds)

Every node has a uid that survives reindex. Scheme:

```
code:file:<path>
code:function:<path>::<name>
code:class:<path>::<name>
code:module:<dotted-name>
doc:file:<path>
doc:heading:<path>#<slug>:<level>
folder:<path>
config:<path>::<key>
```

Path is repo-relative, POSIX, no leading slash. **Never** include line numbers in uids — line numbers shift; uids must be stable.

When adding a new node type, extend the registry in [src/core/graph_os/types.py](../../../core/graph_os/types.py) and document the uid grammar there. The grammar IS the contract — agents reference uids in saved memories.

### 2. Idempotent extraction (keyed on uid)

Every extractor MUST be re-runnable. The contract: extracting the same file twice produces the same nodes + edges. Implementation:

```python
def extract(file_path: Path) -> ExtractionResult:
    nodes = []
    edges = []
    for symbol in _walk_ast(file_path):
        nodes.append(GraphNode(
            uid=_make_uid(symbol),  # deterministic from file + symbol name
            kind="function",
            label=symbol.name,
            file_path=str(file_path),
            start_line=symbol.start,
            end_line=symbol.end,
            confidence=1.0,  # AST gives certainty
        ))
        for callee in symbol.callees:
            edges.append(GraphEdge(
                source_uid=nodes[-1].uid,
                target_uid=_resolve_callee_uid(callee, file_path),
                kind="calls",
                confidence=_calc_confidence(callee),  # see §3
            ))
    return ExtractionResult(nodes=nodes, edges=edges)
```

**Hard rules:**

- **Upsert on uid**, never blind-insert.
- **Removed symbols are tombstoned, not deleted** — if function `foo` disappears from a file, mark the node `deleted_at=now()` so historical references resolve. Compaction deletes tombstones older than 90 days.
- **Edge confidence is part of the key idempotency** — re-extracting the same edge updates the confidence, doesn't append a duplicate.

### 3. Honest confidence scores

Every edge has a confidence ∈ [0, 1]. Calibrated guide:

| Confidence | Meaning | Example |
|---|---|---|
| 1.0 | AST-certain | `import X`, `class Y(Z):` (direct inheritance), `def foo(): bar()` (direct call site) |
| 0.7-0.9 | Strong heuristic | Attribute access through `self.something.method()` (dynamic dispatch but typed) |
| 0.4-0.6 | Weak heuristic | String reference (`"my_module.func"`), dict-keyed dispatch |
| 0.1-0.3 | Possible | Same-named symbol in different module (could be aliasing or coincidence) |
| < 0.1 | Drop | Don't emit; noise |

Tools (`cos_graph_impact`, `cos_graph_references`) cluster low-confidence edges into a separate "context" tier so agents can ignore them. Inflating confidence = agents trusting noise = hallucinations.

### 4. Backend-agnostic tool layer

The tool layer (`src/core/graph_os/tools/*.py`) MUST NOT leak SQL or Cypher into MCP tool responses. The tool calls into a backend abstraction:

```python
# src/core/graph_os/tools/_query.py
from core.graph_os.backends import get_backend

async def query_references(uid: str) -> list[GraphEdge]:
    backend = get_backend()  # returns SqliteBackend today; abstraction kept so a future store can plug in.
    return await backend.find_references(uid)
```

Backends implement a common Protocol:

```python
class GraphBackend(Protocol):
    async def find_references(self, uid: str) -> list[GraphEdge]: ...
    async def find_context(self, uid: str, depth: int) -> list[GraphEdge]: ...
    async def upsert_nodes(self, nodes: list[GraphNode]) -> None: ...
    async def upsert_edges(self, edges: list[GraphEdge]) -> None: ...
    # ...
```

Adding a future backend later = new backend file only, zero changes to the tool layer.

### 5. Reindex is incremental + short-circuited

Full reindex of a large repo is minutes. Production cost must be milliseconds per save. Implementation:

```python
# src/core/graph_os/tools/reindex_dispatch.py
async def dispatch(file_path: str) -> ReindexResult:
    new_hash = _hash_file_contents(file_path)
    old_hash = await _file_index_state.get(file_path)

    if new_hash == old_hash:
        return ReindexResult(skipped=True, reason="content unchanged")

    extraction = _extract(file_path)
    await _backend.upsert_nodes(extraction.nodes)
    await _backend.upsert_edges(extraction.edges)
    await _file_index_state.set(file_path, new_hash)
    return ReindexResult(skipped=False, nodes=len(extraction.nodes), edges=len(extraction.edges))
```

`file_index_state` is the bookkeeping table mapping path → content-hash → last-indexed-at. Without it, every PostToolUse hook re-extracts unchanged files.

## Extractor — the Decision Tree

When adding a new extractor:

1. **What kind of artifact?** Code (Python / Go / TS / etc.) → AST extractor. Docs (Markdown / RST) → header extractor. Config (YAML / TOML / JSON) → key extractor.
2. **What nodes?** One per top-level symbol — functions, classes, modules. Sub-symbols (nested classes, methods) get their own node only if they're called from elsewhere.
3. **What edges?** `calls`, `imports`, `inherits`, `references` (doc → code), `contains` (folder → file → class → method), `tested_by` (test → subject).
4. **Where does ambiguity go?** Low-confidence edges. **Never** invent edges to fill in gaps.

### AST extractor anatomy (Python example)

```python
# src/core/graph_os/extractors/python_ast.py
import ast
from pathlib import Path

from core.graph_os.types import GraphNode, GraphEdge, ExtractionResult


class PythonAstExtractor:
    """Extracts functions, classes, imports, calls from .py files."""

    def extract(self, path: Path) -> ExtractionResult:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                nodes.append(self._function_node(path, node))
                edges.extend(self._call_edges(path, node))
            elif isinstance(node, ast.ClassDef):
                nodes.append(self._class_node(path, node))
                edges.extend(self._inherit_edges(path, node))
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                edges.extend(self._import_edges(path, node))

        return ExtractionResult(nodes=nodes, edges=edges)
    # ... helpers below
```

Test the extractor with a representative file + assert exact uid + count of nodes/edges:

```python
def test_extracts_function_with_two_calls(tmp_path):
    src = tmp_path / "sample.py"
    src.write_text("""
def outer():
    inner()
    other.method()

def inner():
    pass
""")
    result = PythonAstExtractor().extract(src)
    assert len(result.nodes) == 2  # outer + inner
    assert any(e.kind == "calls" and e.target_uid.endswith("::inner") for e in result.edges)
```

## Backend — the Decision Tree

`graph_os` ships a single backend:

- **SQLite** — embedded relational, FTS5 + JSON1, p99 < 30 ms on 5-hop traversal at 1M nodes with PRAGMA tuning + ANALYZE (benchmark 2026-05-18).

The Kuzu backend was retired the same day after the benchmark showed SQLite was well inside budget for every realistic consumer scale. The abstraction (`GraphBackend` Protocol) is kept so a future graph-native store can plug in if a real workload exceeds SQLite's headroom.

When adding a future backend:

1. Implement the `GraphBackend` Protocol.
2. Register it in `src/core/graph_os/backends/__init__.py`.
3. Add parity tests against SQLite — same queries → same results (within confidence-tier tolerance).
4. Document the backend's strengths / weaknesses in [docs/engineering/graph_os-queries.md](../../../docs/engineering/graph_os-queries.md).

**Hard rule:** the backend choice is a deployment concern, never visible to the agent or tool layer. `cos_graph_references` returns identical envelope shape regardless of which backend answered.

## Reindex Dispatch Patterns

| Trigger | Behavior |
|---|---|
| PostToolUse hook (single file written) | `dispatch(path)` — extract that file only |
| Doc indexer (markdown changed) | Same — incremental |
| Bulk migration / `git checkout` | `cos graph-reindex --force` — re-extract everything because content hashes are now misleading |

The PostToolUse path is fire-and-forget: it can't block the agent. Failures log + alert but the user's edit completes regardless.

## Tool-Side (when authoring `cos_graph_*`)

`cos_graph_*` tools are MCP tools — also see [mcp-tool-authoring](../mcp-tool-authoring/SKILL.md). Graph-specific contracts on top of the universal MCP contract:

- **Every response carries `data.meta.layer="graph"`** so agents know which retrieval layer answered.
- **`data.meta.backend`** tells which backend answered (`sqlite` today).
- **`data.meta.backend_fallback=true`** when the primary backend was unavailable and an alternate answered (no alternate today — flag reserved for a future graph-native plug-in).
- **Empty result is valid** — fresh repo, unindexed file. Don't return `fail`; return `ok({results: []})`.

## Anti-patterns (reject in review)

- **Non-idempotent extractor** — running twice produces duplicate edges.
- **Confidence inflation** — labeling a weak heuristic 0.9 to make `cos_graph_impact` return it in the strong tier. Pollutes agent trust.
- **SQL / Cypher leaking into tool responses** — breaks backend abstraction.
- **Hardcoded backend in tool layer** — must go through `get_backend()`.
- **Reindex without content-hash check** — kills perf.
- **Edge to a uid that doesn't exist** — dangling reference. Validate target uid exists or queue resolution.
- **Mutable uid** — including line number, timestamp, hash in the uid breaks cross-rebuild stability.
- **Deleting nodes instead of tombstoning** — breaks historical references.
- **Synchronous extraction in PostToolUse hook** — blocks the agent. Always fire-and-forget.

## Verification (after authoring)

```bash
# Extractor parity tests
uv run --extra graph_os pytest src/core/graph_os/tests/extractors/ -q

# Backend parity tests
uv run --extra graph_os pytest src/core/graph_os/tests/test_backends/ -q

# Tool layer tests
uv run --extra graph_os pytest src/core/graph_os/tests/test_tools.py -q

# Live graph doctor (after reindex)
cos graph-reindex
cos_graph_doctor   # check for dangling edges, orphan nodes, hash mismatch
```

Pre-merge: `make verify` + `cos doctor`.

## Tooling

Scaffold an extractor stub (idempotent uid, content-hash short-circuit, typed Node/Edge):
`python3 scripts/new_extractor.py --lang python`

## See also

- [assets/graph-os-checklist.md](assets/graph-os-checklist.md) — the extractor + backend gate.
- [graph-explorer](../../../core/skills/graph-explorer/SKILL.md) — the query-side counterpart of this skill.
- [docs/engineering/graph_os-queries.md](../../../docs/engineering/graph_os-queries.md) — query routing + freshness contract.
- [docs/engineering/graph-hallucination-cures.md](../../../docs/engineering/graph-hallucination-cures.md) — the 16 `cos_graph_*` tools and what each cures.
- [mcp-tool-authoring](../mcp-tool-authoring/SKILL.md) — when authoring a `cos_graph_*` tool.
- [python-meta-server](../python-meta-server/SKILL.md) — Python conventions for this codebase.
