<!-- domain:CORE | layer:playbooks | ssot:true | updated:2026-05-12 -->
# Polyglot Extractor Roadmap — Python-Grade Coverage for Every Language

> P: Bring every language extractor in `src/core/graph_os/extractors/` to the same
> world-class fidelity as `code_python.py` — accurate parsing, stable UIDs,
> toolchain-aware import resolution, edge-case tolerance, sub-100ms typical
> file. Single source of truth for the rollout plan.
> R: Authoring a new extractor, upgrading an existing one, or auditing the
> graph coverage of a polyglot repo.
> S: Tactical bug fixes on one extractor (open a TASK directly, no roadmap).
> N: [docs/engineering/graph-hallucination-cures.md](../engineering/graph-hallucination-cures.md),
>    [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md),
>    [docs/playbooks/db-reset.md](db-reset.md)

> Nav: [Playbooks Index](./00-index.md) | [Docs Index](../00-index.md)

## 1. Vision — what "world-class" means

A world-class extractor for language L exhibits ALL of:

| Pillar | Concrete bar |
|---|---|
| P1 Accuracy | Uses a real parser (native AST or tree-sitter), never naked regex for structure. Regex only for string-literal hints. |
| P2 UID stability | `uid` is deterministic from `(path, qualname, kind)`. Same content → same uid across runs. Rename = new uid, not silent mutation. |
| P3 Cross-file resolution | Import / call targets resolve via `ToolchainContext` (tsconfig paths, go.mod prefix, pyproject packages, Cargo workspaces). |
| P4 Contracts | Cross-cutting layer (`contracts.py`) extracts HTTP routes, RPC handlers, CLI entrypoints, decorators that bind code to external surfaces. |
| P5 Edge tolerance | Partial parses never crash. `parse_errors_count` + `last_error` recorded. Recovery: skip the broken span, keep emitting from the rest. |
| P6 Performance | < 100 ms median per typical file (≤ 1k LOC). Content-hash cache short-circuits unchanged files. |
| P7 Determinism | Two runs on the same file → byte-identical (uid, kind, edge_type, source_span) output. No hash-set iteration order leaks. |
| P8 Test fidelity | At least one golden test per node-kind + one per edge-type. Edge-case fixtures versioned in `src/core/graph_os/tests/fixtures/<lang>/`. |

`code_python.py` is the reference implementation. Anything that doesn't match it is "not world-class".

## 2. Dependency graph — what depends on what

```
                       ┌──────────────────────────┐
                       │   reindex_dispatch.py    │
                       │   (suffix → chain map)   │
                       └────┬─────────────────────┘
                            │ owns _EXT_MAP
                ┌───────────┼──────────────┬────────────┐
                ▼           ▼              ▼            ▼
        ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐
        │ Extractors │  │ Overlay  │  │ Toolchain│  │ Backend      │
        │  per lang  │  │ layer    │  │ context  │  │ (sqlite)     │
        └─────┬──────┘  └────┬─────┘  └────┬─────┘  └──────────────┘
              │              │             │
              ├── code_python.py ◄─── tree_sitter_overlay (py grammar)
              ├── code_ts.py     ◄─── tree_sitter_overlay (ts + tsx)
              ├── code_go.py     ◄─── tree_sitter_overlay (ts-go: v2 shipped, dep not installed)  ◄── go.mod
              ├── code_shell.py  ◄─── tree_sitter_overlay (bash grammar; regex fallback)
              ├── code_yaml.py   ◄─── PyYAML
              ├── md_links.py    ◄─── custom parser
              ├── contracts.py   ◄─── post-pass on code_python/ts/go
              └── task_deps.py   ◄─── post-pass on md_links
                            ▲
                            │ produces GraphNode / GraphEdge
                            │
                ┌───────────┴────────────┐
                │ types.py (NodeKind,    │
                │  GraphNode, GraphEdge) │
                └────────────────────────┘
```

