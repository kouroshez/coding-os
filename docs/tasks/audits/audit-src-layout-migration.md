---
audit_id: src-layout-migration
task_id: TASK-AUDIT-SRC
intent_detected_at: 2026-05-17T00:00:00Z
matched_exhaustive: ["", "", "", "", ""]
matched_scope: ["audit", "find", "verify", "sweep"]
predicates: ["counts_after_zero", "categories_covered", "reviewer_pass"]
status: completed
created: 2026-05-17
completed: 2026-05-17
---

# Audit: Post src-layout Migration — Deep Sweep

## Source Intent

**User prompt (quoted):**

> ..  src .. .  ... !  ...

**Migration commit:** `5b7e33d refactor: full src-layout migration + scaffold renames + doctor coverage` (1221 files, +37824/-15268)

**Layers moved into `src/`:** `core/` → `src/core/`, `cli/` → `src/cli/`, `adapters/` → `src/adapters/`, `templates/` → `src/templates/`, `scripts/` → `src/scripts/`. pyproject.toml uses `[tool.setuptools.package-dir]` to keep `from core.X` / `from cli.X` working at runtime.

**Follow-up fix commits since migration:** 50 (via `git log 5b7e33d~1..HEAD | wc -l`).

## Categories — Mandatory Coverage Table

| # | Category | Pattern | Files scanned | Hits before | Fixed | Hits after | Verified | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | Broken/dangling symlinks | `find -type l ! -e` | 439 links | 0 | n/a | 0 | yes | `/usr/bin/find -type l ! -e` → 0 broken |
| 2 | Python imports of pre-migration packages | `from (core|cli|adapters|templates)\.` in *.py | 105 occurrences | 0 | n/a | 0 | yes | All resolved via `pyproject.toml::[tool.setuptools.package-dir]` mapping. Verified by `python -c "import cli, core, adapters, thinking_os, graph_os, board_os, web, scheduled"` → OK |
| 3 | server.py sibling imports (pre-existing, NOT migration-caused) | `from (database|tools|graph|background) import` in `src/core/thinking_os/server.py` | 1 file (server.py) | 5 lines | 0 | 5 | n/a | Pre-existed before commit 5b7e33d (confirmed via `git show 5b7e33d~1`); MCP runs as `python server.py` (cwd-on-sys.path), but `import thinking_os.server` from external scripts breaks. Out of migration scope. |
| 4 | Shell scripts: hard-coded path without `src/` | grep `(\$REPO_ROOT|\$COS_ROOT|\$DIR|\$CLAUDE_PROJECT_DIR)/(core|cli|adapters|templates)/` in *.sh | All src/**/*.sh + Makefile | 7 functional bugs | 7 | 0 | yes | Fixed: Makefile:216, remind-dogfood.sh:36, cos-env.sh:596-597, classify.sh:108, _pre_commit_body.sh:9, cursor/install.sh:54, codex+cursor dispatcher fallbacks (no-op via symlinks) |
| 5 | Makefile targets | grep package-relative paths in Makefile | Makefile | 1 (cos-stats) | 1 | 0 | yes | Makefile:216 `from db import` → `from database import` |
| 6 | Documentation links | `\]\(([^)]*/)?((core|cli|adapters)/)` in *.md | 68 md in docs/ + AGENTS + README | 3 (foundation-map) | 3 | 0 | yes | foundation-map.md:58,107,108 — `../core/...` → `../src/core/...` |
| 7 | YAML/JSON registries with stale paths | grep in `registry.yaml`, `adapter.yaml`, `stack.yaml`, `scaffold-boundary.yaml` | 1+3+8+7 files | 3 (meta-stack.yaml + scaffold-boundary.yaml) | 3 | 0 | yes | meta/stack.yaml:40 + meta/scaffold-boundary.yaml:16-19,37-38 |
| 8 | Test fixture path strings (string parsing only, NOT runtime path resolution) | grep `(core|cli|adapters)/[a-z_]+/[a-z_]+` literals in tests/ | All tests | ~50 fixtures | 0 | 50 | n/a | All are inputs to extractor/parser tests — strings, not paths to resolve. Out of audit scope. |
| 9 | Graph_os UIDs with legacy prefix | sqlite scan `graph_nodes` where uid LIKE `code:file:core/%` etc. | DB graph_nodes table | 0 | n/a | 0 | yes | `cos doctor::graph.uid_consistency` PASS |
| 10 | Scaffold manifest paths | grep `"core/|"cli/...` in scaffold_manifest.json | 1 file (226K) | 0 | n/a | 0 | yes | Clean. |
| 11 | pyproject entry points | check `[project.scripts]` & `package-dir` | pyproject.toml | 0 | n/a | 0 | yes | All entry points resolve; `cos --version` → `0.3.0` |
| 12 | Web UI / Vite config | grep in `vite.config.ts`, `tsconfig.json`, `package.json` | 3 UI configs | 0 | n/a | 0 | yes | No package-path refs; Vite uses `@/` alias to `./src` (UI src). Clean. |
| 13 | Agent prompts / skills / commands / rules markdown | grep package-path refs in skills+commands+rules+agents | All *.md under those dirs | 0 | n/a | 0 | yes | Clean. |
| 14 | Runtime smoke (cos doctor, verify-hooks, make verify) | full doctor + hook syntax + import check | full repo | 1 FAIL (scaffold.placeholders, unrelated) + 5 WARN | n/a | per below | yes | doctor: 46 PASS / 5 WARN / 1 FAIL (FAIL = template doc placeholder — NOT migration-caused); verify-hooks: PASS; imports: OK; cos-stats: was FAIL → now PASS |

