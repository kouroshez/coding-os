<!-- domain:CORE | layer:engineering | ssot:false | updated:2026-10-07 -->
# Graph-OS Final Verification Round (2026-10-07)

> P: Register of the defects a seven-member audit team confirmed on graph_os
>    after the first audit closed, with the fix checklist.
> R: Fixing or reviewing an item below.
> S: The first audit's items: see
>    [graph-os-polyglot-audit-2026-10-04.md](graph-os-polyglot-audit-2026-10-04.md).
> N: [graph_os-queries.md](graph_os-queries.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Method

Seven read-only auditors, one per scope (Go and Fiber; TS, JS and React
Native; Python and FastAPI; Shell; Astro; cross-language completeness;
external practice), probed HEAD after the first audit's 71 items and the
review's 12 findings. Each listed only what a probe it ran reproduced, against
adversarial fixtures and the benchmark (the private monorepo of the first
audit, rebuilt at HEAD). The practice researcher checked behaviour against the
language specs and established tools through Firecrawl. Overlapping reports
are merged below; the scope tags name who found an item.

Severity follows the first audit. Tags: GO, TS, PY, SH, AS, CO (completeness),
EX (external practice).

## Checklist

### Freshness and storage

- [x] **V-01 [CRITICAL] A linker moves the extracted stub edge onto the real
  node, so deleting, renaming or moving that node cascades the caller's edge
  away for good** (CO D1, GO 3, PY 3, SH 1). Benchmark: renaming one Go file
  and moving one TS file lost 1,209 edges until `--force`. Fix: before a prune
  (an edit's, a deleted file's, or the bulk reconcile's) the backend lists the
  other files with edges into the doomed nodes (`files_depending_on`); after it
  each is re-extracted with `force`, so its stub comes back and links wherever
  the symbol lives now. The same move now leaves 435 and 547 inbound edges, as a
  fresh build does; the whole-graph diff fell from 1,209 edges to 5. Test:
  `test_relink_after_edits.py`.
- [x] **V-02 [HIGH] Edit-time linking only binds stubs the edited file emits**,
  so callers of a symbol added to it, or of a new file, stay on stubs (CO D4,
  TS 6, GO 3). Fix: the uids a file gains name stubs; the files holding those
  stubs rerun their own per-file link passes (`link_callers_of`), each language
  keeping its binding rules. Tests: `test_relink_after_edits.py` (Python, TS, Go,
  shell; a Go function moved to a new file) and
  `test_a_stub_minted_before_its_target_binds_when_the_target_is_indexed`.
- [x] **V-03 [HIGH] The per-file cache ignores inputs besides the file**: a
  tsconfig `paths` change or a newly created sourced file never reaches files
  already indexed (CO D2). Fix: the cache key carries a digest of the config a
  file's imports resolve through (`resolution_fingerprint`): the tsconfig or
  jsconfig `extends` chain and the workspace manifests for TS/JS/Astro, the
  governing go.mod and any go.work for Go — so a non-force reindex re-reads
  exactly the files an alias or module-path edit governs. A file created after
  its importer already binds through the V-02/V-15 relink (checked for a TS
  import and a sourced shell function). Cost: a full cache-hit pass over 1,618
  benchmark files 1.16 s → 1.36 s. Test:
  `test_a_changed_resolution_config_reindexes_the_files_it_governs`.
- [x] **V-04 [MEDIUM] `upsert_node` reads and writes outside one transaction**;
  under `-j N` a stub overwrites a real node (CO D6, TS 4; 2 benchmark modules).
  Fix: `_write()` opens `BEGIN IMMEDIATE`, so the database's write lock — not
  only the per-process thread lock — is held from the first read; `upsert_edge`
  drops its own now-redundant BEGIN. Benchmark, three `-j 8` builds against a
  serial one: HEAD differed on 0, 2 and 1 nodes (a TSX module, a Go package);
  now 0, 0 and 1 — the one is a route two files register, whose shared node
  takes the last writer's fields by design (V-07). Test:
  `test_a_write_holds_the_database_lock_from_its_first_read`.
- [x] **V-05 [MEDIUM] The deletion prune keeps the file's cache row**, so a
  file restored with the same bytes is a cache hit with no nodes (CO D9). Fix:
  the deletion prune drops every `file_index_state` row of the path
  (`forget_file_state`), the docs row with the graph ones — the doc indexer
  already removes a missing file's chunks. Test:
  `test_a_deleted_file_restored_with_the_same_bytes_is_indexed_again`.
- [x] **V-06 [MEDIUM] The Bash reconcile hook runs no link pass on delete and
  gates on a stale suffix list** (CO D5). Fix: the hook watches every routed
  suffix (`ROUTED_SUFFIXES`, held to `_EXT_MAP` by a test) and hands the
  touched paths, gone ones first, to one `dispatch` worker
  (`cos_reindex_paths` in `_reindex_on_edit.sh`): a deleted file is pruned,
  its dependents re-read and the links rerun, as an edit-time delete already
  was. The worker resolves the project root, the core and the interpreter like
  the edit hooks and takes the paths as arguments — the old inline Python read
  `src/core` from `$PWD` and pasted each path into its source.
  `prune_deleted_path.py` is no longer on this path. Tests:
  `test_the_shell_reconcile_hook_prunes_and_indexes_every_routed_suffix`,
  `test_the_shell_reconcile_hook_watches_every_routed_suffix`.

### Routes and contracts

- [x] **V-07 [HIGH] Route uids are global per method and path**: routes of
  different apps or services merge into one node, and one owner's deletion
  takes the others (AS 1, CO D3, GO 7, TS 12). Fix: the loss was the defect,
  and V-01 closes it — the other registrants hold edges into the pruned node,
  so they are re-read and mint it again. The shared uid stays on purpose: the
  route node is the HTTP contract (method and path) that `groups/cross_repo.py`
  matches client calls against, and each registration is its own
  `handles_route` edge with its own span, which `cos_graph_contracts` lists
  separately. The auditor's fixture now matches a fresh build after a delete
  and after an edit-out (0 edges lost, the FastAPI registration still listed).
  Test: `test_a_route_two_services_register_survives_one_of_them_leaving`
  (fails with the dependent refresh switched off).
- [x] **V-08 [HIGH] `cos_graph_contracts` reads 200 rows by confidence,
  ignores `scope` and cannot page** (GO 1, TS 13; 1 of 196 Fiber routes shown).
  Fix: every `handles_*` edge is read (one bulk node fetch per edge type),
  `scope` keeps the registrations under that path prefix, and the list is
  ordered by file and line, then paged with `offset`/`limit` against a
  `total_count`; the MCP tool and `cos graph-contracts` take both. Benchmark:
  `total_count` 194, first page 63 (token trim, `result_truncated`), paging
  reaches all 194 in 12 ms. Test: `test_contracts_paging.py`.
- [x] **V-09 [HIGH] Fiber sub-apps passed as `*fiber.App` and mounted with
  `Use`/`Mount` are not composed; a second mount overwrites the first** (GO 5).
  Fix: a router keeps every mount (`_Router.mounts`) and its prefixes branch
  over all of them; an `*fiber.App` parameter stays the root unless a caller
  passes it a mounted sub-app — its routes carry `router_root`, so the link pass
  composes them from such a caller and otherwise leaves them where they are
  (never provisional). The benchmark has no sub-app mounts: its 205 Fiber
  routes and 11 unresolved prefixes are unchanged. Test:
  `test_a_mounted_sub_app_composes_once_per_mount_and_an_app_parameter_stays_the_root`.
  Extraction version 30.
- [x] **V-10 [MEDIUM] Fiber routes on struct-field routers, `RouteChain`,
  `Add`, `Domain` and inline `Group(...)` receivers are missing** (GO 6, EX 11).
  Fix: a route's receiver may be a struct field typed as a Fiber router
  (`s.app.Get`), an inline `Group(…)`, a `Domain(…)` or a v3 `RouteChain(…)`
  whose verbs take only handlers (`_go_route_receivers.py`), and `Add` takes a
  method or a `[]string` of them. The benchmark uses none of these forms (205
  routes before and after). Extraction version 45. Test:
  `test_struct_field_routers_inline_groups_add_route_chains_and_domains_register_routes`.
- [x] **V-11 [MEDIUM] FastAPI: a non-literal prefix is dropped unmarked,
  sub-project mounts never resolve, `app.mount` is ignored, a router included
  twice keeps one mount, an annotated router assignment is missed** (PY 4, EX 3).
  Fix: a prefix is a literal or a module-level string constant, anything else
  marks the route `prefix: unresolved`; `router: APIRouter = …` counts;
  `app.mount("/sub", sub_app)` mounts like an include (`StaticFiles(…)` does
  not); a router keeps every mount, in the file and across files, so a second
  include adds its path (`also_mounted_at`); and the link pass reaches a
  router through the file its import is bound to, so a sub-project's
  `from app.routers import x` resolves. The benchmark's 8 routes are unchanged
  (its prefixes are literal `APIRouter(prefix=…)`). Extraction version 46.
  Tests: `test_constant_and_unknown_prefixes_annotated_routers_double_includes_and_mounted_apps`,
  `test_a_sub_project_router_included_twice_from_another_file_gets_both_paths`.
- [x] **V-12 [MEDIUM] A route handler nested in a factory, a method or an
  imported endpoint points at a phantom node** (PY 5). Fix: the FastAPI scan
  walks with its scope, so a handler is named as code_python names it
  (`create_app.ping`, the method `Items.list_items`), and an
  `add_api_route(…, endpoint)` naming an import points at
  `code:external:<module>:<name>`, which the Python linker binds. Benchmark:
  2 phantom handler targets, 0 after. Extraction version 41. Test:
  `test_a_handler_in_a_factory_a_class_or_another_module_points_at_its_real_node`.
- [x] **V-13 [MEDIUM] File-route paths and forms**: `_` directories, `[a]-[b]`,
  `[id].json`, `.md`/`.mdx`/`.html` pages, `export { x as GET }`, an Expo
  `export { default } from`, `const X; export default X`, TanStack
  `createRoute` (AS 6–8, TS 12, EX 12). Fix: any `_` folder hides an Astro
  route; every `[param]` in a segment becomes `{param}` (`/{lang}-{slug}`,
  `/api/{id}.json`); `.md`/`.mdx` pages under an Astro `src/pages/` run
  `contracts` too, which hangs the route on the doc's own node
  (`scan_markdown_page`); `export { handle as POST }` is an endpoint; Expo
  reads `export { default } from` and names the handler of
  `export default Settings`; TanStack code routes compose `path` up their
  `getParentRoute` chain. `.html` is indexed by no extractor and stays out.
  The benchmark's 105 file routes are unchanged — every Expo screen already
  routed. Extraction version 47. Test: `test_route_forms_beyond_the_plain_file`.

### References and impact

- [x] **V-14 [HIGH] `references(file)` ignores edges into the file's symbols**,
  so a file consumed through a barrel shows 5 of 105 dependents (TS 1). Fix:
  a file's references are the edges other files hold into any node it defines
  (`list_edges(target_file=…)`, one indexed query; its own internal calls stay
  out), plus its Go package. Benchmark: the barrel-consumed component went from
  5 to 108 dependent files, the database's own count; the five most-used files
  match it exactly (178–298) in 11–68 ms, and paging reaches every row (853 of
  853). Test: `test_a_files_references_count_the_files_that_reach_its_symbols_through_a_barrel`.
- [x] **V-15 [HIGH] Python `from pkg import submodule` never reaches the
  submodule's file**: `references(file)` finds 25 of 100 importer pairs (PY 1).
  Fix: an imported name the package does not define binds to the one repo
  module `<package>.<name>` (stdlib names excluded), and at edit time a new
  Python file's own name, like any new symbol, relinks the files whose import
  nodes name it — an import that is never called holds no stub to find it by.
  Benchmark: 75 of 75 such imports bind (0 before); `references(file)` recall
  is 100 of 100 importer pairs (62 after V-14) and `impact` 100 (83). Tests:
  `test_from_package_import_submodule_binds_to_the_submodules_file`,
  `test_an_import_only_name_binds_when_its_symbol_or_submodule_appears_later`.
- [x] **V-16 [HIGH] Default reference kinds omit `constructs` for functions and
  `calls`/`constructs` for variables**, hiding every JSX render (TS 2). Fix:
  both defaults include them (and `awaits` for variables). Test:
  `test_default_references_include_renders_and_calls_through_variables`.
- [x] **V-17 [MEDIUM] `impact(depth=1)` on a file drops its direct dependents**
  for edges that target the file node (SH 3). Fix: a file's impact walks the
  file node alongside its symbols and module instead of in place of them — a
  shell `source` points at the file itself. Test:
  `test_impact_on_a_sourced_library_names_every_script_that_sources_it`.
- [x] **V-18 [LOW] `impact` and `duplicates` are trimmed with no `offset`** (CO D12).
  Fix: `impact` takes `offset` / `limit` over one order — tier by tier, walk
  order within each — and reports `count` / `total_count`; `duplicates` takes
  `offset` over its three lists. The MCP tools and the CLI twins take both.
  Tests: `test_impact_pages_through_every_edge_in_tier_order`,
  `test_offset_pages_through_every_clone_group`.
- [x] **V-19 [MEDIUM] tsconfig `extends` edges are not normalised, read a
  package preset as a path, and ignore the array form** (CO D7). Fix: a
  relative parent is `normpath`-ed (`../../tsconfig.base` is the root file, not
  `apps/mobile/../../…`), a bare specifier is the package preset
  `code:module:npm:<specifier>` — it rolls into that package's fan-in like an
  import — and a list is read entry by entry. Extraction version 37. Test:
  `test_tsconfig_extends_normalises_paths_and_reads_presets_and_arrays`.

### Go

- [x] **V-20 [HIGH] `_retarget_type` rewrites import and call ids when a
  package name prefixes another import's domain** (GO 2). Fix: only an
  `alias.Name` of two identifiers is a qualified type. Test:
  `test_an_import_named_like_another_imports_domain_keeps_both_ids`.
- [x] **V-21 [HIGH] The Python linker binds Go library stubs to Python files**
  (`context.Context` → `context.py::Context`) (GO 4). Fix: the pass selects and
  rewrites only edges whose source is Python. Test:
  `test_a_go_library_reference_never_links_to_a_python_file_of_the_same_name`.
- [x] **V-22 [HIGH] Go method calls on fields, locals and call results produce
  no edge** (EX 1; 0 of 4,279 on the benchmark). Fix: a receiver's type is
  read where the source spells it (`_go_receivers.py`) — a parameter, `var x T`,
  `T{}` / `&T{}` / `new(T)`, a field of a struct in the file, a function's
  result — and the call becomes a `T.M` stub; a name bound more than one way is
  left alone. A field of a struct, or the result of a function, declared in
  another file becomes `T.field.M` / `F().M`, which the Go linker resolves from
  that declaration's `go_fields` / `go_result` metadata. The global link pass
  indexes Go symbols once instead of querying per stub. Benchmark (566 files):
  calls reaching a real Go method 936 → 2,929, plus 491 calls into 60 library
  methods; the link pass 20.9 s → 16.1 s; 309 member stubs stay unbound
  (promoted through embedding, library results). Route handlers keep the old
  resolution (V-26). Extraction version 27. Test: `test_go_member_calls.py`.
- [x] **V-23 [MEDIUM] go.work `use .`, a `replace` without go.work and an
  in-repo sibling module mis-resolve or report a false unused require**
  (GO 8–10, EX 8). `use .` already resolved. Fix: a `replace X => ../dir`
  line or block entry in the importer's go.mod maps X to that repo folder
  (`resolve_go._local_replaces`; a target outside the repo stays external), so
  the call reaches the real function instead of `code:external:X`. An import
  that resolved to an in-repo package now counts toward its module's require,
  so a sibling module both required and imported is no `unused_requirement`.
  The benchmark has one module and no replace: unchanged, 0 gaps and 1,564
  in-repo imports. Extraction version 48. Test:
  `test_a_local_replace_resolves_the_import_and_a_used_sibling_module_is_no_unused_require`.
- [x] **V-24 [MEDIUM] A Go call into a package never imported is not reported**
  (GO 11). Fix: a selector call on a lowercase name that is no import, local,
  receiver or typed name is recorded on the module (`go_unimported`), and
  `cos_graph_undefined` reports it `not_imported` only when no file of the
  package declares the name. Measuring precision exposed two gaps, now closed:
  grouped `var ( … )` blocks (a `var_spec_list`) made no nodes — 174 package
  variables were missing on the benchmark, 1,320 → 1,494 — and a type switch's
  `x := v.(type)` was no binding. The compiling benchmark reports 0. Extraction
  version 40. Test: `test_a_go_call_into_a_package_never_imported_is_reported`.
- [x] **V-25 [LOW] `implements` precision**: signatures not compared, embedded
  conflicts, methods hung by directory and name onto test fakes, embedded
  `error`, `type Runner Base` (GO 12, EX 5). Fix: every Go method and interface
  method records `go_types` (`[]byte,int->int,error`, names and package
  qualifiers dropped), and `implements` compares it beside arity unless either
  side is generic; a method set keeps each name at its shallowest embedding
  depth and leaves out one two embedded types promote at that depth, as the
  compiler does; `struct{ error }` promotes `Error()`; a method joins a type of
  another file only when both files have one package clause, so an external
  `x_test` package's fake no longer lends its methods to the real type (or the
  other way round). Checked and already right: `type Runner Base` inherits no
  method. The benchmark has none of these shapes: 174 `implements` edges,
  identical. Extraction version 55. Test: `test_go_implements_precision.py`.
- [x] **V-26 [LOW] Go resolution gaps**: handler on a parameter or local, a
  parameter shadowing a file function, package name ≠ directory, explicit
  generic calls, several `init()`, a deprecated `module` line, build-tag twins
  (GO 13–14, EX 8). Fix: a parameter or local shadows the file's function of
  that name (scope checked first in `_call_target`); `Map[int](xs)` and
  `pkg.Wrap[T](xs)` (which the grammar parses as a conversion to a generic
  type) call the instantiated function; an unaliased in-repo import is used
  by its folder's `package` clause name (`resolve_go.package_name`, cached), not
  the folder's; each `init` is its own node (`init`, `init#2`, …) with its own
  calls, and `var _ T = …` makes no variable; `module x // Deprecated: …` and a
  commented `replace` line parse; a call to build-constrained twins
  (`open_linux.go` / `open_darwin.go`, or `//go:build`) reaches every twin
  instead of none; a Fiber handler on a typed local or parameter
  (`users.List`) resolves by its type, and a handler parameter no longer binds
  to a same-named file function. Benchmark (567 Go files): 10,720 calls and
  218 route handlers on their real node either way, 3 phantom `_` variables
  gone — none of the other forms occurs there. Extraction version 54. Test:
  `test_go_resolution.py`.

### Python

- [x] **V-27 [HIGH] `Depends(module.fn)` and `Depends` inside `Annotated[...]`
  make no edge** (PY 2). Fix: `Depends`/`Security` calls in a parameter's
  annotation — inline or through a module-level alias such as `SessionDep` —
  are walked in the function's scope, and their `module.fn` argument resolves
  like a call. Only those two calls take an attribute: a generic rule would
  have added 809 value-passing edges here (`print(sys.stderr)`). Benchmark: the
  four router-level `dependencies=[fastapi.Depends(auth.…)]` now reach the auth
  function (0 before). Extraction version 26. Test:
  `test_dependencies_in_annotations_aliases_and_module_attributes_reach_their_function`.
- [x] **V-28 [MEDIUM] A bare name resolves file-wide to a method or another
  function's nested function** (PY 6). Fix: a bare call resolves by Python's
  scoping (`_visible_declaration`): the module and the functions enclosing the
  caller, innermost first; a method only from its own class body. Benchmark
  plus this repo: 34 bare calls bound to a declaration the caller cannot see,
  0 after (11 now unresolved, the rest on the visible one). Extraction version
  35. Test: `test_a_bare_name_sees_only_the_module_and_its_own_enclosing_functions`.
- [x] **V-29 [MEDIUM] `self.attr.m()` binds to the enclosing class's own `m`** (PY 7).
  Fix: only `self.m()` / `cls.m()` — one dot — binds to the class's own method;
  `self.repo.save()` stays an unresolved stub. The benchmark holds no such call
  (own-method bindings 6 before and after). Extraction version 33. Test:
  `test_a_call_on_an_attribute_of_self_is_not_this_classs_own_method`.
- [x] **V-30 [MEDIUM] A third-party import binds to a repo file of the same
  name, and can store a self-loop** (PY 8, EX 4). Fix: a name `pyproject.toml`
  declares as a dependency binds to a repo file only at that very path (from
  the root or `src/`), never by suffix (`_names_module`, shared by the three
  Python linkers, and the module index); a module never binds an import to
  itself. Path-hack imports of non-dependency names keep their suffix match:
  this repo binds the same 5,795 import nodes before and after, and neither it
  nor the benchmark holds a shadowed dependency. Extraction version 36. Test:
  `test_a_declared_dependency_never_binds_to_a_repo_file_of_the_same_name`.
- [x] **V-31 [MEDIUM] An import of a name its Python module no longer defines
  is not reported** (PY 9). Fix: `cos_graph_undefined` reports a Python
  `from m import name` as `not_exported` when `m` is a repo module that neither
  defines nor re-imports the name, has no such submodule, and holds no star
  import or module `__getattr__` (`_py_broken_imports`). Fresh builds of this
  repo and the benchmark report 0, the seeded fixture its one. Test:
  `test_a_python_import_of_a_name_its_module_does_not_define_is_reported`.
- [x] **V-32 [LOW] Python gaps**: `Cls.method()` on an imported class, the
  same-name ambiguity skip, module-level double counting, a `TYPE_CHECKING`-only
  importer, star re-exports, `a.b.c.f()`, symtable edge cases, the tree-sitter
  path, conditional nested defs (PY 10–16). Fix, first pass: a def under
  `if`/`try`/`with`/`for`/`match` inside a function is its nested function
  (`_walk_body`); `User.create()` and `models.User.create()` bind to the
  method, `pkg.sub.func()` to the submodule's function
  (`_python_class_method`); a facade follows `from .core import *` — this repo
  +21 cross-file calls on their real node, +12 functions found (version 42).
  Second pass: a call inside a def or class under a module-level `if` / `try`
  is no longer also the module's (`_walk_body(module_level=True)`): this repo
  went from 3,109 to 2,904 module-sourced calls, every other call unchanged; the
  undefined-name report moved to `_undefined_python.py` and knows `__module__`
  / `__qualname__` and a walrus in a module-level comprehension, reads names
  inside string annotations (never `Literal[...]` or `Annotated` metadata), and
  checks an annotation against the scopes that enclose it instead of a binding
  anywhere in the file — identical output on 1,338 real files, so no new false
  positive; the opt-in tree-sitter import path keeps the `ast` imports and only
  tags them, so a `TYPE_CHECKING` import stays `imports_type` and a
  `try`/`except` fallback no longer replaces the real binding (version 56).
  Checked and already right: a `TYPE_CHECKING` import is `imports_type` and its
  importer links to the module. By design: two same-named candidates stay
  unbound rather than guessed. Tests: `test_python_scope_edges.py`,
  `test_a_function_defined_under_if_try_or_with_inside_a_function_is_its_nested_function`,
  `test_a_method_called_on_an_imported_class_binds_either_way_it_is_spelled`,
  `test_a_star_re_export_and_a_submodule_member_bind_to_the_real_function`.
- [x] **V-33 [LOW] Python newer than the host interpreter loses the whole
  file** (EX 10). Fix: on a SyntaxError the file is read by tree-sitter
  (`_python_fallback.py`): its functions, classes, methods and imports, named
  as the `ast` path names them and sent through the same emitters, under a
  module marked `recovered`; the syntax error stays reported. Calls and
  annotations still need `ast`. Extraction version 43. Test:
  `test_a_file_this_interpreter_cannot_parse_keeps_its_declarations_and_imports`.

### TypeScript, JavaScript and React Native

- [x] **V-34 [HIGH] Methods of class expressions (mixins) are not nodes** (TS 3;
  149 production methods). Fix: a class expression is named by what holds it
  (`ts_class_name`): `const Store = class {}` is the class `Store` (no second
  `Store` variable to make imports ambiguous), and the anonymous class a mixin
  returns is `withAccountApi.class`, a label apart from the function's. Its
  methods are nodes and `this.m()` inside it reaches the sibling method.
  Benchmark: 149 of 149 such methods (0 before). Extraction version 28. Test:
  `test_class_expressions_and_mixins_keep_their_methods`.
- [x] **V-35 [MEDIUM] `X.m()` on a named or default import keys `<module>:m`,
  and `this.svc.m()` binds to the class's own `m`** (TS 5, EX 2). Fix:
  `_ts_callee` keeps a member chain whole (it collapsed `this.svc.save` to
  `this.save`), `this.m()` binds to an own method only with one dot, and a
  member call keys `<module>:X.m` unless `X` is a namespace import
  (`ts_member_tail`) — JSX tags and the Astro template follow the same rule.
  The benchmark holds no such call (own-method bindings 8 before and after).
  Extraction version 34. Test:
  `test_a_member_chain_keeps_its_middle_and_only_a_namespace_import_names_an_export`.
- [x] **V-36 [MEDIUM] Names bound by `const { X } = await import('./X')` never
  bind** (TS 7). Fix: the binding pattern `require` used also takes
  `(await) import('…')`, so each destructured name (and `{ default: Foo }`, and
  a whole-module `const lib = await import(…)` as a namespace) is an import node
  marked `dynamic` that the linker binds. Benchmark: 79 of 79 such names (0
  before). Extraction version 38. Test:
  `test_names_bound_by_a_dynamic_import_bind_like_an_import`.
- [x] **V-37 [MEDIUM] Resolver gaps**: tsconfig `references`, `exports`
  conditions that point at unbuilt files, `**` workspaces reaching nested
  `node_modules`, `${configDir}`, `.js` → `.d.ts`, a workspace `extends`,
  `#` imports (TS 8, EX 9). Fix (`resolve_ts.py`): a solution tsconfig hands
  a file to the `references` project whose `include` / `files` holds it (the
  Vite template keeps `paths` in `tsconfig.app.json`); every `exports` /
  `imports` condition is tried in order, so an unbuilt `dist` falls through to
  `src`; a workspace glob skips `node_modules` and honours `!` negations;
  `./x.js` also finds `x.d.ts` (`.mjs` → `.d.mts`, `.cjs` → `.d.cts`); an
  `extends` naming a workspace package reads its preset; `${configDir}` means
  the extending project; `#x` resolves through the nearest package.json
  `imports`. A `baseUrl` reaching the repo root no longer falls back to the
  `paths` folder. The auditor's 10 resolution probes: 3 → 10 right. The
  benchmark uses none of these layouts: 7,377 in-repo TS/JS imports either way
  (the 121 unbound are icon assets). Extraction version 50. Tests:
  `test_resolve_ts.py::TestProjectLayouts`.
- [x] **V-38 [MEDIUM] `not_exported`/`undefined`: barrels are never checked,
  CommonJS exports are false positives, ambient declarations count as
  undefined** (TS 9). Fix: `_may_define` follows a barrel's re-exports (and a
  re-exported import of the name) instead of trusting any barrel, and trusts a
  module marked `commonjs` (`module.exports`, `exports.x =`); a `.d.ts` file's
  `declare function` / `declare const` / `declare global { … }` names are now
  nodes (`emit_ambient`), and a TS name one of them declares is not
  undefined. The type-checked benchmark reports 0 before and after; the
  fixture pins all three. Extraction version 44. Test:
  `test_ts_checks_names_through_barrels_and_trusts_commonjs_and_ambient_declarations`.