**Hard dependencies:**
- All extractors → `types.py` (no extractor may bypass canonical node kinds).
- All non-regex extractors → `tree_sitter_overlay.py` for grammar loaders.
- All cross-file edges → `toolchain.py::ToolchainContext`.
- `contracts.py` runs AFTER its host language extractor in the chain.

**Cycle break:** extractors are PURE (no DB writes); the orchestrator persists. So a fixture test runs an extractor in-memory and asserts on the emitted records without spinning SQLite.

## 3. Mind map — taxonomy of work

```
World-class polyglot graph
│
├── Languages (target = Python parity)
│   ├── Python ......................... DONE ✅ — reference impl (47K LOC, AST + ts overlay)
│   ├── TypeScript/TSX ................. DONE ✅ — tree-sitter AST walker is DEFAULT (_walk_ts_symbols): class/interface/method/function/arrow nodes, calls scoped to enclosing fn, inherits_from/implements/extends, is_decorated_by, param/return type edges, JSX constructs. Regex = fallback only.
│   ├── JavaScript/JSX ................. DONE ✅ — same code_ts tree-sitter walker (.js/.jsx/.mjs/.cjs)
│   ├── Go ............................. code_go@v2 ts rewrite SHIPPED; gap = install tree_sitter_go dep (regex fallback runs until then)
│   ├── Shell .......................... DONE ✅ — tree-sitter-bash (regex is fallback only)
│   ├── YAML ........................... GOOD — PyYAML based
│   ├── Markdown ....................... GOOD — custom parser + task_deps
│   ├── JSON ........................... DONE ✅ — code_json (package.json/tsconfig/mcp.json deps)
│   ├── TOML ........................... DONE ✅ — code_toml (pyproject/Cargo deps)
│   ├── Rust ........................... ABSENT — defer, no Rust in this repo
│   ├── Java/Kotlin .................... ABSENT — defer
│   └── Ruby/PHP ....................... ABSENT — defer
│
├── Cross-cutting
│   ├── contracts.py ................... GOOD — runs on py/ts/go
│   ├── task_deps.py ................... GOOD — TASK-NNN graph
│   ├── md_links.py .................... GOOD — heading + link extraction
│   └── doc_indexer (RAG) .............. SEPARATE — RAG layer, not graph
│
├── Overlays
│   ├── tree_sitter_overlay ............ GOOD — py/ts/tsx/bash/yaml grammars installed
│   ├── lsp_overlay .................... DORMANT — no LSP servers spawned in runtime
│   └── toolchain context .............. GOOD — tsconfig + go.mod + pyproject + Cargo
│
├── Infrastructure
│   ├── reindex_dispatch ............... GOOD — chain map, cache, idempotent
│   ├── file_index_state cache ......... GOOD — content_hash short-circuit
│   ├── backend (sqlite) ............... GOOD — single store; Kuzu retired 2026-05-18 after benchmark showed SQLite p99 < 30 ms on 5-hop @ 1M nodes
│   └── auto-reindex-docs hook ......... GOOD — fires PostToolUse:Write|Edit
│
└── Quality bars
    ├── P1 Accuracy ............ parser, not regex
    ├── P2 UID stability ....... deterministic id
    ├── P3 Resolution .......... toolchain-aware
    ├── P4 Contracts ........... HTTP/RPC/CLI
    ├── P5 Edge tolerance ...... never crash
    ├── P6 Performance ......... <100ms / file
    ├── P7 Determinism ......... byte-identical reruns
    └── P8 Test fidelity ....... golden per kind + edge
```

## 4. Per-language gap analysis & target state

### 4.1 Python — REFERENCE

Already world-class. Native `ast` module + tree-sitter overlay for fallback.
Cross-file resolution via pyproject + setup.cfg packages. Contracts: FastAPI
routes, MCP tools, decorators, click commands. **Do not touch unless reference
changes.**

### 4.2 TypeScript / TSX

