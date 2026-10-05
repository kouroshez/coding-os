<!-- domain:CORE | layer:engineering | ssot:false | updated:2026-10-04 -->
# Graph-OS Polyglot Audit — Go · TS · JS · Python · Shell (2026-10-04)

> P: Defect register + fix checklist from a deep audit of graph_os coverage for
>    Go, TypeScript, JavaScript, Python and Shell, and for the React Native, Go
>    Fiber, Astro and FastAPI frameworks.
> R: Fixing or reviewing an item below, or judging how complete the graph is for
>    one of these stacks.
> S: Authoring a new extractor from scratch — see
>    [polyglot-extractor-roadmap.md](../playbooks/polyglot-extractor-roadmap.md).
> N: [graph_os-queries.md](graph_os-queries.md),
>    [graph-hallucination-cures.md](graph-hallucination-cures.md),
>    [polyglot-extractor-roadmap.md](../playbooks/polyglot-extractor-roadmap.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Questions this audit answers

1. Is the graph tuned for these five languages and four frameworks?
2. Can it show that a shared module is duplicated somewhere?
3. Does every file, class, function and dependency reach the graph, and can the
   MCP tools return them?
4. When an agent edits a file, does the graph surface the files that depend on it?
5. Can it say how many files import a given library?
6. Can it show that something was missed — a name used but never imported or
   defined?
7. Is the graph complete: every file in the repo and the detail inside it?

## Method

Read-only auditors (one per language or framework, plus an external-practice
researcher) probed the extractors with adversarial fixtures and the live graph.
Real-world numbers come from a private 2.1k-file monorepo (Go API, Python
service, React Native app, Astro site, shared TypeScript packages) indexed from a
scratch copy — called *the benchmark* below; it is deliberately not named.
Every finding below was reproduced before it was listed. Fixes were made one per
commit on `main` by a single writer. External practice (TypeScript and Node
resolution, Go modules, Metro and Expo Router, Fiber v3, Astro, FastAPI, PEP 328,
ShellCheck, clone-detection literature, SCIP / stack-graphs / Kythe) came from the
researcher's 89-item checklist; the items that changed a fix are cited inline.

## Baseline answers (before the fixes below)

Measured on the benchmark with a go/types type-check, tree-sitter scans and grep
as ground truth.

| Q | Go | TS / JS | Python | Shell | Astro |
|---|---|---|---|---|---|
| 1 tuned | no — 0 of 10,973 cross-file call sites reach the callee | partial — 0 cross-file calls; 39% of file imports | partial — the only language with cross-file links | partial — `source` only | no — not walked |
| 2 duplicates | no | no | no | no | no |
| 3 complete | symbols yes, 46 `go.mod` requires no | symbols yes, `.mts`/`.cts` no | yes | 15 of 83 scripts | 0 of 66 files |
| 4 edit impact | 0 dependents surfaced | 0–2 of 21–303 for alias / workspace imports | about half | `source`d files only | none |
| 5 library fan-in | exact import path only | edges, not files; workspace packages look external | exact module only | no | no |
| 6 missing import | no — unknown calls emit nothing | no — 99.9% of unresolved stubs are builtins or members | no | no | no |
| 7 whole repo | no — 36% of all nodes were lockfile / OpenAPI keys; `.astro` and `.mdx` absent | | | | |

## Findings and checklist

Severity: **CRITICAL** — the graph answers confidently and wrongly, or misses most
callers for a language · **HIGH** — a whole category is missing · **MEDIUM** —
partial · **LOW** — noise.

- [x] **F-01 [CRITICAL] An edit to a file erased every edge other files held into
  it (all languages).** The per-file reindex deleted the file's nodes *before*
  re-extracting, and edges are `ON DELETE CASCADE`, so the re-inserted symbols came
  back with new row ids and no inbound `calls` / `imports` edges. Repro: `a.py`
  calls `b.f()`; edit `b.py`; `references(b.f)` drops from 2 inbound cross-file
  edges to 0 until a full reindex. Fix: clear only the file's outbound edges up
  front (`delete_edges_from_file`), upsert, then hard-delete the nodes the new pass
  no longer emits (`delete_nodes_for_file(keep_uids=…)`). Tests:
  `test_reindexing_callee_keeps_inbound_cross_file_edges`,
  `test_reindex_drops_edges_the_file_no_longer_emits`.
- [x] **F-02 [CRITICAL] The toolchain context was never switched on.**
  `toolchain.set_active()` has no production caller, although its docstring says
  dispatch calls it, so tsconfig `paths` / `baseUrl`, `go.mod` and pyproject
  package roots never reached an extractor. On the benchmark monorepo, 296 `@/…`
  alias imports and 1,007 imports of its own workspace packages pointed at invented
  `code:module:npm:…` packages, so editing a shared package surfaced no dependent
  app. Fix: `_reindex_graph` activates the project's toolchain around every
  extraction (restored afterwards); the TS side is TS-01, Go is GO-02.
- [x] **F-03 [MEDIUM] Parallel indexing failed files on a write race.**
  `graph-reindex -j 4` on the benchmark monorepo logged `UNIQUE constraint failed: graph_nodes.uid`
  and 94–151 per-file failures that a retry pass had to recover. `upsert_node` did
  a bare INSERT after an existence check, so a sibling worker inserting the same
  shared uid (a stub, a folder) in between failed the file; `upsert_edge` opened a
  deferred `BEGIN`, whose read-to-write upgrade fails at once under contention —
  `busy_timeout` never applies to it. Fix: `INSERT … ON CONFLICT(uid) DO NOTHING`
  then re-read, and `BEGIN IMMEDIATE` for edges. Test:
  `test_upsert_node_survives_a_rival_insert_of_the_same_uid`. Measured on the benchmark at `-j 4`:
  first-pass failures 94–151 → 0, wall time 176 s → 84 s at a similar load.
- [x] **F-04 [HIGH] Renamed or deleted TypeScript symbols lived on as zombies.**
  The reindex prune was scoped to each extractor module's `EXTRACTOR_ID`, but
  `code_ts` stamps its AST declarations `code_ts_ts@v1` (and `code_python` its
  tree-sitter imports `code_python_ts@v1`), so a renamed `foo` kept its node and a
  deleted call kept its `calls` edge — 3,087 nodes and 24,141 edges of the benchmark sat
  outside every prune. Fix: `types.extractor_family()` derives the full ID set
  (sub-extractors and older versions) from the provenance registry. Test:
  `test_ts_rename_and_removed_call_leave_no_zombies`. Reported by the
  completeness auditor.
- [x] **F-05 [MEDIUM] A `$schema` URL silently voided a whole tsconfig.** Both
  JSONC strippers (`toolchain`, `code_json`) deleted `//[^\n]*` without knowing
  about strings, so `"$schema": "https://json.schemastore.org/tsconfig"` was cut at
  `https:` and the file stopped parsing — every alias in it was dropped, and
  `code_json` lost the file's keys whenever it also had a comment. Fix: one
  string-aware `toolchain.strip_json_comments`, used by both. Test:
  `test_schema_url_survives_comment_stripping`.

### Cross-cutting

- [x] **CC-01 [CRITICAL] Cross-file link passes only know Python.** `link_external_stubs`
  and `link_import_bindings` match `<module>.py` / `__init__.py` only, so Go, TS and
  shell stubs never reach a real symbol: 0 cross-file call edges for Go and TS on
  the benchmark. Fixed per language below (TS-01, GO-01/02, SH-01): `link_cross_file`
  now runs Python, TS/JS, Go, shell, PHP and FastAPI-route passes.
- [x] **CC-02 [HIGH] Lockfiles and generated specs were 36% of all nodes.**
  `pnpm-lock.yaml` / `package-lock.json` pass the `*.yaml` / `*.json` include, the
  rule that says lock files are graph-excluded was untrue, and
  `COS_GRAPH_EXCLUDE_PATHS` is read by no code. `query("react")` returned 10
  lockfile keys before the npm module. Fix: `LOCKFILE_NAMES` are skipped by name,
  and `COS_GRAPH_EXCLUDE_PATHS` now works for directories and single files (the
  place to drop a generated OpenAPI spec). Test: `test_walk_exclusions.py`.
- [x] **CC-03 [HIGH] The walk drops `.astro`, `.mdx`, `.mts`, `.cts`, `.bash`, `.zsh`
  and extensionless shebang scripts.** Three hand-kept extension lists (walk
  include, `_EXT_MAP`, the auto-reindex hook) drift apart. Fix: all are walked
  and routed (shebang scripts by their `#!` line); the hook list is CC-14.
- [x] **CC-04 [HIGH] `references(code:file:X)` silently answers 0 for TS, Go and Python.**
  Importers point at the module (or Go import-path) node; the folder `contains`
  edge keeps the zero-from-kind-filter warning from firing. Fix: a file's
  references merge its module's and Go package's inbound edges
  (`meta.merged_targets`), `contains` is no longer a file default, and file impact
  expands to the module as well as its symbols. `imports_type`, `re_exports`,
  `field_of_type` and `extends` now count as behavioural for impact and rename.
- [x] **CC-05 [HIGH] No duplicate / clone signal (Q2).** `ast_hash` exists for Python
  only and hashes the uid, so two files can never match; Go, TS and shell set none.
  Fix: `extractors/_fingerprint.py` gives every function, method, class and type
  in all five languages two body hashes after Roy & Cordy's clone types —
  `content_hash` for an exact copy (layout and comments ignored) and `ast_hash`
  for a copy with renamed names and constants; bodies under 50 tokens (jscpd's
  default) get none. `cos_graph_duplicates(scope, clone_type)` lists clone
  groups (a copied class is one group, not one per method), files sharing most
  of their symbols, and byte-identical files; `cos_graph_similar` ranks copies of
  the body first. Generated files (`DO NOT EDIT`, `@generated`, `*.gen.ts`,
  protobuf output) are marked at index time and left out. The same pass records
  where every TS, Go and shell symbol ends — 0% → 100% on the benchmark — so
  `context(include_content=True)` returns the body, not its first line.
  Benchmark: 5,433 fingerprinted symbols, 73 hand-written clone groups (a
  29-line function copied between two Go services, one helper in three
  components) once 40 generated files are skipped; 42 ms. Tests:
  `test_duplicates.py`.
- [x] **CC-06 [HIGH] No unbound-name signal (Q6).** `code:external:unresolved:*` is 98–99.9%
  builtins, members and locals; Go emits nothing for an unknown call. Fix:
  `extractors/_undefined_names.py` records, on each module node, the names a file
  uses but never binds — Python through `symtable` plus names only annotations
  use (under `from __future__ import annotations` symtable never sees them), TS /
  JS calls, `new` and JSX components against every declaration and the platform
  globals; Go reads it from the link: a bare call no file of its package defines.
  `cos_graph_undefined(scope)` lists them and `cos_graph_detect_changes` returns
  them for the edited files as `undefined_names`. Measured with one import line
  deleted at a time: Python 262 / 262 caught on this repo, TS 292 / 295 on the
  benchmark; false positives 0 on both (the one Python hit here is a real
  undefined name its author silenced with `noqa: F821`), 32 ms on the benchmark.
  With TS-02 and TS-08 every exported name has a node, so a TS import the linker
  cannot bind, of a name its in-repo target defines nowhere, is reported too
  (`reason: "not_exported"` — a renamed or removed export); 0 on the benchmark.
- [x] **CC-07 [MEDIUM] JS / PHP file nodes end up `lang='txt'`.** `contracts._lang_for`
  knows four suffixes and overwrites the code extractor's value. Fix: it returns the
  script family's own language (`js`, `jsx`, `ts`, …) or nothing, and the JS/TS
  contract scanners now also run on `.js`, `.jsx`, `.mjs`, `.cjs`, `.mts`, `.cts`.
- [x] **CC-08 [MEDIUM] Route uids are global.** `cos:route:GET:/health` from a Go service
  and a Python service merge into one node; the test-source filter misses
  `_test.go`, `.test.ts`, `.spec.ts`. Fix: `graph_os/test_paths.is_test_path` is now
  the one rule (Go, TS/JS, Jest `__tests__`, `testdata`, Python) behind dead-code,
  test-gap, contracts, duplicates, ranking, communities, overview and
  entry-points — seven copies knew only Python layouts. Benchmark: 323 → 630 of
  1,780 files are tests. The route uid stays method + path on purpose — repo
  groups match a client's call to a server's route by it — but
  `cos_graph_contracts` now lists every production registration with its own
  file, line and framework (from its edge), so two services serving `/health`
  are two entries. Test: `test_test_paths.py`.
- [ ] **CC-09 [MEDIUM] Token-budget trimming has no offset.** A hub module's importers
  cannot be listed past the first ~90.
- [x] **CC-10 [LOW] Default edge kinds omit `imports_type`, `re_exports`, `constructs`,
  `awaits` and `dispatches`.** Files and impact are fixed (CC-04); module, class,
  interface, function, method and variable defaults now include them too.
- [x] **CC-11 [LOW] Single-file reindex indexes `.gitignore`d files** the full walk skips.
  Fix: dispatch applies the walk's lockfile, path and `.gitignore` rules.
- [x] **CC-12 [LOW] Every extractor's stubs are stamped `md_links@v1`**, and a stub
  upsert over a real node overwrote its kind and label (workspace packages turned
  `doc_external`). The overwrite is fixed — `upsert_node` keeps the owner's kind
  and label (`test_a_stub_upsert_keeps_the_real_nodes_kind_and_label`); the stamp
  remains.
  The stamp is fixed too: a stub carries the extractor whose edge minted it.
- [x] **CC-14 [MEDIUM] The auto-reindex hook keeps its own extension list** and misses
  every suffix added since (`.astro`, `.mdx`, `.php`, the generic languages). Fix:
  the list now covers every routed suffix plus extensionless files, and
  `test_reindex_hook_suffixes.py` fails the moment `_EXT_MAP` gains one it lacks.
- [x] **CC-15 [HIGH] An extractor upgrade never reaches an existing graph.** The
  per-file cache matched only the content hash and the chain name, so after an
  upgrade every unedited file kept its old extraction until `--force` — none of
  the fixes in this register reached a graph built before them. Fix: the cache
  key carries `GRAPH_EXTRACTION_VERSION` (bump it with any change to
  extraction output), so the next `cos graph-reindex` re-reads each file once.
  Test: `test_an_extractor_upgrade_reindexes_an_unchanged_file`.
- [ ] **CC-13 [MEDIUM] Edit-time reindex depends on the docs module and an unset
  `COS_PYTHON`.** Under a system Python without tree-sitter the regex fallback
  re-indexes a Go file without its type edges. The interpreter half is fixed: the
  hook runs on `cos_resolve_python` (the interpreter `cos` itself uses). Still open:
  the hook ships in the `docs` module, so a graph-on / docs-off profile goes stale.

### TypeScript / JavaScript / React Native

- [x] **TS-01 [CRITICAL] Module resolution was string-based** — `./x.js` kept `.js`,
  extensionless imports always became `.ts` (785 imports of `.tsx` files dangled),
  and no tsconfig `paths`, nested tsconfig, `extends` or workspace package was ever
  consulted (F-02). Stubs kept the importer-relative specifier, so files in
  different folders shared one wrong stub. Fix: `graph_os/resolve_ts.py` mirrors
  TypeScript's bundler resolution (ESM `.js`→`.ts`, extension / index / React
  Native platform probing, the nearest tsconfig or jsconfig through relative
  `extends`, workspace packages through `exports` / `types` / `main`); stubs are
  keyed by the resolved repo file; `link_ts_symbols` binds call stubs and import
  nodes to the exported symbol, following `re_exports` through barrels (one match
  per hop). Benchmark: cross-file TS/TSX call and render edges 0 → 4,168; alias
  stubs 296 → 0; workspace-package stubs 1,007 → 0; dangling `.tsx` guesses
  782 → 60. Tests: `test_resolve_ts.py`, `test_ts_cross_file_links.py`.