- [x] **V-39 [LOW] TS gaps**: renamed re-exports, two `export *` sources,
  namespace JSX, a comment stripper blind to strings, platform twins, cycles
  through `re_exports`, `import type x = require()` (TS 10–14). Fix: a barrel
  keeps the names it re-exports — `reexported_as` on its module node, from
  `export { a as b } from` and `import { a } …; export { a as b }` — and the
  linker follows `b` to `a` (`_ts_reexports.py`, `_sqlite_links_ts.py`); the
  export-clause pass read `{ a as b }` the import way round and missed a renamed
  local. `export type …` re-exports carry `ts_type_reexport`, and
  `cos_graph_cycles` now walks `re_exports` beside `imports`, minus those, so a
  component importing its own barrel shows as the cycle it is. `import type x
  = require()` is `imports_type`. The import scan skips strings whole, so
  `'src/*'` no longer opens a comment that blanks the next imports. An import
  reaching `Map.ios.tsx` also links `Map.android.tsx`, and `./Pay` reaching
  `Pay.tsx` links `Pay.web.tsx` (`platform_twins`, one cached folder listing).
  Checked and already right: two `export *` sources and namespace JSX
  (`<UI.Button />`). The auditor's probes: cycle 0 → 1, twins 2 of 4 → 4 of 4,
  type forms 10 of 10. The benchmark has no renamed re-export, platform twin or
  barrel cycle: bindings unchanged, 14 barrels now carry `reexported_as`.
  `resolve_ts.py` reached 496 lines; its file probing moved to
  `_resolve_ts_files.py`. Extraction version 53. Tests: `test_ts_reexports.py`,
  `test_a_comment_marker_inside_a_string_hides_no_import`.