| Pillar | Now | Target |
|---|---|---|
| P1 Parser | tree-sitter (`typescript`, `tsx` grammars) ✅ | unchanged |
| P2 UID | stable ✅ | unchanged |
| P3 Resolution | tsconfig `paths` ✅ | + monorepo workspace `package.json` resolution |
| P4 Contracts | Express/Next routes via `contracts.py` ✅ | + tRPC, NestJS decorators, React Server Component boundaries |
| P5 Edges | tolerant ✅ | + JSX type-only imports (`import type {…}`) skip cleanly |
| P6 Perf | OK | unchanged |
| P7 Determinism | OK | unchanged |
| P8 Tests | partial | golden fixture per: function, class, interface, type alias, JSX component, async generator |

**Workstream TS-1:** monorepo workspace resolver (4h)
**Workstream TS-2:** tRPC + NestJS contract patterns (4h)
**Optional TS-3:** LSP overlay for type inference on `any` / inferred returns (8h, only if LSP server pool is built)

### 4.3 Go

| Pillar | Now | Target |
|---|---|---|
| P1 Parser | **regex only** | **tree-sitter-go** (install grammar, wire into overlay) |
| P2 UID | partial (regex misses generics, methods on aliases) | from ts-go AST: `code:function:<path>::<name>`, `code:method:<path>::<receiver>.<name>` |
| P3 Resolution | go.mod prefix ✅ | + replace directives, + workspace `go.work` |
| P4 Contracts | gin/echo route regex ✅ | + chi, fiber, gRPC service registration, cobra CLI |
| P5 Edges | brittle | partial-parse recovery via tree-sitter ERROR nodes |
| P6 Perf | fast (regex) | tree-sitter slightly slower but still <100ms typical |
| P7 Determinism | OK | OK |
| P8 Tests | minimal | golden per: func, method, interface, struct, generic, embed, defer |

**Workstream GO-1:** add `tree-sitter-go` to deps + extend `_LOADERS` (1h)
**Workstream GO-2:** rewrite `code_go.py` against ts-go AST queries (4h)
**Workstream GO-3:** golden fixtures for the 7 node kinds + 5 edge types (2h)
**Workstream GO-4:** workspace + replace-directive resolution in toolchain.py (2h)

### 4.4 Shell

| Pillar | Now | Target |
|---|---|---|
| P1 Parser | **regex** | **tree-sitter-bash** (grammar already installed) |
| P2 UID | partial — function names by regex | from ts-bash AST: `code:function:<path>::<name>` |
| P3 Resolution | n/a | + `source` / `.` includes → file edges |
| P4 Contracts | n/a | + hook event metadata when path matches `src/core/hooks/*.sh` |
| P5 Edges | brittle — 209 errors in 110 files in this repo (96%) | parse errors → 0 on well-formed scripts |
| P6 Perf | fast | maintained |
| P7 Determinism | OK | OK |
| P8 Tests | minimal | golden per: function, alias, source-include, here-doc literal |

**Workstream SH-1:** rewrite `code_shell.py` on ts-bash (3h) ← MVP
**Workstream SH-2:** hook-event metadata extractor for `src/core/hooks/*.sh` (1h)
**Workstream SH-3:** golden fixtures (1h)

### 4.5 YAML

| Pillar | Now | Target |
|---|---|---|
| P1 Parser | PyYAML ✅ | unchanged |
| P2 UID | document/key-path based ✅ | unchanged |
| P3 Resolution | n/a | n/a |
| P4 Contracts | hook registry parsing ✅ | unchanged |
| P5 Edges | tolerant | OK |
| P6 Perf | OK | OK |
| P7 Determinism | OK | OK |
| P8 Tests | minimal | golden per: mapping, sequence, anchor, alias, multi-document |

### 4.6 JSON — NEW EXTRACTOR

Currently invisible to graph. Targets: `settings.json`, `mcp.json`, `tsconfig.json`,
`package.json`, `composer.json`, `.eslintrc.json`.

