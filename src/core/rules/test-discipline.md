# Test Discipline (Always Active)

> **Hard rule:** Run only the Verification Matrix command for what changed. Never `pytest tests/ -q` mid-task.

## Why

`pytest tests/ -q` runs 743 broad integration tests (~6 minutes — scaffold cos init, install symlinks, real DB ops). The matrix commands run 15s–90s each. Six minutes per change × N iterations = the user waits, productivity dies, hooks rot.

## Match changed files → command (single source: AGENTS.md Verification Matrix)

| Changed | Command |
|---|---|
| `src/core/thinking_os/**.py` | `uv run --extra rag pytest src/core/thinking_os/tests/ -q -m 'not slow'` |
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

In those cases say so out loud before launching: "Running full sweep — expect ~6 min."

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
