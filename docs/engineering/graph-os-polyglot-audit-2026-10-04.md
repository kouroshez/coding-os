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

- [ ] **CC-01 [CRITICAL] Cross-file link passes only know Python.** `link_external_stubs`
  and `link_import_bindings` match `<module>.py` / `__init__.py` only, so Go, TS and
  shell stubs never reach a real symbol: 0 cross-file call edges for Go and TS on
  the benchmark. Fixed per language below (TS-01, GO-01/02, SH-01).
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
- [ ] **CC-04 [HIGH] `references(code:file:X)` silently answers 0 for TS, Go and Python.**
  Importers point at the module (or Go import-path) node; the folder `contains`
  edge keeps the zero-from-kind-filter warning from firing.
- [ ] **CC-05 [HIGH] No duplicate / clone signal (Q2).** `ast_hash` exists for Python
  only and hashes the uid, so two files can never match; Go, TS and shell set none.
- [ ] **CC-06 [HIGH] No unbound-name signal (Q6).** `code:external:unresolved:*` is 98–99.9%
  builtins, members and locals; Go emits nothing for an unknown call.
- [x] **CC-07 [MEDIUM] JS / PHP file nodes end up `lang='txt'`.** `contracts._lang_for`
  knows four suffixes and overwrites the code extractor's value. Fix: it returns the
  script family's own language (`js`, `jsx`, `ts`, …) or nothing, and the JS/TS
  contract scanners now also run on `.js`, `.jsx`, `.mjs`, `.cjs`, `.mts`, `.cts`.
- [ ] **CC-08 [MEDIUM] Route uids are global.** `cos:route:GET:/health` from a Go service
  and a Python service merge into one node; the test-source filter misses
  `_test.go`, `.test.ts`, `.spec.ts`.
- [ ] **CC-09 [MEDIUM] Token-budget trimming has no offset.** A hub module's importers
  cannot be listed past the first ~90.
- [ ] **CC-10 [LOW] Default edge kinds omit `imports_type`, `re_exports`, `constructs`,
  `awaits` and `dispatches`.**
- [x] **CC-11 [LOW] Single-file reindex indexes `.gitignore`d files** the full walk skips.
  Fix: dispatch applies the walk's lockfile, path and `.gitignore` rules.
- [ ] **CC-12 [LOW] Every extractor's stubs are stamped `md_links@v1`**, and a stub
  upsert over a real node overwrote its kind and label (workspace packages turned
  `doc_external`). The overwrite is fixed — `upsert_node` keeps the owner's kind
  and label (`test_a_stub_upsert_keeps_the_real_nodes_kind_and_label`); the stamp
  remains.
- [x] **CC-14 [MEDIUM] The auto-reindex hook keeps its own extension list** and misses
  every suffix added since (`.astro`, `.mdx`, `.php`, the generic languages). Fix:
  the list now covers every routed suffix plus extensionless files, and
  `test_reindex_hook_suffixes.py` fails the moment `_EXT_MAP` gains one it lacks.
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
- [ ] **TS-02 [HIGH] `import Def, { a, b } from …` drops the named half**; `a as b`
  loses the exported name.
- [ ] **TS-03 [HIGH] CommonJS `require()` is a call to `require`, not an import.**
- [ ] **TS-04 [MEDIUM] JSX usage is sourced at the module, not the component**, and JSX
  in `.js` files is parsed with the non-JSX grammar. The grammar half is fixed —
  JS-family files parse with the tsx grammar and run the JSX passes.
- [ ] **TS-05 [LOW] 17% of import nodes carry the wrong line** (`^\s*import` swallows
  blank lines).
- [ ] **TS-06 [MEDIUM] `typeof import('x')` in a type position counts as a runtime import.**
- [ ] **TS-07 [HIGH] Expo Router screens and `+api` routes, and TanStack file routes,
  produce no contracts;** any `pages/` folder yields phantom Next.js routes, and
  there is no Express / Fastify / Hono scanner although the roadmap says so.
- [ ] **TS-08 [HIGH] Exported non-function values and wrapped components have no node**
  (`memo(...)`, `forwardRef(...)`, stores, query clients, design tokens).
- [ ] **TS-09 [MEDIUM] Module-level `references` omits `imports_type` and `re_exports`,**
  so library fan-in under-counts (react 207 of 344 files).
- [ ] **TS-10 [LOW] Tree-sitter ERROR nodes are never reported** (27 benchmark files);
  nested closures become file-level functions; `Number(x)` counts as construction;
  tsconfig `extends` paths are not normalised and arrays are ignored.

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
- [ ] **GO-04 [HIGH] Fiber route handlers record the first argument** — the middleware in
  62% of routes; closures become `func`; no handler edge reaches a real node.
- [x] **GO-05 [HIGH] No file → symbol `contains` edges**, so `detect_changes` and file
  impact return nothing for Go. Fix: emitted for every top-level function, method
  and type.
- [ ] **GO-06 [HIGH] Methods attach to a phantom type when the type is declared in another
  file** (43% of methods); `[]T` / `map[K]V` types are dropped. Partly fixed: no
  phantom class is minted any more — the receiver and type edges name the
  package stub, which binds type edges to the real declaration; `[]T`,
  `map[K]V`, `chan T` and `...T` unwrap to their named types. Still open: a
  method's `contains` edge comes from that stub, not the declaring type's node.