### Astro and MDX

- [x] **V-40 [HIGH] The Astro template is invisible**: 153 component tags and
  35 calls make no edge (AS 2). Fix: `_astro_template.py` reads the template
  (frontmatter, scripts, styles and comments blanked, so lines stay the file's
  own) with the frontmatter's bindings: a capitalised tag renders
  (`constructs`), `fn()` / `ns.fn()` inside `{…}` calls; a name the
  frontmatter neither imports nor declares (`Astro.props`, a global) and a
  longer chain over imported data (`press.items.map()`) make no edge. Benchmark
  (66 files): 155 of 155 imported component tags render, 42 template calls (0
  before). Extraction version 29. Test: `test_astro_template.py`.
- [x] **V-41 [MEDIUM] MDX imports and site-absolute MDX links are dropped** (AS 3, 12).
  Fix: a `/route` link resolves under the site root (the folder holding
  `astro.config.*`) to the page or content entry serving it (`_site_route`),
  and an `.mdx` page's ESM imports become `imports` edges, its component tags
  `constructs` (`_md_mdx.py`). Benchmark: 324 of 324 site-absolute links (0
  before) and both MDX imports. Extraction version 39. Test:
  `test_mdx_site_absolute_links_reach_the_page_or_entry_and_its_imports_are_edges`.