- [x] **TS-02 [HIGH] `import Def, { a, b } from …` drops the named half**; `a as b`
  loses the exported name. Fix: every clause form parses (`Def, { … }`,
  `Def, * as ns`), import nodes record the exported name (`default`, `*`, or `a`
  for `a as b`) beside the local one, calls and JSX through an alias point at the
  exported name, and the linker binds `default` to the symbol the module marks as
  its default export (a `.astro` / `.vue` file binds to its module). `export type
  {…} from` and `export { X }` of an import now count as barrel re-exports.
- [x] **TS-03 [HIGH] CommonJS `require()` is a call to `require`, not an import.** Fix:
  every `require('…')` is an `imports` edge (config files, Expo plugins, lazy
  native modules, `require('./logo.png')` assets), and `const x = require(…)`,
  `const { a, b: c } = require(…)` and `import x = require(…)` bind names like an
  import clause, so calls through them link.
- [x] **TS-04 [MEDIUM] JSX usage is sourced at the module, not the component**, and JSX
  in `.js` files is parsed with the non-JSX grammar. Fix: JS-family files parse
  with the tsx grammar and run the JSX passes, and a JSX element's edge starts at
  the component that renders it (benchmark: 3,392 from components).
- [x] **TS-05 [LOW] 17% of import nodes carry the wrong line** (`^\s*import` swallows
  blank lines). Fix: the import and export scanners anchor on horizontal space
  only, so a statement's line is its own.