| Pillar | Spec |
|---|---|
| P1 Parser | stdlib `json` (fast, lossless) with fallback to `json5` if comments seen |
| P2 UID | `config:json:<path>#<json-pointer>` per leaf of interest |
| P3 Resolution | `package.json` deps → node-module nodes; `tsconfig.json` references → other tsconfigs |
| P4 Contracts | npm scripts → CLI entrypoints; MCP servers in `mcp.json` → mcp_server nodes |
| P5 Edges | malformed → 0 nodes, error logged |
| P6 Perf | trivially fast |
| P7 Determinism | dict order = insertion order from json module |
| P8 Tests | golden per: package.json src/scripts/deps, tsconfig paths, mcp.json server, settings.json hooks |

**Workstream JSON-1:** new `code_json.py` + `_EXT_MAP[".json"]` (3h)
**Workstream JSON-2:** path-aware emitters for package.json vs tsconfig vs mcp.json (3h)
**Workstream JSON-3:** golden fixtures (2h)

### 4.7 TOML — NEW EXTRACTOR

Targets: `pyproject.toml`, `Cargo.toml`, `*.toml` configs.

| Pillar | Spec |
|---|---|
| P1 Parser | stdlib `tomllib` (3.11+) with `tomli` fallback |
| P2 UID | `config:toml:<path>#<dotted-key>` |
| P3 Resolution | `pyproject.toml [project.dependencies]` → package nodes; `Cargo.toml [dependencies]` → crate nodes; workspace `[workspace.members]` → directory edges |
| P4 Contracts | Cargo bin/lib targets → entrypoints; poetry scripts → CLI entries |
| P5 Edges | malformed → 0 nodes, log |
| P6 Perf | trivially fast |
| P7 Determinism | dict order = stable |
| P8 Tests | golden per: pyproject deps, Cargo workspace, scripts table |

**Workstream TOML-1:** new `code_toml.py` (3h)
**Workstream TOML-2:** workspace member resolution (2h)
**Workstream TOML-3:** fixtures (1h)

### 4.8 Parity-closure to Python-gold (TASK-067)

The tree-sitter migrations (A1/GO-2) landed the parsers; this workstream
closes the remaining *knowledge + accuracy* gaps so Go/TS/Shell and the
framework contracts reach Python-gold parity. Each item is a real edge /
node / correctness fix — not feature-padding (Rule 22).

| Lang / layer | Gap (pre-067) | Target edge / node (post-067) |
|---|---|---|
| **Go** `code_go.py` | calls are regex-only, sourced at the module, conf 0.5; NO same-file function/method call resolution | AST `calls` edge sourced at the enclosing func/method uid; a same-file `func B()` / `(r *T) M()` invocation resolves to B's real `code:function`/`code:method` uid at conf 0.9 (mirrors Python `same_scope`). Cross-package `pkg.Fn()` stays the conf-0.5 external edge. |
| **TS** `code_ts.py` | `has_param_type`/`returns_type` always target `code:external:unresolved:<T>`; `await fn()` emits `calls`; `enum`/`namespace` invisible | type edges resolve through `local_names`/`imported_names` (unresolved only as last resort, like Python); `await`-ed call emits an `awaits` edge; `enum_declaration` → `code:class` node (metadata.ts_kind=enum), `internal_module`/`module` (namespace) → `code:module`-style node with contained members |
| **Shell** `code_shell.py` | regex fallback emits only script-file calls + `cos_log_hook`; intra-file function calls missing (tree-sitter path has them) | regex fallback resolves a command matching a same-file function name → `calls` edge (parity with `_walk_ts`) |
| **Go contracts** `contracts.py` `_scan_fiber`/`_scan_gin`/`_scan_echo` | `groups[-1]` ("last group seen") prefixes EVERY route regardless of the receiver variable → wrong paths when ≥2 groups or a bare-app route coexists; `handler=None` always | track `var → prefix` from `g := app.Group("/x")`; a route on `g.Get(...)` gets `g`'s prefix, a route on bare `app.Get(...)` gets none; capture the handler arg → `cos:route → handler` `calls` edge |
| **Next.js contracts** `_scan_nextjs` | only app-router named exports (`export function GET`) detected; pages-router (`export default function handler`) + `page.tsx` page-routes invisible | detect pages-router default-export handler under `pages/api/**` (method `any`); detect `page.tsx`/`page.ts` as a `get` route at the derived URL |
| **React** `code_ts.py` | function components indistinguishable from plain functions | PascalCase function/arrow whose body contains JSX → `metadata.component=true` on the `code:function` node (makes "list components" queryable; reuses the existing node, no new edge type) |