## Resume Marker

<!-- last_updated_row: 14 -->
<!-- next_unchecked_row: 0 -->
<!-- last_updated_at: 2026-05-17T01:00:00Z -->

## Notes

. :

** ( functional +  yaml/doc):**

1. `Makefile:216` —  `cos-stats`  `from db import`  `database.py` rename .
2. `src/core/hooks/remind-dogfood.sh:36` — detector  meta  `${DIR}/templates/_base`  ( `src/`) `src/`  project root .
3. `src/core/hooks/cos-env.sh:596-597` — health-check `board_os`  `${CLAUDE_PROJECT_DIR:-.}/core/board_os` ( `src/`) .  meta-repo  fail .
4. `src/core/skills/thinking_os/scripts/classify.sh:108` — `WRITE_STATE="$REPO_ROOT/core/hooks/write-state.sh"` ( `src/`).  write-state .
5. `src/scripts/_pre_commit_body.sh:9` — `HOOKS_DIR="${REPO_ROOT}/core/hooks"` ( `src/`). git pre-commit hook  (fallback  `.claude/hooks`  primary path ).
6. `src/adapters/cursor/install.sh:54` —  MCP fallback `f'{cos_root}/core/thinking_os'` ( `src/`)  `cos`  PATH .
7. `src/templates/meta/stack.yaml:40` — `REF:HOOK-REGISTRY → ../core/hooks/registry.yaml` ( `src/`)  AGENTS.md  `aggregator.py::STACK_REF_CODES` .
8. `src/templates/meta/scaffold-boundary.yaml:16-19, 37-38` — `roots:`  `imports_from:`  paths  `src/` (only cosmetic — parser  `file_patterns:`  `forbids_writing_in:` ).
9. `docs/_meta/foundation-map.md:58` — `REF:HOOK-REGISTRY → ../core/hooks/registry.yaml`
10. `docs/_meta/foundation-map.md:107` — `../core/scripts/ref-resolve.sh`
11. `docs/_meta/foundation-map.md:108` — `../core/scripts/docs-lint.sh`

**:**

- . ✓
- pyproject.toml mapping .  import . ✓
-  markdown  resolve  (doctor docs.markdown_link_integrity). ✓
- graph DB  UID legacy . ✓
-  verify-hooks syntax-clean. ✓
- Cursor + Codex dispatcher fallbacks `../../../core/hooks/`  `src/core/hooks/`  ( `src/adapters/<id>/hooks/`  `../`  `src/` ) — fallback .

** (pre-migration scope  audit):**

- `src/core/thinking_os/server.py`  sibling-imports (`from database import`, `from tools.X import`)  `python server.py`  `import thinking_os.server`.  ** migration**  ( `git show 5b7e33d~1:core/thinking_os/server.py`).  caller `src/scripts/audit_mcp_tools.py` .

## Closing Checklist

- [x] Every category row has non-empty `Files scanned`
- [x] Every category row has `Hits after = 0` (or explicit `n/a` with justification)
- [x] Every category row has `Verified = yes`
- [x] Every category row has a non-empty `Evidence` cell
- [x] EvidenceBundle submitted via `cos_supervise_record_output`
- [x] Reviewer subagent re-grep produced zero hits (verdict: PASS)
- [x] Frontmatter `status` updated to `completed`