- [x] **TS-06 [MEDIUM] `typeof import('x')` in a type position counts as a runtime import.**
  Fix: `typeof import(…)` and `import(…).Name` are `imports_type`;
  `import(…).then(…)` stays a runtime import.
- [x] **TS-07 [HIGH] Expo Router screens and `+api` routes, and TanStack file routes,
  produce no contracts;** any `pages/` folder yields phantom Next.js routes, and
  there is no Express / Fastify / Hono scanner although the roadmap says so. Fix:
  `_contracts_file_routes.py` reads the nearest `package.json` and routes a file
  by the router it names — Expo Router screens (route groups dropped, `_layout`
  and `+not-found` skipped) and `+api` endpoints, Next.js only in a `next`
  package, Astro (AS-03) — and TanStack's `createFileRoute('/path')`, with an
  edge to each screen's component or endpoint function. Benchmark: Expo 48,
  Astro 33, TanStack 16 routes, all 0 before; 302 route → handler edges reach a
  real node. The roadmap now says Express / Fastify / Hono are not scanned.
  Test: `test_file_routes.py`.
- [x] **TS-08 [HIGH] Exported non-function values and wrapped components have no node**
  (`memo(...)`, `forwardRef(...)`, stores, query clients, design tokens). Fix:
  `extractors/_ts_exports.py` gives every exported value a `variable` node
  (`metadata.wrapped` names `memo` / `forwardRef` / `create`), including
  `export { a }`, `export declare const` and `export declare function`, and marks
  the default export. Benchmark: in-repo TS import bindings 5,143 → 6,326; imports
  of a name the target exports but the graph could not bind 1,020 → 0.