Verification: `uv run --extra graph_os pytest src/core/graph_os/tests/ -q`
(new adversarial tests per group) + `cos graph-reindex` smoke on this repo.

### 4.9 PHP + Laravel + WordPress + WHMCS (TASK-069)

Net-new language. Mirrors `code_go` (tree-sitter primary + regex fallback)
because PHP is class-heavy with real type hints — AST is mandatory for
parity. Grammar: `tree-sitter-php` via `language_php()` (handles
`<?php … ?>` islands in mixed HTML/PHP files).

**PHP language (`code_php.py`) — Python-gold parity:**

| Emitted | Detail |
|---|---|
| nodes | `code:file`, `code:module`(namespace), `code:class`, `code:interface`, trait → `code:class` + `metadata.php_kind=trait`, `code:method`, `code:function`, `code:variable`(typed property + class const), `code:import`(`use`, incl alias + grouped `use A\{B,C}`) |
| edges | `contains`, `imports`, `inherits_from`(extends), `implements`, `uses_trait`(trait composition; signal on an `inherits_from` edge), `has_param_type`/`returns_type`(incl `?T` nullable, `A\|B` union, `A&B` intersection), `field_of_type`(typed props), `is_decorated_by`(PHP-8 `#[Attr]`), `calls`/`constructs` with **same-file resolution** — bare `B()`, `$this->m()`, `self::m()`/`static::m()`/`ClassName::m()`, `new X()` → real uids @0.9 (the Go `same_scope` analog) |

**Framework contracts (`contracts.py` PHP scanners), via the existing
ContractMatch → handles_route / handles_event / handles_command pipeline:**

| Framework | Patterns → graph |
|---|---|
| **Laravel** | `Route::{get,post,put,patch,delete,any}('/p', handler)` → http; `Route::resource/apiResource('users', Ctrl::class)` → 7/5 synthesised routes (DRF-style); **group-closure prefix join** (TASK-071) — `Route::prefix('api')->group(fn)` + `Route::group(['prefix'=>'api'], fn)`, brace-matched + nesting-aware, routes outside a group keep their literal path; handler `[Ctrl::class,'m']`/`'Ctrl@m'`/invokable → route→handler `calls`, **resolved cross-file** to the real `code:method` via the `link_php_handlers` post-pass (TASK-071); `extends Command`+`$signature`→cli |
| **WordPress** | `add_action`/`add_filter('hook', cb)` → `handles_event` (cb→handler); `do_action`/`apply_filters` → event fire-site; `add_shortcode`; `register_post_type` → CPT; `register_rest_route('ns','/r',[methods])` → http; `wp_ajax_{action}`/`wp_ajax_nopriv_*` → ajax route |
| **WHMCS** | `add_hook('Point', prio, cb)` → `handles_event`; `{module}_{Action}` functions where `{module}` == file/dir stem (`_CreateAccount`, `_ConfigOptions`, `_ClientArea`, …) → module-function tag + module-type (provisioning/registrar/addon/gateway) from action set + `modules/{servers,registrars,addons,gateways}/` path |