- [x] **V-42 [MEDIUM] `astro:*` virtual modules do not roll up into astro's
  fan-in** (AS 4; 5 of 31 files). Fix: a package's roll-up also takes its
  `name:*` virtual modules (`astro:content`, `astro:assets`), symbols excluded
  as for sub-paths. Benchmark: astro's fan-in 5 → 31, the source scan's count.
  Test: `test_astro_virtual_modules_count_toward_astros_fan_in`.
- [x] **V-43 [MEDIUM] An arrow function wrapped in `satisfies`/`as` is no
  function node** (AS 5). Fix: `ts_unwrap` looks through `(…)`, `as` and
  `satisfies` to the value, and the scope chain looks up through them to the
  declarator, so `GET = (async () => {…}) satisfies APIRoute` is the function
  `GET` and a function inside it is `GET.inner`. Benchmark: 9 of 9 such
  functions (0 before). Extraction version 31. Test:
  `test_an_arrow_function_wrapped_in_satisfies_or_as_is_a_function`.
- [x] **V-44 [LOW] Astro scripts**: `<script src>` imports, unprocessed
  scripts read as modules, frontmatter and script scopes sharing uids (AS 9–11).
  Fix: a script is read only when Astro processes it — no attribute but `src`,
  per Astro's docs — so `is:inline`, `type="module"` and `data-*` scripts are
  left to the browser; `<script src="./x.ts">` imports x.ts
  (`_astro_split.astro_scripts`). Each processed script is its own scope
  (`_astro_scope.py`): its symbols take a `script.` qualname, an edge from inside
  it reaches its own symbol, and the frontmatter and template never reach a name
  only a script declares — the duplicate `::en` / `::label` uids are gone. Found
  on the way: the closing fence is the first `---` outside a frontmatter string
  or comment, a byte-order mark before the opening fence and CRLF fences no
  longer hide the frontmatter, and a call written in a template comment or
  string (`{/* render() … */}`) is no call. Benchmark (66 components): 17 script
  symbols take their own scope, 351 imports and 402 symbols unchanged, 4 calls
  gone — 3 from an `is:inline` script, 1 from a template comment. The
  auditor's 5 masking probes all right. Extraction version 52. Tests:
  `test_astro_scripts.py`,
  `test_a_call_written_in_a_template_comment_or_string_is_not_a_call`.