- [x] **TS-09 [MEDIUM] Module-level `references` omits `imports_type` and `re_exports`,**
  so library fan-in under-counts (react 207 of 344 files). Fix: module defaults
  include both, an external package merges its deep imports (`react/jsx-runtime`),
  and `references` returns `source_files` — distinct importing files, the Q5
  answer. Benchmark: react 344 files (was 207), react-native 279,
  @tanstack/react-query 126. Test: `test_library_fan_in.py`.
- [x] **TS-10 [LOW] Tree-sitter ERROR nodes are never reported** (27 benchmark files);
  nested closures become file-level functions; `Number(x)` counts as construction;
  tsconfig `extends` paths are not normalised and arrays are ignored. Fix: syntax
  errors are parse errors (benchmark files with one 47 → 74); a nested function
  is `Outer.inner` with `contains` from its enclosing function, and calls resolve
  from the innermost scope outward (247 nested functions no longer share uids);
  `Number`, `String`, `Boolean` and the other conversions are calls;
  `extends` arrays and paths were fixed with TS-01.

### Go and Fiber

- [x] **GO-01 [CRITICAL] Same-package calls across files are dropped** (2,264 sites).
  Fix: a bare call the file cannot resolve, and a receiver call to a method declared
  in a sibling file, become `code:external:gopkg:<dir>:<name>` stubs (builtins and
  locally bound names excluded); `link_go_symbols` binds each to the one definition
  directly inside that directory (0.9).
