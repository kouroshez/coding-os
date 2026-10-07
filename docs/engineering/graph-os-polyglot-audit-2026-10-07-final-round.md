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
- [ ] **V-04 [MEDIUM] `upsert_node` reads and writes outside one transaction**;
  under `-j N` a stub overwrites a real node (CO D6, TS 4; 2 benchmark modules).
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
- [ ] **V-10 [MEDIUM] Fiber routes on struct-field routers, `RouteChain`,
  `Add`, `Domain` and inline `Group(...)` receivers are missing** (GO 6, EX 11).
- [ ] **V-11 [MEDIUM] FastAPI: a non-literal prefix is dropped unmarked,
  sub-project mounts never resolve, `app.mount` is ignored, a router included
  twice keeps one mount, an annotated router assignment is missed** (PY 4, EX 3).
- [ ] **V-12 [MEDIUM] A route handler nested in a factory, a method or an
  imported endpoint points at a phantom node** (PY 5).
- [ ] **V-13 [MEDIUM] File-route paths and forms**: `_` directories, `[a]-[b]`,
  `[id].json`, `.md`/`.mdx`/`.html` pages, `export { x as GET }`, an Expo
  `export { default } from`, `const X; export default X`, TanStack
  `createRoute` (AS 6–8, TS 12, EX 12).

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
- [ ] **V-19 [MEDIUM] tsconfig `extends` edges are not normalised, read a
  package preset as a path, and ignore the array form** (CO D7).

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
- [ ] **V-23 [MEDIUM] go.work `use .`, a `replace` without go.work and an
  in-repo sibling module mis-resolve or report a false unused require**
  (GO 8–10, EX 8).
- [ ] **V-24 [MEDIUM] A Go call into a package never imported is not reported**
  (GO 11).
- [ ] **V-25 [LOW] `implements` precision**: signatures not compared, embedded
  conflicts, methods hung by directory and name onto test fakes, embedded
  `error`, `type Runner Base` (GO 12, EX 5).
- [ ] **V-26 [LOW] Go resolution gaps**: handler on a parameter or local, a
  parameter shadowing a file function, package name ≠ directory, explicit
  generic calls, several `init()`, a deprecated `module` line, build-tag twins
  (GO 13–14, EX 8).

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
- [ ] **V-32 [LOW] Python gaps**: `Cls.method()` on an imported class, the
  same-name ambiguity skip, module-level double counting, a `TYPE_CHECKING`-only
  importer, star re-exports, `a.b.c.f()`, symtable edge cases, the tree-sitter
  path, conditional nested defs (PY 10–16).
- [ ] **V-33 [LOW] Python newer than the host interpreter loses the whole
  file** (EX 10).

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
- [ ] **V-36 [MEDIUM] Names bound by `const { X } = await import('./X')` never
  bind** (TS 7).
- [ ] **V-37 [MEDIUM] Resolver gaps**: tsconfig `references`, `exports`
  conditions that point at unbuilt files, `**` workspaces reaching nested
  `node_modules`, `${configDir}`, `.js` → `.d.ts`, a workspace `extends`,
  `#` imports (TS 8, EX 9).
- [ ] **V-38 [MEDIUM] `not_exported`/`undefined`: barrels are never checked,
  CommonJS exports are false positives, ambient declarations count as
  undefined** (TS 9).
- [ ] **V-39 [LOW] TS gaps**: renamed re-exports, two `export *` sources,
  namespace JSX, a comment stripper blind to strings, platform twins, cycles
  through `re_exports`, `import type x = require()` (TS 10–14).

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
- [ ] **V-41 [MEDIUM] MDX imports and site-absolute MDX links are dropped** (AS 3, 12).
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
- [ ] **V-44 [LOW] Astro scripts**: `<script src>` imports, unprocessed
  scripts read as modules, frontmatter and script scopes sharing uids (AS 9–11).

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
- [ ] **V-48 [LOW] Shell gaps**: script-dir variable idioms, missed run forms,
  name-only binding, `command -v` counted as a call, small hook items (SH 7–10).
- [ ] **V-49 [LOW] Shell has no undefined-name report** (SH Q6).

### Duplicates, walk and manifests

- [ ] **V-50 [MEDIUM] The clone fingerprint ignores literal keys and values,
  so same-shaped data tables match; only whole symbols are compared**
  (CO D8, EX 6).
- [ ] **V-51 [LOW] The walk collects every dotted file regardless of the
  include list, and drops tracked `build`/`dist`/`target`/`vendor` source
  directories** (CO D10–D11).
- [ ] **V-52 [MEDIUM] Undeclared and unused npm and Python dependencies are
  not reported** (EX 7).