### Shell and the reindex hooks

- [x] **V-45 [HIGH] The reindex hook takes `$PWD` as the project root** (SH 2).
  Fix: `COS_PROJECT_ROOT`, then `CLAUDE_PROJECT_DIR`, then the directory above
  the `COS_STATE_DIR` cos-env walked to; `$PWD` last. Test:
  `test_the_hook_finds_the_project_root_when_run_from_a_subdirectory`.
- [x] **V-46 [MEDIUM] Without tree-sitter or on an old Python the worker
  degrades silently, and the log says `ok` for a failed graph layer** (SH 4–5).
  Fix: the worker refuses Python below 3.10, and the graph layer without
  tree-sitter, with an error line; the log prints the layer's own status and
  reason. Test: `test_a_worker_without_the_parsers_leaves_the_graph_and_logs_why`.
- [x] **V-47 [MEDIUM] `dead_code` and `test_gap` skip every `.sh` file** (SH 6).
  Fix: shell has a call graph now, so `dead_code` reads `.sh` functions; a
  function handed over by name — `trap cleanup EXIT`, `trap 'on_err' ERR`,
  `export -f greet` — gets a `dispatches` edge so it is not reported dead.
  `test_gap` keeps shell out on purpose: a test runs a script as a process,
  which no edge records, so every shell function would read untested.
  Extraction version 32. Test:
  `test_dead_code_reads_shell_functions_and_spares_trap_and_exported_ones`.