Wiring: `pyproject [graph_os] += tree-sitter-php`; `code_php` self-loads
`tree-sitter-php` via `language_php()` (no `tree_sitter_overlay` loader —
no other consumer); `_EXT_MAP[".php"] = ("php", ["code_php","contracts"])` + `ingest/base.py::DEFAULT_INCLUDE += *.php` (bulk walk — TASK-071);
`types.py` provenance `code_php@v1`/`code_php_ts@v1`. Verification:
`uv run --extra graph_os pytest src/core/graph_os/tests/ -q` + per-framework
adversarial suites + `cos graph-reindex --force` errors=0. A `src/templates/php/`
stack for `cos init` is OUT of scope here (separate task).

## 5. Implementation checklist (grouped, ordered)

### Epic A — Fix the broken (highest immediate value)

- [ ] **A1 Shell → tree-sitter-bash** [3h] _(MVP this session)_
  - [ ] A1.1 Rewrite `code_shell.py` against ts-bash AST queries
  - [ ] A1.2 Emit function + alias + source-include nodes
  - [ ] A1.3 Wire `tree_sitter_overlay._LOADERS["bash"]` if not already
  - [ ] A1.4 Hook-event metadata when path matches `src/core/hooks/*.sh`
  - [ ] A1.5 Golden fixtures: 6 scripts spanning all node kinds
  - [ ] A1.6 Verify on real repo: 209 errors → 0 errors expected

### Epic B — Add the missing (net new coverage)

- [ ] **B1 JSON extractor** [6h]
  - [ ] B1.1 New `code_json.py` skeleton
  - [ ] B1.2 Path-aware: package.json / tsconfig.json / mcp.json / settings.json / generic
  - [ ] B1.3 Wire `_EXT_MAP[".json"] = ("json", ["code_json"])`
  - [ ] B1.4 Golden fixtures (5 file types)
  - [ ] B1.5 Verify: src/scripts/deps/paths/servers extracted, reindex run clean

- [ ] **B2 TOML extractor** [6h]
  - [ ] B2.1 New `code_toml.py`
  - [ ] B2.2 pyproject + Cargo + generic detector
  - [ ] B2.3 Wire `_EXT_MAP[".toml"] = ("toml", ["code_toml"])`
  - [ ] B2.4 Workspace member edges
  - [ ] B2.5 Fixtures + verify

### Epic C — Upgrade the working (close to world-class)

- [x] **C1 Go → tree-sitter-go** [shipped]
  - [x] C1.1 Rewrite `code_go.py` on ts-go AST — full coverage including
        function/method/struct/interface/alias/generics/const/var/init/
        test funcs (TestXxx/BenchmarkXxx/ExampleXxx/FuzzXxx/TestMain) +
        build tags + dot/blank/aliased imports.
  - [x] C1.3 Contracts: gin / echo / chi / fiber / gorilla / net/http
        (Go 1.22+) / gRPC RegisterXxxServer / cobra / urfave/cli.
  - [x] C1.4 Golden fixtures: TestGoExtractor (12 cases) +
        TestContractsGoFrameworks (7 cases) in tests/test_i7_extractors.py.
  - [ ] C1.2 Workspace + replace-directive in `toolchain.py` — open
        until a real Go workspace consumer arrives.

### Epic E — Cross-cutting infrastructure

- [ ] **E1 Performance budget** [4h]
  - [ ] E1.1 Per-extractor timing in `file_index_state` (new column `duration_ms`)
  - [ ] E1.2 Hub panel pie chart by extractor cost

## 6. Edge-case catalog (the "" the user asked about)

### Shell
- Functions defined with `function foo()` vs `foo() { … }` — both must emit same UID.
- `source` vs `.` — both create same edge kind.
- Heredoc bodies (`<<EOF … EOF`) — content must NOT be parsed as code.
- Comments containing dangerous patterns (e.g. `# python3 - <<HEREDOC`) — must not be flagged as code (see `block-bad-patterns.sh` precedent).
- Bash 5 vs POSIX `sh` — accept both; degrade gracefully on bash-only syntax in `.sh` files.