- [x] **GO-02 [CRITICAL] `pkg.Func()` ends at an alias-keyed stub** (`code:external:store.New`
  merged 14 different functions) that never links; 58% of those stubs are really
  method calls on values. Fix: `resolve_go` maps an import path to its in-repo
  directory through the nearest `go.mod` and the root `go.work`; a call is only
  treated as a package call when its operand is an import name not bound locally,
  and the noisy regex pass no longer runs beside the grammar. Library calls are
  keyed by import path (`code:external:<path>:<Name>`). Benchmark: Go cross-file
  call and construct edges 0 → 6,201; unresolved stub edges 10,267 → 4,963.
- [x] **GO-03 [HIGH] Package nodes are keyed by package name** — one `service` node held
  197 files from 18 directories; in-repo imports end at `code:external:<path>`.
  Fix: `code:package:go:<dir>` (`:<name>_test` for external test packages); in-repo
  imports land on it (1,564 on the benchmark); the global link retires the old
  name-keyed nodes.
- [x] **GO-04 [HIGH] Fiber route handlers record the first argument** — the middleware in
  62% of routes; closures become `func`; no handler edge reaches a real node.
  Fix: `extractors/_go_routes.py` reads Fiber routes from the Go syntax tree
  (the regex scanner remains only for a missing grammar). The last argument is
  the handler and the rest are middleware (`metadata.middleware`, plus `calls`
  edges at 0.6); an inline closure points at the function that registers it;
  a named handler resolves like a call — same file, package stub, or import —
  and the Go linker binds it. Benchmark against a go/types ground truth: correct
  handler 59 → 208 of 208 matched registrations; route → handler edges reaching
  a real node 0 → 149 (the rest bind at link time). Test:
  `test_go_fiber_routes.py`.