- [x] **V-48 [LOW] Shell gaps**: script-dir variable idioms, missed run forms,
  name-only binding, `command -v` counted as a call, small hook items (SH 7–10).
  Fix (`_shell_paths.py`): `cd -- … &>/dev/null && pwd`, `$(cd "$(dirname
  "$0")/.." && pwd)`, `readlink -f` / `realpath` around `$0`, backticks and a
  `${DIR:-…}` default now expand to the script folder, and a variable assigned
  more than once keeps every static value, each reading tried (the auditor's
  19 source idioms: 12 → 19). `_shell_commands.py`: a runner's value flags
  (`python -W x`, `node --require x`) and inline-code flags (`-c`, `-e`) are
  read, `uv run x.py`, `bun run`, `deno run`, `pnpm tsx`, `npm exec` reach the
  script, `sudo` / `xargs` / `timeout 5s` are wrappers, and an extensionless
  file with a shell shebang runs by path or shell (17 run forms: 5 → 17);
  `$COPY_CMD` is no Python interpreter any more; `command -v NAME` is a lookup,
  not a call; shell keywords a parse error leaves as words mint no stub. This
  repo: 50 → 59 run edges, all 9 real (`cd …/../..` roots, a reassigned root,
  a `${HELPER:-…}` default), stub calls 1,148 → 1,123. Checked and kept:
  binding a library function by name — 303 of 322 cross-file calls go to a
  file the caller sources, and the other 19 are siblings one aggregator
  (`cos-env.sh`) sources together, so the call is real. The hook items: an
  edit from a subdirectory cwd reindexes; without `cos` on PATH the hook logs
  that the found Python is too old; with no `cos-env.sh` beside them the two
  reindex hooks exited 127 against their fail-open contract and now exit 0
  (the same `source … || true` line opens 96 hooks — a kernel-wide question,
  not a graph one). Extraction version 51. Tests: `test_shell_forms.py`,
  `test_a_hook_whose_env_is_missing_exits_cleanly_and_indexes_nothing`.
- [x] **V-49 [LOW] Shell has no undefined-name report** (SH Q6). Fix:
  `cos_graph_undefined` reports a shell call no sourced library answered when
  its name belongs to a `prefix_` family the repo's own functions use (`log_`,
  `cos_`) and no command on PATH carries it — any command looks like a call,
  so a name outside those families (`jq`, `systemctl`) is never guessed
  missing. Both repos run cleanly and report 0; without the family rule 4
  commands absent from macOS would read as missing. Test:
  `test_a_shell_call_to_a_function_its_libraries_lost_is_reported`.

### Duplicates, walk and manifests

- [x] **V-50 [MEDIUM] The clone fingerprint ignores literal keys and values,
  so same-shaped data tables match; only whole symbols are compared**
  (CO D8, EX 6). Partly done: a data declaration — a variable, a TS enum —
  keeps its literals in the structure hash, as PMD CPD compares literals unless
  `--ignore-literals` is set, so two tables of one shape (locale files, a dark
  and a light palette, two unrelated maps of one length) are no clone, while a
  table copied under a new name still is; code keeps Type-2 matching.
  Benchmark: duplicated lines 22,628 → 1,174, the 11-file locale group and a
  gradient pair gone, the 76 code groups unchanged. This repo: 7 of 35 renamed
  groups were data tables, all 7 gone. Extraction version 49. Test:
  `test_a_data_table_is_a_clone_only_of_the_same_contents`. Second half:
  `cos_graph_duplicates(fragments=true)` (CLI `--fragments`) finds a block
  copied into otherwise different code (`_graph_fragments.py`). At query time it
  turns each indexed code file into a token stream (comments, layout and import
  statements dropped, strings kept, so a match is an exact copy), keeps the
  winnowed minimum of every 26 consecutive 25-token window hashes (Schleimer,
  Wilkerson and Aiken, 2003; any shared run of 50 tokens keeps a hash), and grows
  each shared hash into the longest common run. A run of 50 tokens or more is
  listed unless a symbol clone group or an identical file already covers every
  copy, or a wider run already reported overlaps each of its copies. This repo:
  166 fragment groups in 1.7 s; the benchmark: 210 in 1.8 s (for example one
  block three times in a Go handler file). Off by default, so the plain call
  stays as fast as before. Test:
  `test_a_block_copied_inside_two_different_functions_is_a_fragment_clone`.
- [x] **V-51 [LOW] The walk collects every dotted file regardless of the
  include list, and drops tracked `build`/`dist`/`target`/`vendor` source
  directories** (CO D10–D11). Fix: the shebang exception for an extensionless
  script had its condition inverted, letting every dotted file through; now a
  file outside the include list is walked only when it is a dotless shell
  script. A `dist`, `build` or `target` folder is pruned only when git tracks
  nothing in it (`ingest/_tracked.py`, one `git ls-files` per such folder,
  after the cheaper name and `.gitignore` checks); the single-file reindex and
  the go.mod unindexed-package check apply the same rule. By design `vendor`
  stays out even when committed — it holds third-party copies. This repo: 3,567
  → 3,476 walked files (91 css, svg, txt, templates… that no extractor reads),
  the benchmark 2,248 → 2,243, same walk time. Tests:
  `test_a_file_outside_the_include_list_is_not_walked`,
  `test_a_build_named_folder_git_tracks_is_source_and_an_untracked_one_is_not`.