### Go
- Generics (`func F[T any](…) T`) — emit type parameters as evidence, not separate nodes.
- Methods on type aliases — `code:method:<path>::<TypeAlias>.<name>`.
- Embedded interfaces — emit `IMPLEMENTS` edge.
- `init()` functions — special-cased as `kind=function, init=true` evidence flag.
- Build tags (`//go:build linux`) — record as evidence on file node.

### JSON
- Trailing commas in JSON5 → fallback parser.
- Comments in tsconfig.json (de-facto JSON5) → strip-then-parse.
- `package.json` `workspaces` field — array OR object form, both must work.
- `tsconfig.json` `extends` chain — follow up to 3 levels, cycle-detect.

### TOML
- Inline tables vs nested tables — collapsed to same UID.
- Array-of-tables (`[[deps]]`) — each table = own node.
- Workspace `[workspace.members]` — glob patterns (`crates/*`) expand to dir edges.

### TypeScript
- `import type {…}` — emit edge with `evidence.type_only=true`, don't count as runtime dep.
- JSX namespaces / fragments — `<></>` ≠ identifier.
- Decorators (legacy + new TC39) — emit two-way edge.

## 7. Performance budget per language

| Lang | Median target | P95 target | Cache hit-rate target |
|---|---|---|---|
| Python | < 80 ms | < 400 ms | > 80% on incremental edits |
| TS/TSX | < 100 ms | < 500 ms | > 80% |
| Go (post-migration) | < 100 ms | < 500 ms | > 80% |
| Shell (post-migration) | < 30 ms | < 150 ms | > 90% (small files) |
| YAML | < 30 ms | < 150 ms | > 90% |
| JSON | < 10 ms | < 50 ms | > 95% |
| TOML | < 10 ms | < 50 ms | > 95% |
| Markdown | < 60 ms | < 300 ms | > 80% |

A regression below these caps in CI blocks the PR.

## 8. Verification matrix

| Workstream | Command | Expected |
|---|---|---|
| Any extractor change | `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` | green |
| Shell migration | `cos graph-reindex --force --path src/core/hooks` then `cos db-stats` | code_shell parse_errors_count = 0 in `file_index_state` |
| Performance | `cos graph-reindex --force --path <large-dir>` with timer | median below budget |
| Polyglot smoke | `cos graph-reindex --force` on this repo | nodes > 31k, edges > 64k, errors = 0 |

## 9. Status snapshot (post 9bee865 + cleanup)

| Workstream | Status | Notes |
|---|---|---|
| A1 Shell → ts-bash | shipped | 87% error reduction on real repo |
| B1 JSON extractor | shipped | 19 files, 138 nodes, 0 errors |
| B2 TOML extractor | shipped | pyproject + Cargo handled |
| C1 Go → ts-go | shipped | full AST + 9 frameworks of contracts; toolchain workspace open |
| D1 Generic polyglot baseline | shipped | `code_generic` (TASK-296) — one table-driven extractor emits file+spine+function/class+contains for any grammar in `_LANG_SPEC`. Calls/imports stay per-language. |
| D2 Broadened grammars | shipped | TASK-304 — grammars now ship for rust, ruby, java, c, c++, c#, scala, kotlin, lua (+ C/C++ declarator-name fix). SQL deferred (DDL doesn't fit func/class). |
| E1 Performance telemetry | open | duration_ms column landing alongside this cleanup |

> **Generic vs hand-written precedence.** `code_generic` only owns the
> extensions in `reindex_dispatch._EXT_MAP` that have no hand-written
> extractor (`.rs .rb .java .c/.h .cc/.cpp/.cxx/.hpp/.hh .cs`). A
> language graduates to its own extractor (calls, imports, type edges)
> the same way Go did — `code_generic` is the floor that guarantees a
> new language is never invisible, not the ceiling.

## See also

- [docs/engineering/graph-hallucination-cures.md](../engineering/graph-hallucination-cures.md)
- [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md)
- [docs/playbooks/db-reset.md](db-reset.md)
- [src/core/skills/graph-explorer/SKILL.md](../../src/core/skills/graph-explorer/SKILL.md)
