---
id: TASK-082
title: "graph_os P1: Language toolchain config parser (tsconfig.json, go.mod, Cargo.toml, pyproject.toml) for import resolution"
swimlane: graph_os
kind: feature
epic: graph_os-the upstream scope-resolution implementation
labels: [hub, graph, config, imports, P1-parity]
status: icebox
priority: P1
appetite: "5h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: [TASK-080]
blocked_by: []
references: []
---

# TASK-082: graph_os P1 — Language toolchain config parser

**Outcome (one sentence):** Cross-file import resolution uses real path-aliases from `tsconfig.paths`, the Go module prefix from `go.mod`, and crate names from `Cargo.toml` / `pyproject.toml` — so `from @shared/auth import login` or `import "myapp/internal/auth"` emit concrete edges to real nodes instead of falling back to `unresolved:@shared/auth`.

## Read First

- [core/graph_os/extractors/code_ts.py](../../core/graph_os/extractors/code_ts.py) — current TS import resolver: falls through to `unresolved:` when it doesn't know an alias.
- [core/graph_os/extractors/code_python.py](../../core/graph_os/extractors/code_python.py) — Python counterpart; today it reads nothing from `pyproject.toml`.
- [core/graph_os/ingest/](../../core/graph_os/ingest/) — file walker; where per-repo toolchain scan should hook.
- external graph tooling capability matrix (Phase P1 analysis): "Language toolchain config parsing — " → this task closes that gap.

## Acceptance (G/W/T) — *this IS the Definition of Done*

- **Given** a repo with `tsconfig.json` declaring `"paths": { "@shared/*": ["packages/shared/src/*"] }`
  **When** any `.ts` file does `import { login } from "@shared/auth"`
  **Then** the emitted `IMPORTS` edge resolves to the concrete node `packages/shared/src/auth` — not `unresolved:@shared/auth`.
- **Given** a Go repo with `module github.com/acme/myapp` in `go.mod`
  **When** any `.go` file does `import "github.com/acme/myapp/internal/auth"`
  **Then** the edge resolves to `internal/auth` (repo-local), and any external import (e.g. `github.com/stretchr/testify`) is tagged `external:github.com/stretchr/testify` — preserved, not dropped.
- **Given** a Rust repo with `name = "myapp"` in `Cargo.toml` and workspace members `["crates/core", "crates/api"]`
  **When** extraction runs
  **Then** `use myapp::core::X` resolves to `crates/core/**`, and inter-crate references emit `WORKSPACE_CRATE` edges.
- **Given** a Python repo with `[tool.poetry.packages] = [{ include = "myapp" }]` under `src/myapp/`
  **When** extraction runs
  **Then** `from myapp.auth import login` resolves to `src/myapp/auth.py` — not the top-level `myapp/` anti-match.
- **Tests:** `core/graph_os/tests/test_toolchain_config.py`, one fixture per toolchain (4 total) with ≥ 4 resolved imports each.

## Implementation Notes

1. New module `core/graph_os/toolchain.py` exposing `load_toolchain(repo_root) -> ToolchainContext` that caches parsed configs keyed by `(repo_root, mtime_sum)`.
   - `ToolchainContext` dataclass: `ts_paths: dict[str, list[str]]`, `go_module: str | None`, `rust_crates: dict[str, Path]`, `python_packages: dict[str, Path]`.
2. Extractors accept `toolchain: ToolchainContext` as a second arg; fallback path stays for repos without config files (no regression).
3. Resolution precedence when both tsconfig alias and relative path could match: alias wins (matches `tsc --traceResolution` behavior).
4. Tolerance: if a config file is malformed, log WARN and fall back — never raise. Malformed-config fixtures must assert this.
5. Watch for `compilerOptions.baseUrl` interaction with `paths` (tsc semantics); reference file `docs/engineering/toolchain-resolution.md` (create as part of this task).

## Dependencies

- **Depends on:** TASK-080 (tree-sitter primary → clean AST hand-off to resolver).
- **Unblocks:** TASK-077 multi-lang extractors — Go/Rust toolchains are not optional for them.

## Work Log