- [x] **V-52 [MEDIUM] Undeclared and unused npm and Python dependencies are
  not reported** (EX 7). Fix: `cos_graph_undefined` reports
  `undeclared_dependency` — a JS/TS import no nearest/root package.json nor
  workspace declares (built-ins, `node:`, aliases and `virtual:` skipped), a
  Python import that is neither stdlib, repo nor a declared distribution — and
  `unused_dependency` for runtime npm `dependencies` nothing under the manifest
  imports, counting imports resolved into a workspace package's folder
  (`_graph_undefined_deps.py`). Python is never called unused: the
  distribution→import guess and plugins/CLIs make it unreliable. Benchmark: 25
  npm phantom dependencies (transitive Expo packages), 17 Python imports in a
  script folder no manifest covers, 13 unused candidates — 11 named nowhere in
  their package, 2 Expo config plugins used only by name in app.json. This
  repo: `starlette` (arrives through fastapi), four UI packages never
  imported, the optional `anthropic`/`jedi`/`tomli` imports, and scaffold
  manifests with no code. Test:
  `test_undeclared_and_unused_npm_and_python_dependencies_are_reported`.

## Review of the fixes

An independent read-only reviewer went over the commits for V-23 to V-50 and
reproduced 9 defects against the tree before them, plus 2 slowdowns. Each fix
below has a test unless marked as a cost fix.

- [x] **R-01** A Go package's import name was read from its alphabetically
  first file, a `//go:build ignore` generator included, so `lib.Hello()` lost its
  edge. Fix: the clause most of the built files share (`resolve_go`). Test:
  `test_a_generator_file_and_a_later_local_neither_hide_the_real_callee`.
- [x] **R-02** A `#` specifier skipped tsconfig `paths`. Fix: `paths` first,
  then package.json `imports`, as TypeScript does. Test:
  `test_tsconfig_paths_come_before_package_imports_for_a_hash_specifier`.
- [x] **R-03** A `references` project took files its parent config includes,
  and a glob include (`*.config.ts`) covered its whole folder. Fix: the including
  config keeps the file; include globs match `**`, `*` and `?` per segment. Test:
  `test_the_config_that_includes_the_file_keeps_it_over_a_reference`.
- [x] **R-04** Go shadowing was decided for the whole function, so `client :=
  client()` lost its call. Fix: each local is in scope from the end of its
  statement to the end of its block (`_go_scopes.py`). Test: as R-01.
- [x] **R-05** `any` / `interface{}`, `byte` / `uint8` and `rune` / `int32`
  compared unequal in `implements`. Fix: the signature key normalises them.
  Test: `test_builtin_type_aliases_are_the_same_type`.
- [x] **R-06** `import type { A } …; export { A }` counted as a runtime cycle,
  and a platform twin's copy of a type-only re-export lost its signal. Fix: the
  import's own type-only flag carries over, and twin evidence is appended. Test:
  `test_a_cycle_through_a_barrel_is_found`.
- [x] **R-07** A shell function two libraries define read as missing. Fix: a
  name any repo shell function defines is ambiguous, not undefined. Test:
  `test_a_shell_function_two_libraries_define_is_ambiguous_not_missing`.
- [x] **R-08** (cost) `go.mod` was re-read and re-scanned for every import
  (about 14× per import on a large `go.mod`). Fix: an mtime cache.
- [x] **R-09** (cost) The global Go link queried once per unbound stub for
  build-tag twins. Fix: only where the symbol index holds two or more.
- [x] **R-10** An apostrophe in JSX text inside an Astro expression (`Don't miss
  {fmt(i)}`) hid the call. Fix: only `/* … */` comments are blanked. Test:
  `test_a_call_in_a_template_comment_is_none_and_jsx_text_apostrophes_hide_no_call`.
- [x] **R-11** A prose string annotation (`name: "username"`) read as an
  undefined name. Fix: only capitalised names in a string annotation are
  checked. Test:
  `test_a_name_only_a_string_annotation_or_a_shadowed_annotation_uses_is_reported`.
- [x] **R-12** Minor: the tracked-folder cache ignored a worktree's `.git` file,
  the referenced-config cache ignored the referenced file's edits, and the
  include match was case-sensitive. All three fixed; the last has a test.

## Write path under load

- [x] **W-01** On a loaded machine a fresh `cos graph-reindex -j 4` could grow
  the WAL to gigabytes (9.5 GB seen once). The WAL held 251,677 frames over
  only 2,588 pages: every node and edge upsert committed on its own, so each
  file rewrote the same index pages dozens of times. Four workers always kept a
  reader open, so SQLite's passive checkpoint could not reset the file. Fix:
  `bulk_upsert` writes one transaction, and the parallel CLI runs `PRAGMA
  wal_checkpoint(TRUNCATE)` every 100 files. A normal benchmark build went from
  45 s to 25 s, with the WAL peaking at 7 MB and identical link results. Under
  load, after W-02 and TASK-1052: a fresh `-j 4` build of the benchmark, with two
  readers keeping a read transaction open at every moment and a load average of
  9 to 24 on 11 cores, took 63 s; the WAL peaked at 80.6 MB and ended at 6.4 MB,
  and no checkpoint was blocked. Every process ran in its own group behind a
  1.5 GB WAL cap and a memory floor, and none was left behind.