- [x] **GO-05 [HIGH] No file → symbol `contains` edges**, so `detect_changes` and file
  impact return nothing for Go. Fix: emitted for every top-level function, method
  and type.
- [x] **GO-06 [HIGH] Methods attach to a phantom type when the type is declared in another
  file** (43% of methods); `[]T` / `map[K]V` types are dropped. Fix: no phantom
  class is minted — the receiver and type edges name the package stub, which
  binds to the real declaration; `[]T`, `map[K]V`, `chan T` and `...T` unwrap to
  their named types; and the linker also re-points edges the stub is the source
  of, so a method's `contains` comes from its type. Benchmark: methods under
  their real type 1,261 → 2,228 of 2,228.
- [ ] **GO-07 [MEDIUM] Fiber prefixes are lost across functions, `Route`, mounts and
  `RouteChain`;** trailing slashes are kept. Mostly fixed with GO-04: `Group`,
  `Route` callbacks and `Mount` compose, trailing slashes go, and a router passed
  to a helper in the same file takes the caller's prefix. Still open: a prefix
  only another file knows (19 benchmark routes) — those routes are marked
  `metadata.prefix = "unresolved"` instead of looking complete.
- [x] **GO-08 [MEDIUM] Header names read in tests become routes** (`GET Content-Type`).
  Fix: only a typed router registers a route; an untyped receiver (an app a
  constructor in another package returns) counts only for a `/`-rooted path
  literal in a file importing Fiber. Benchmark false positives 7 → 0.
- [ ] **GO-09 [MEDIUM] Interface methods are not nodes and no `implements` edges exist.**
- [ ] **GO-10 [MEDIUM] `go.mod` / `go.work` are not read**; library fan-in cannot roll
  sub-packages up to the module. The fan-in half is fixed: an import path merges
  its sub-packages (Fiber v3: 87 files across 6 packages). Still open: `require`
  lines are no dependency nodes, so an unused or undeclared module is invisible.
- [x] **GO-11 [LOW] Function-local `var` / `const` / `type` become package-level nodes**
  (36% of Go variables). Fix: only declarations directly in the file are package
  symbols. Benchmark Go variables 2,070 → 1,320 (750 locals gone, 36%).