- [ ] **GO-07 [MEDIUM] Fiber prefixes are lost across functions, `Route`, mounts and
  `RouteChain`;** trailing slashes are kept.
- [ ] **GO-08 [MEDIUM] Header names read in tests become routes** (`GET Content-Type`).
- [ ] **GO-09 [MEDIUM] Interface methods are not nodes and no `implements` edges exist.**
- [ ] **GO-10 [MEDIUM] `go.mod` / `go.work` are not read**; library fan-in cannot roll
  sub-packages up to the module.
- [ ] **GO-11 [LOW] Function-local `var` / `const` / `type` become package-level nodes**
  (36% of Go variables).
- [ ] **GO-12 [LOW] `handles_test` points at a shared name stub**; Go symbols carry no
  `end_line` or signature.

### Python and FastAPI

- [ ] **PY-02 [CRITICAL] Module import edges almost never reach the module node** (7% in
  this repo, 0% on the benchmark): relative sources stay `code:module:.x`, the
  module name strips only one `src`/`core` segment, and no pass links modules.
- [ ] **PY-03 [CRITICAL] An attribute call binds by its last segment** — `requests.get()`
  became a call to an unrelated same-file `Repo.get` at confidence 1.0.
- [ ] **PY-04 [CRITICAL] `pydantic.BaseModel` resolved to `pydantic:pydantic`** — 2,299
  type, decorator and base-class edges in this repo point at the module, not the
  attribute.
- [ ] **PY-05 [HIGH] FastAPI paths are never composed** from `APIRouter(prefix=)` and
  `include_router(prefix=)`; 101 of 126 Hub routes lack their prefix, and equal
  suffixes merge distinct endpoints.
- [ ] **PY-06 [HIGH] The route regex misses `""`, `api_route`, `websocket`, `path=` and
  `add_api_route`, and matches example code in docstrings.**
- [ ] **PY-07 [HIGH] Facade / `__init__.py` re-exports are never followed** (2,127 call
  edges unlinked here); relative imports inside `__init__.py` resolve one level high.
- [ ] **PY-08 [HIGH] Relative `from .x import y` never binds to `y`** (0 of 2,388).
- [ ] **PY-09 [HIGH] `Depends(...)`, parameter defaults, decorator arguments and class
  bodies are never walked** (816 call sites).
- [ ] **PY-10 [HIGH] Unbound-name signal** — see CC-06; a `symtable` pass measured 0 false
  positives on 963 files and caught 40 of 40 seeded deleted imports.
- [ ] **PY-11 [MEDIUM] `import a.b.c` chains split wrongly** (`os.path:path.join`).
- [ ] **PY-12 [MEDIUM] Call chains collapse into attribute paths** (`hashlib:sha256.hexdigest`).
- [ ] **PY-13 [MEDIUM] Module-level variables (`app`, `router`, `mcp`) are not nodes.**
- [ ] **PY-14 [MEDIUM] Submodule imports do not roll up to the package** for fan-in.
- [ ] **PY-15 [LOW] `super().m()`, inherited `self.m()` and `cls()` are unresolved.**
- [ ] **PY-16 [LOW] `TYPE_CHECKING` imports count as runtime cycles.**

### Shell

- [ ] **SH-01 [CRITICAL] Calls to functions from `source`d libraries never link** — 510
  call sites in 98 hooks, 0 edges.
- [ ] **SH-02 [CRITICAL] Script → Python / Node invocations emit nothing** — 63 hook →
  helper dependencies, 0 edges.
- [ ] **SH-03 [HIGH] Script-directory variables, `# shellcheck source=` and literal loops
  are not followed** — 26 of 137 `source` lines unresolved; four core libraries
  showed 0 dependents.
- [ ] **SH-04 [HIGH] Repo-root-relative paths are joined to the script folder** and minted
  as phantom files (`scripts/x/scripts/x/y.sh`).
- [ ] **SH-05 [MEDIUM] Quoted literals are dropped** (`bash "x.sh"`), and a later argument
  can be taken as the script.
- [ ] **SH-06 [MEDIUM] 86 no-op fallback definitions of `cos_log_hook` hide the real one.**
- [ ] **SH-07 [MEDIUM] `.agents/` is excluded wholesale**, though consumer repos keep
  tracked scripts there.
- [ ] **SH-08 [LOW] Shell functions have no `end_line` or body hash; confidences are
  constants; env-prefixed and wrapped commands are missed.**

### Astro

- [x] **AS-01 [CRITICAL] `.astro` files are never indexed** — 87% of the site's import
  edges start in them; a util imported only by pages looks dead. Fix:
  `_astro_split.mask_astro` hands `code_ts` a same-length view of the frontmatter
  and processable scripts (`lang='astro'`, hash of the real file); imports resolve
  through `resolve_ts` like any TS file. Test: `test_extension_coverage.py`.
- [x] **AS-02 [HIGH] `.mdx` content is never indexed.** Fix: routed to the markdown
  graph extractor (the docs RAG layer stays `.md`-only).
- [ ] **AS-03 [MEDIUM] Pages are not routes;** `export const GET: APIRoute`, `ALL` and
  `.js` endpoints are missed, and `framework` says `nextjs`.
- [ ] **AS-04 [MEDIUM] Endpoint handlers and `getStaticPaths` look dead.**
