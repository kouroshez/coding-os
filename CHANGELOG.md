# Changelog

All notable changes to coding-os are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> Pre-public development happened on a private branch and is preserved
> locally under the `archive/full-history` branch and the tag
> `archive/pre-public-2026-05-20`. The public history starts at the
> [0.3.0](#030--2026-05-20) entry below.

## [Unreleased]

### Added

### Changed

### Fixed

### Removed

---

## [0.3.0] — 2026-05-20

Initial public release of **coding-os**, the agent-agnostic cognitive
operating system for AI coding agents.

### What is coding-os?

Three-layer composition that teaches AI agents *how to think* and
*how to code*:

- **`src/core/`** — agent-agnostic kernel: MCP server (`thinking_os`,
  `graph_os`, `board_os`), hooks (62 scripts), rules, skills.
- **`src/adapters/<agent>/`** — per-agent translation: how the kernel
  surfaces as `.claude/`, `.codex/`, `.cursor/`.
- **`src/templates/<stack>/`** — per-stack scaffolds: Django, Next.js,
  FastAPI, Go, Go+Fiber, React Native, Python library, Meta.

The `cos` CLI composes the three layers into a consumer project that
inherits the same skeleton (own hooks, own MCP, own `AGENTS.md`).

### Highlights of the 0.3 line

#### Cognitive layer (`thinking_os` + `graph_os` + `board_os`)

- 11 semantic agent roles (researcher, analyst, architect, documenter,
  implementer, reviewer, debugger, security_auditor, deployer,
  observer, refactorer) composable via `cos_compose_chain`.
- Append-only schema migrations with idempotent extractors.
- Polyglot graph extractor: Python, TS/TSX, Go, Bash, YAML, Markdown,
  JSON, TOML. Parallel reindex (`cos graph-reindex --workers N`).
- Knowledge graph backed by SQLite (Kuzu backend retired in B2 series
  — see ADR 02).
- 79 MCP tools, all under the `cos_*` prefix with the
  `ok(data) / fail(category, message)` envelope (Rule 13).

#### Workflow governance

- Intent enforcement layer: exhaustive-intent vocabulary (FA + EN)
  triggers evidence-required audit mode (G0–G14).
- Completion guardian (Stop hook) refuses premature "done" claims
  without satisfying predicates.
- Scrumban task system (`docs/tasks/TASK-*.md`) with axes:
  swimlane · kind · epic · labels. WIP-limit enforcement.

#### Web Hub

- Singleton FastAPI + uvicorn on port 9188, multi-project router via
  `/api/p/<slug>/*`. SSE event stream at `/api/stream/events`.
- React 18 + Vite + TypeScript + Sigma.js graph canvas + Zustand state.
- 4 tabs: Graph (3 views — overview/tree/code), Board (Scrumban),
  Cognition (trace replay), Search.
- All `/api` responses ≥ 500 B gzipped (compresses 270 KB → 21 KB).

#### Adapter parity

- Adapter capabilities declared in
  `src/adapters/<agent>/adapter.yaml::hook_capabilities` — renderer
  skips registry entries the agent's CLI can't fire.
- Claude Code: 58/62 hooks fire. Cursor: 59/62. Codex CLI: 21/62
  (Bash-only). Codex GUI: 0/62 (`.codex/hooks.json` ignored upstream).

#### Performance

- Database mmap + `ANALYZE` on init → 4× faster JOINs.
- Nightly auto-reindex when graph probe > 24 h stale.
- Barnes–Hut FA2 layout cuts graph-tab freeze from 10–30 s to < 2 s.
- Hook timeouts capped at ≤ 30 s (previously up to 5000 s).

#### Repo hygiene (this release)

- Apache License 2.0 + NOTICE.
- SECURITY.md private-disclosure policy.
- CONTRIBUTING.md + CODE_OF_CONDUCT 2.1.
- `.github/workflows/ci.yml` matrix CI on every PR.
- `pyproject.toml` `[tool.ruff]` + `[tool.mypy]` baseline.
- `.github/dependabot.yml` (Python uv, npm, actions).
- `.pre-commit-config.yaml` (ruff + shellcheck + prettier).
- 5 ADRs documenting the major architectural decisions of the 0.x line.

### Removed in 0.3.0

- Internal client references (`NakoDigital`) replaced with neutral
  `ExampleApp` placeholders across scaffold templates, golden
  fixtures, and the E2E verification script.
- Developer-local path defaults in `verify_phase_c_e2e.py`; the script
  now requires `COS_CORPUS_PATH` explicitly.
- Pre-public development history (preserved locally — see top of file).

### Acknowledgements

- The thinking_os methodology draws on John Boyd's OODA loop, the
  Cynefin framework (Snowden), Wardley Mapping, and DDD bounded
  contexts.
- The graph_os layer draws on Roy Fielding's REST dissertation,
  tree-sitter, and the GraphRAG literature.

[Unreleased]: https://github.com/kouroshebra/coding-os/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/kouroshebra/coding-os/releases/tag/v0.3.0