- [x] **GO-13 [MEDIUM] Type parameters became package types.** `func F[Row any](rows []Row)`
  minted a `Row` type stub and `Row(x)` a call, edges no definition can bind —
  and false "undefined" names for Q6. Fix: type parameters (and a generic
  receiver's `[Item]`) are bound names for calls, and their type edges are
  dropped; the edge rewrites moved to `extractors/_go_edges.py`.
- [x] **GO-12 [LOW] `handles_test` points at a shared name stub**; Go symbols carry no
  `end_line` or signature. Fix: `handles_test` points at the test function itself,
  and (with CC-05) functions and methods carry `end_line` and their `func …`
  signature.

### Python and FastAPI

- [x] **PY-02 [CRITICAL] Module import edges almost never reach the module node** (7% in
  this repo, 0% on the benchmark): relative sources stay `code:module:.x`, the
  module name strips only one `src`/`core` segment, and no pass links modules. Fix:
  relative sources are made absolute, the active toolchain names modules by their
  package roots, and `link_python_modules` binds a `code:module:<dotted>` stub to the
  one repo file whose path ends in that dotted name (stdlib names never bind). Here:
  7% → 31% of module imports reach a module node (the rest are stdlib and
  third-party); relative phantom modules 222 → 0.
- [x] **PY-03 [CRITICAL] An attribute call binds by its last segment** — `requests.get()`
  became a call to an unrelated same-file `Repo.get` at confidence 1.0. Fix: only a
  bare name resolves by name; `Cls.m()` resolves through the class's own methods.
- [x] **PY-04 [CRITICAL] `pydantic.BaseModel` resolved to `pydantic:pydantic`** — 2,299
  type, decorator and base-class edges in this repo point at the module, not the
  attribute. Fix: one `_import_target` serves calls, bases, decorators and
  annotations; such edges here 2,299 → 0.
- [x] **PY-05 [HIGH] FastAPI paths are never composed** from `APIRouter(prefix=)` and
  `include_router(prefix=)`; 101 of 126 Hub routes lack their prefix, and equal
  suffixes merge distinct endpoints. Fix: contracts records each file's routers
  and mounts; `link_fastapi_routes` follows the Python imports to the router a
  name means (a shared `router` module, `users.router`) and renames each route to
  its composed path, recomputing all routes on every link so a prefix edited in
  one file moves routes in others. Until composed, a route a mount may still
  prefix keeps a file-scoped uid (`…@<file>`), so two routers' `/items` never
  merge; a route on a `FastAPI()` app is final at once. This repo's Hub: 126 of
  126 OpenAPI operations exact (was 25). Test: `test_fastapi_routes.py`.
- [x] **PY-06 [HIGH] The route regex misses `""`, `api_route`, `websocket`, `path=` and
  `add_api_route`, and matches example code in docstrings.** Fix:
  `_contracts_fastapi.py` reads the syntax tree — every form above, `{x:path}`
  normalised to OpenAPI's `{x}`, docstrings ignored. The `/foo`-style noise list
  now applies only to regex scanners, and its skipped matches no longer mint a
  phantom stub through the file's `contains` edge.
- [x] **PY-07 [HIGH] Facade / `__init__.py` re-exports are never followed** (2,127 call
  edges unlinked here); relative imports inside `__init__.py` resolve one level high.
  Fix: when a module defines no symbol by the name but imports it, both binding
  passes follow that import node (up to 4 hops) to the definition. This repo's
  Python: import bindings 2,952 → 3,340, cross-file calls to a real node
  2,702 → 2,855; the remaining stub calls are library and stdlib calls.
- [x] **PY-08 [HIGH] Relative `from .x import y` never binds to `y`** (0 of 2,388). Fix:
  the import node records `resolved_module`, which the binding pass matches.
- [x] **PY-09 [HIGH] `Depends(...)`, parameter defaults, decorator arguments and class
  bodies are never walked** (816 call sites). Fix: a function's defaults and its
  decorators' arguments are walked as its own calls, a class body as the class's,
  and an imported callback passed as an argument (`Depends(get_db)`) becomes a
  `dispatches` edge the linker binds. This repo: `dispatches` 21 → 445, calls
  22,542 → 22,989, cross-file calls to a real node 2,855 → 3,015. Test:
  `test_python_dependencies.py`.
- [x] **PY-10 [HIGH] Unbound-name signal** — see CC-06; a `symtable` pass measured 0 false
  positives on 963 files and caught 40 of 40 seeded deleted imports. Fixed with
  CC-06.
- [x] **PY-11 [MEDIUM] `import a.b.c` chains split wrongly** (`os.path:path.join`). Fix:
  the longest imported module the expression starts with is the module.
- [x] **PY-12 [MEDIUM] Call chains collapse into attribute paths** (`hashlib:sha256.hexdigest`).
  Fix: a call on a computed value (a call result or a subscript) is not folded
  into a dotted name; the inner `hashlib.sha256(...)` call is still an edge.
- [x] **PY-13 [MEDIUM] Module-level variables (`app`, `router`, `mcp`) are not nodes.** Fix:
  every name assigned at module scope (tuple targets and `if` / `try` blocks
  included, function and class bodies not) is a `variable` node, so `from .main
  import app` binds and the value carries a body fingerprint.
- [x] **PY-14 [MEDIUM] Submodule imports do not roll up to the package** for fan-in.
  Fix: `references(code:module:fastapi)` merges `fastapi.*` stubs (13 files on
  the benchmark, `fastapi.testclient` included).
- [ ] **PY-15 [LOW] `super().m()`, inherited `self.m()` and `cls()` are unresolved.**
- [x] **PY-16 [LOW] `TYPE_CHECKING` imports count as runtime cycles.** Fix: an import
  under `if TYPE_CHECKING:` is `imports_type`, which cycle detection skips. Found
  on the way: with `try: from .x import f / except ImportError: from x import f`
  the fallback replaced the real binding, and facade linking only worked by luck
  of walk order — the first binding of a name now wins (import bindings here
  3,958 → 4,015).

### Shell

- [x] **SH-01 [CRITICAL] Calls to functions from `source`d libraries never link** — 510
  call sites in 98 hooks, 0 edges. Fix: a command the file does not define becomes a
  `code:external:shfn:<name>` stub; `link_shell_functions` binds it to the one real
  definition (fallback shims excluded, SH-06). This repo's hooks: 0 → 286 edges;
  `cos_log_hook` now shows 83 calling files. External tools keep their stub (Q5).
- [x] **SH-02 [CRITICAL] Script → Python / Node invocations emit nothing** — 63 hook →
  helper dependencies, 0 edges. Fix: `python*`, `$PY`-style variables, `uv run …
  python`, `node`/`tsx`/`bun`, `npx`/`pnpm exec`, `bash`/`sh` and wrappers
  (`exec`, `nice`, `timeout`, `env`) emit `calls` to the file they run (`-m` to the
  module); 0 → 34 of the 63 here — the rest go through a helper-dir function.
- [x] **SH-03 [HIGH] Script-directory variables, `# shellcheck source=` and literal loops
  are not followed** — 26 of 137 `source` lines unresolved; four core libraries
  showed 0 dependents. Fix: `_shell_paths.ShellScope` expands the script-dir idioms and
  variables built on them, literal `for` loops unroll, and a directive on the line
  above a dynamic `source` names its file.
- [x] **SH-04 [HIGH] Repo-root-relative paths are joined to the script folder** and minted
  as phantom files (`scripts/x/scripts/x/y.sh`). Fix: a bare path tries the script
  folder then the repo root and keeps the one that exists; absolute, `~` and missing
  paths mint nothing.
- [x] **SH-05 [MEDIUM] Quoted literals are dropped** (`bash "x.sh"`), and a later argument
  can be taken as the script. Fix: quotes are stripped from words and only the first
  positional argument is the script.
- [x] **SH-06 [MEDIUM] 86 no-op fallback definitions of `cos_log_hook` hide the real one.**
  Fix: a definition guarded by `command -v` / `declare -F` / `type` is tagged
  `fallback_shim` and left out of same-file and cross-file binding.
- [x] **SH-07 [MEDIUM] `.agents/` is excluded wholesale**, though consumer repos keep
  tracked scripts there. Fix: only `.agents/memory` (agent-written notes) is
  excluded; a project's own hooks, skills and scripts there are walked (68 shell
  files in the consumer the auditor checked).
