# Test Discipline (Always Active)

> **Hard rule:** Run only the Verification Matrix command for what changed. Never `pytest tests/ -q` mid-task.

## Why

`pytest tests/ -q` runs 743 broad integration tests (~6 minutes — scaffold cos init, install symlinks, real DB ops). The matrix commands run 15s–90s each. Six minutes per change × N iterations = the user waits, productivity dies, hooks rot.

## Match changed files → command (single source: AGENTS.md Verification Matrix)

| Changed | Command |
|---|---|
| `src/core/thinking_os/**.py` | `uv run --extra rag pytest src/core/thinking_os/tests/ -q` |
| `src/core/thinking_os/database.py` | `uv run --extra rag pytest src/core/thinking_os/tests/test_db.py -q` |
| `src/core/graph_os/**` | `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` |
| `src/core/board_os/**` | `uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q` |
| `src/core/hooks/*.sh` | `make verify-hooks` |
| `src/adapters/**` | `uv run pytest tests/test_adapters.py tests/test_adapter_parity.py -q` |
| `src/cli/*.py` | `uv run pytest tests/test_cli.py -q` |
| `src/templates/**/scaffold/**` | `uv run pytest tests/test_template_scaffold.py -q` |
| `docs/**/*.md` | `make docs-lint` |

If a single file affects two rows, run both — still cheaper than full sweep.

## Single-test targeting

When debugging one failure: `pytest path/to/test_file.py::TestClass::test_name -v`. Resist the urge to "just run the file" until the named test passes. Re-run the file only after the targeted test goes green.

## When full sweep IS allowed

- Pre-merge / pre-release final gate
- Cross-cutting refactor that touched ≥3 verification-matrix rows
- User explicitly asked: "run all tests"
- **Task class = audit_exhaustive** (see below)

In those cases say so out loud before launching: "Running full sweep — expect ~6 min."

## Per-task-class verification matrix (TASK-004 G9)

The per-file matrix above answers "what changed?".  Some task CLASSES
have additional verification obligations that fire regardless of which
files changed — because the contract is about the work itself, not the
files touched.

| Task class | Triggered by | Mandatory verification |
|---|---|---|
| `audit_exhaustive` | intent.json::exhaustive=true OR preset `audit-exhaustive` matched | (1) full `pytest tests/ -q` · (2) `cos sync-doctor` returns clean · (3) `grep -rn '<each pattern from audit table>' src/ tests/ docs/` returns 0 · (4) `cos graph-doctor` returns clean · (5) `make docs-lint` clean · (6) reviewer subagent (G6 hint) returns PASS · (7) ExhaustiveEvidence submitted via cos_supervise_record_output |
| `migration_exhaustive` | intent.matched_scope includes "migrate" + exhaustive | per-file matrix PLUS before/after state diff captured in audit Notes section |
| `refactor_exhaustive` | intent.matched_scope includes "refactor" + exhaustive | per-file matrix PLUS `cos_graph_impact` re-run for every renamed symbol, comparison stored in audit Evidence column |

For audit-class tasks the per-file matrix command alone is INSUFFICIENT —
the completion guardian (G4) will refuse the Stop until the class-level
checks above are recorded in the EvidenceBundle.

## Before writing any test/script/function/feature

P1 SSOT — check existing first:

1. `cos_graph_context` / `cos_search` for related code
2. `cos_doc_search` for spec
3. `grep` / `find` for the symbol

Found it? Reuse. Not found? Add and index — don't duplicate.

## Anti-patterns (do not)

- `pytest tests/` after every edit
- `pytest tests/test_cli.py tests/test_adapters.py tests/test_persona_integration.py` "just to be safe"
- Per-file timing sweeps to "see what's slow" — read this file instead
- Re-running a green test "to make sure"