- [x] **W-02** The W-01 checkpoint waited up to 30 s for readers and ignored
  the first column of the pragma's result, which is 1 when a reader blocked
  it. Per [sqlite.org/pragma.html](https://sqlite.org/pragma.html#pragma_wal_checkpoint),
  TRUNCATE "blocks concurrent writers while it is running", so a starved
  checkpoint could hold every worker's write for the whole wait, and nobody
  would hear about it. [sqlite.org/wal.html](https://sqlite.org/wal.html)
  names the cause ("if there is always at least one active reader … the WAL
  file will grow without bound") and the remedy (manual RESTART or TRUNCATE
  checkpoints in the reader gaps). Fix: the checkpoint gives up after 3 s, as
  `wal_guard` already does, prints a `[WARN]` with the frames it kept when
  blocked, and the next call 100 files later retries.


## Second review

A second read-only reviewer went over the review fixes, the fragment pass, the
batched upsert and the WAL checkpoint (TASK-1053), on hand-made fixtures only.
It found the batching, `_winnow`, `_glob`, the include cache and the Go spans
for `if`/`for`/`range`/closures clean, and reported these:

- [x] **F-01** The script import blanker in `_graph_fragments` ran from any
  `export` to the first quote, across lines, so semicolon-free TypeScript lost
  whole exported functions before the clone search saw them. Fix: only a
  statement naming a module is blanked. Test:
  `test_an_exported_function_without_semicolons_keeps_its_body`.
- [x] **F-02** The same pattern rescanned to end of file for every `export`
  line without a quote: 4,000 such lines took 5.9 s, now 0.018 s. Test:
  `test_export_lines_without_a_quote_are_read_in_linear_time`.
- [x] **F-03** `fragments=true` read every indexed code file whatever the
  `scope`, with no bound on the token count held in memory. Fix: a scope's
  files are read first and an outside file is kept only if it shares a hash
  with them; tokens are interned (31 bytes a token, was 109); reading stops at
  5M tokens with `meta.fragments_truncated`. Test:
  `test_a_focus_keeps_only_copies_that_touch_it_and_is_read_first`.
- [x] **F-04** The Astro expression scanner still opened a string at every
  apostrophe, so JSX text with an odd count (`Don't`) hid every later call.
  Fix: a small lexer tells code from JSX (a `<` after `(`, `=>`, `&&`, `?`,
  `return` …), and only code is scanned; JSX text and its apostrophes are not.
  Version 58. Test: `test_strings_comments_and_jsx_text_in_a_template_hold_no_call`.
- [x] **F-05** A value re-export and a type-only re-export of one module share
  an edge key; the type-only one was written last and won, hiding a real cycle.
  Fix: one edge per module, and the value re-export wins. Test:
  `test_a_cycle_through_a_barrel_is_found` (the `mix/` pair).
- [x] **F-06** An `include` that climbs out of the config's folder
  (`../../packages/shared/src`) never matched, a regression on R-03. Fix: the
  file is matched by its path relative to the config, and only an entry that
  itself starts with `../` reaches outside, so `**` still never does. Test:
  `test_an_include_that_climbs_out_of_its_folder_owns_the_shared_package`.
- [x] **F-07** The capital-letter filter for string annotations also dropped
  dotted names (`"np.ndarray"`) whose module is never imported. Fix: the filter
  applies to a bare name only. Test:
  `test_a_name_only_a_string_annotation_or_a_shadowed_annotation_uses_is_reported`.
- [x] **F-08** Strings and `//` comments inside an Astro expression were no
  longer blanked, so `{'render() as text'}` made a call edge. Fix: the same
  lexer blanks them in code. Test: as F-04.
- [x] **F-09** A block copied three times in a row listed only the outer two
  copies. Fix: a run that overlaps itself is cut into its copies. Test:
  `test_a_block_repeated_back_to_back_lists_every_copy`.
- [x] **F-10** With `clone_type="renamed"` the exact clone groups were left out
  of the fragment coverage, so whole-function exact clones came back as fragments.
  Fix: coverage reads every group. Test:
  `test_a_clone_type_filter_still_counts_every_group_as_reported`.
- [x] **F-11** Go scoping: `case v := <-ch:` bound nothing, a type switch alias
  shadowed its own header (`switch c := c().(type)`), and a parameter of a
  local interface's method shadowed across the function. Fix: a receive, range
  or short declaration binds only with `:=`, the alias is in scope from the end
  of the switched value, and an interface method's parameters bind nothing.
  Version 58. Test: `test_select_receives_switch_headers_and_interface_methods_scope_like_go`.
- [x] **F-12** Only the parallel reindex loop checkpointed the WAL; the serial
  path and the link pass after it never did, so a Hub or MCP reader could starve
  them too. Fix: the serial walk checkpoints every 100 files and the link pass
  once when it ends. Test:
  `test_a_serial_reindex_checkpoints_while_walking_and_after_linking`.

## Third review

A third read-only reviewer went over the second review's fixes and the governance
edits (TASK-1059). It found the lexer safe (no endless loop, linear time), the
fragment split, focus and cap correct, and the Go `:=` scoping right, and
reported these:

- [x] **T-01** `run_server` passed its host only to uvicorn while the bind guard
  read `COS_WEB_HOST`, so `cos board --web --bind 0.0.0.0` opened every
  interface with no token. Fix: `run_server` guards the host it binds and exports
  it. Test: `test_run_server_guards_the_host_it_binds_not_the_env`; the real
  command now exits 1 with the remedy.
- [x] **T-02** The Astro lexer skipped a template literal whole, so
  ``href={`/blog/${slug(x)}`}`` lost its `slug` call. Fix: a template-literal
  mode in which only `${…}` is code. Version 59. Test:
  `test_template_literals_void_tags_odd_comments_and_regexes_keep_their_calls`.
- [x] **T-03** A void element written without `/>` (`<img>`, `<br>`) inside an
  expression opened JSX children that never closed, so later text was read as
  code and `Don't` hid the calls after it. Fix: void elements close at `>`, and
  a bare `}` in JSX text or a tag closes the expression it belongs to. Test: as
  T-02.
- [x] **T-04** `/*/` closed its own comment, and a regex literal holding a quote
  (`/"/g`) opened a string that ran to the end of the template. Fix: the end of
  a comment is searched after its opener, and a `/` where an operand starts
  reads a regex. Test: as T-02.
- [x] **T-05** Lifting the capital-letter filter for every string annotation
  made prose and units (`"m/s"`, `"a or b"`) report undefined names; only the
  head of a dotted name should skip it. Fix: a lowercase name in a string
  annotation counts only as the head of a dotted name. Test:
  `test_a_name_only_a_string_annotation_or_a_shadowed_annotation_uses_is_reported`.
- [x] **T-06** `include` globs were not normalised against the config's folder,
  so `../web/src` in `apps/web/tsconfig.json` and `src/../../shared` matched
  nothing. Fix: each entry is resolved against the config's folder first. Test:
  `test_an_include_that_detours_through_dot_dot_is_read_against_its_folder`.
- [x] **T-07** The fragment focus test passed without the focus ordering. Fix:
  its cap now fits only the focus file and its copy, so it fails when the focus
  is not read first (checked by removing the ordering).
- [x] **T-08** The blocked-checkpoint warning promised a retry 100 files later,
  which the post-link checkpoint never makes. Fix: it now says to close
  long-lived readers if the WAL keeps growing.
- [ ] **T-09** RISK-004 named `test_background` as nightly-only, but the
  thinking_os step runs it on every PR, and `test_template_scaffold` is now four
  files.
- [x] **T-10** KNOWN_LIMITATIONS claimed the Hub refuses any off-loopback bind;
  fixed with T-01, and the text now names the `uvicorn --host` route that
  bypasses `run_server`.
