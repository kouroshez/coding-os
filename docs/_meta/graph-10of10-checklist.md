# Graph → 10/10 — Execution Checklist (autonomous, self-executed)

Goal: close the genuine gaps to 10/10 without over-engineering. Each group: doc-first (inventory) → implement → unit test → matrix (`graph_os` pytest) → MCP self-test → live output check → commit (explicit paths). Extractor groups also: reindex + doctor verify. NO over-engineering — each item is a user-approved, bounded, enterprise capability.

Legend: `[ ]` todo · `[x]` done.

## Order: additive tools first (zero risk to existing graph), then extractor changes (reindex).

## GA — B1 cycle detection  (`cos_graph_cycles`)  [additive tool]
- [ ] New tool: circular dependency detection via strongly-connected-components over in-repo `calls`+`imports` edges (scope=imports|calls|all). Reports SCCs size≥2 (refactor-safety). networkx (already a graph_os dep).
- [ ] graph.py impl + server.py register + test + inventory(19).
- Verify: unit + `pytest graph_os` + self-test + live (find a real cycle or confirm acyclic).

## GB — B3 test-gap  (`cos_graph_test_gap`)  [additive tool]
- [ ] New tool: prod function/method/class with ZERO inbound edge from a TEST source (untested symbols). Inverse of dead_code's filter.
- [ ] graph.py impl + server.py register + test + inventory(20).
- Verify: unit + `pytest graph_os` + self-test + live count.

## GC — B2 revision diff  (`cos_graph_diff`)  [additive tool]
- [ ] New tool: `cos_graph_diff(base, head)` → `git diff --name-only base..head` → reuse `cos_graph_detect_changes` blast-radius (DRY). PR/review persona.
- [ ] graph.py impl + server.py register + test + inventory(21).
- Verify: unit + `pytest graph_os` + self-test + live (HEAD~1..HEAD).

## GD — O2 shell intra-call edges  (`extractors/code_shell.py`)  [extractor — reindex]
- [ ] Emit `calls` edges between bash functions (tree-sitter-bash command_name → local function). Closes the shell call-graph limp (dead_code + navigation).
- Verify: `pytest graph_os` (test_code_shell) + reindex + live (a .sh file shows calls).

## GE — O1 bounded self-method resolution  (`extractors/code_python.py` + `code_ts.py`)  [extractor — reindex]
- [ ] Resolve `self.method()` (py) / `this.method()` (ts) to the enclosing class's method uid (scope-aware, no LSP). Raises in-repo call resolution. Bounded — only same-class self/this receiver.
- Verify: `pytest graph_os` + reindex + resolution-rate before/after.

## FINAL
- [ ] `cos graph-reindex --force` + `cos_graph_doctor` clean.
- [ ] Full MCP tool review: every cos_graph_* returns valid envelope (self-test + spot live calls).
- [ ] `make verify-hooks` if any hook touched (none expected).
- [ ] Report: scores, per-tool outputs, before/after resolution.