- [x] **SH-08 [LOW] Shell functions have no `end_line` or body hash; confidences are
  constants; env-prefixed and wrapped commands are missed.** `end_line` and the
  body fingerprint came with CC-05; env-prefixed (`FOO=1 cmd`) and wrapped
  (`env`, `exec`, `nice`, `timeout`) commands with SH-02; and confidence now
  follows the evidence — an anchored `source` 0.9 against a guessed path 0.7, a
  run file 0.85 / 0.7, a `-m` module 0.6, a local call 0.9, a library-function stub
  0.5 until linked.

### Astro

- [x] **AS-01 [CRITICAL] `.astro` files are never indexed** — 87% of the site's import
  edges start in them; a util imported only by pages looks dead. Fix:
  `_astro_split.mask_astro` hands `code_ts` a same-length view of the frontmatter
  and processable scripts (`lang='astro'`, hash of the real file); imports resolve
  through `resolve_ts` like any TS file. Test: `test_extension_coverage.py`.
- [x] **AS-02 [HIGH] `.mdx` content is never indexed.** Fix: routed to the markdown
  graph extractor (the docs RAG layer stays `.md`-only).
- [x] **AS-03 [MEDIUM] Pages are not routes;** `export const GET: APIRoute`, `ALL` and
  `.js` endpoints are missed, and `framework` says `nextjs`. Fixed with TS-07:
  `src/pages/` `.astro` files are page routes, `.ts` / `.js` files endpoints for
  every exported method (`ALL` included), `_`-prefixed files skipped.
- [x] **AS-04 [MEDIUM] Endpoint handlers and `getStaticPaths` look dead.** Fixed with
  TS-07: each route calls its endpoint function, and a page calls its
  `getStaticPaths`, so dead-code no longer lists them.
