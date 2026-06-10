---
id: TASK-313
title: "Polyglot quality to 9: edge hooks for 7 langs + measured benchmark (coverage/precision/speed/memory)"
swimlane: core
kind: feature
epic: graph-coverage-hardening
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-10
started: 2026-06-09
completed: 2026-06-09
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-313: Polyglot quality to 9: edge hooks for 7 langs + measured benchmark (coverage/precision/speed/memory)

**Outcome (one sentence):** The 7 generic languages (java/c/cpp/c#/scala/kotlin/lua) sit at completeness 5 (node+contains only) and all sub-9 scores rest on judgment, not measurement; add calls/imports/inherits edge hooks for all 7 and build a real quality benchmark (ground-truth corpora × scenarios measuring coverage/precision/speed/memory/confidence calibration) so every language's score ≥9 is backed by measured data.

## Read First
- src/core/graph_os/extractors/code_generic.py
- src/core/graph_os/tests/test_code_generic.py
- docs/playbooks/polyglot-extractor-roadmap.md

## Plan (verified against real grammars, not guessed)

### Part A — edge hooks (one shared table-driven walker, NOT 7 copies)
Per-language node types probed live against the installed grammars:
- **java**: imports=`import_declaration`(scoped_identifier) · calls=`method_invocation`(name+object fields; object⇒dynamic 0.3) · inherits=`superclass`(type_identifier) · implements=`super_interfaces`(type_list, comma-split)
- **c**: imports=`preproc_include`(path field, strip <>/"") · calls=`call_expression`(function field: identifier⇒0.9/0.5, field_expression⇒0.3)
- **cpp**: c + inherits=`base_class_clause`(type_identifier children)
- **c_sharp**: imports=`using_directive` · calls=`invocation_expression`(function: identifier / member_access_expression.name) · inherits=`base_list`(identifiers; class-vs-interface not statically distinguishable ⇒ conf 0.9, honest)
- **scala**: imports=`import_declaration`(path fields joined) · calls=`call_expression`(function field) · inherits=`extends_clause`(first type ⇒ inherits, `with` types ⇒ includes)
- **kotlin**: imports=`import`(qualified_identifier) · calls=`call_expression`(no fields; child[0]=identifier/navigation_expression) · inherits=`delegation_specifier`(constructor_invocation⇒inherits, user_type⇒implements)
- **lua**: imports=`function_call` name=='require'(string arg) · calls=`function_call`(name field: identifier/dot_index_expression)

Confidence tiers (graph-os-authoring §3, same as rust/ruby): 0.9 same-file AST-resolved · 0.5 cross-file linkable stub (code:external:) · 0.3 dynamic dispatch (code:external:unresolved:). All targets stubbed via _promote_stubs ⇒ zero dangling edges.

### Part B — quality benchmark (real measurements, not judgment)
New `src/core/graph_os/tests/test_polyglot_quality.py` + bench script. Ground-truth corpora per language × 3 scenarios (personas):
1. **simple** (junior dev file): flat functions + one class + imports.
2. **nested** (library author): nested classes/modules, methods-in-class, inheritance chains.
3. **real-world** (enterprise service file): mixed imports + cross-file calls + dynamic dispatch + inheritance + decoy code inside comments/strings.

Metrics per language (the goal's axes):
- **coverage** = symbol recall (ground-truth symbols all extracted) and edge recall (expected edges found)
- **accuracy/trust** = precision (no phantom symbols; decoys in comments/strings NOT extracted) + confidence calibration (0.9+ edges must all be true)
- **speed** = median ms/file over N runs
- **resources** = peak tracemalloc KB per extract
- **algorithm** = tree-sitter AST on all 7 (documented; no regex guessing)

Thresholds asserted in tests: symbol recall ≥ 0.9 · precision ≥ 0.95 · edge recall ≥ 0.8 · median ≤ 25 ms/file · peak ≤ 6 MB/file. A language that misses a threshold = red test = fix before close.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a source file in each of java/c/cpp/c#/scala/kotlin/lua with imports, same-file calls, cross-file/dynamic calls, and inheritance, **When** indexed, **Then** the graph has imports + tiered calls (0.9/0.5/0.3) + inherits/implements edges, proven per language by tests against the real installed grammars.
- **Given** the ground-truth corpora (3 scenarios × language incl. decoy code in comments/strings), **When** the quality benchmark runs, **Then** it reports measured symbol recall, edge recall, precision, median ms/file and peak-memory per language, asserting recall ≥ 0.9, precision ≥ 0.95, edge recall ≥ 0.8, speed ≤ 25 ms, memory ≤ 6 MB.
- **Then** the roadmap score table is regenerated from the measured numbers, graph_os matrix is green, and no shipped language scores below 9 on coverage/accuracy.

## Work Log
- 2026-06-10 [claude]: Probed all 7 grammars live; recorded exact node types + field structures in the plan above before writing any code.
- 2026-06-10 [claude]: Edge hooks shipped for java/c/cpp/c#/scala/kotlin/lua via one table-driven walker (probed node types, tiered 0.9/0.5/0.3
- 2026-06-10 [claude]: Edge hooks shipped for java/c/cpp/c#/scala/kotlin/lua via one table-driven walker (probed node types, tiered 0.9/0.5/0.3
- 2026-06-10 [claude]: committed 93a8594c: docs/playbooks/polyglot-extractor-roadmap.md, src/core/graph_os/extractors/code_generic.py, src/core
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
