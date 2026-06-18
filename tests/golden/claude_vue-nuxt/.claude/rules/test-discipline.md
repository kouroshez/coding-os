# Test Discipline (Always Active)

> **Hard rule:** Run only the Verification Matrix command for what changed. Never `pytest tests/ -q` mid-task — the `test-governor` hook BLOCKs it without an audited override.

The suite is ~4,110 test functions across 289 files; the matrix suites alone sum to ~28 min wall-clock, so a full sweep mid-task melts a laptop running concurrent sessions. Measurements + spec: [test-governance.md](../../docs/engineering/test-governance.md).

## Enforcement + the verify ledger (no longer convention-only)

Three mechanisms back this rule (spec: [test-governance.md](../../docs/engineering/test-governance.md)):

1. **Dedup** — suite runs auto-record to `$COS_STATE_DIR/.last-verify.json` (keyed on git_head + dirty_digest). Re-running a suite already green on the same tree within TTL is BLOCKed; force with `COS_TEST_FORCE=1 <command>`.
2. **Run lock** — one heavy pytest run per machine (`$COS_STATE_DIR/.test-run.lock`, TTL + liveness); a concurrent attempt is BLOCKed naming the holder.
3. **Full-sweep gate** — bare `pytest`, `pytest tests/`, or ≥3 test roots is BLOCKed unless `COS_FULL_SWEEP_OK=1 COS_OVERRIDE_REASON='...≥15 chars'` (audited). Prefix heavy runs with `nice -n 19`.

A tree change auto-invalidates recorded passes. Slow-marked tests (314: `test_background.py`, scaffold sandboxes) run via `make test-slow` pre-merge, not mid-task.

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

In those cases say so out loud before launching ("Running full sweep — expect ~30 min") and run it with the audited override under `nice`:

```bash
COS_FULL_SWEEP_OK=1 COS_OVERRIDE_REASON='pre-merge final gate' nice -n 19 uv run pytest tests/ -q
```

## Before writing any test/script/function/feature

P1 SSOT — check existing first (`cos_graph_context`/`cos_search` for code, `cos_doc_search` for spec, grep/find for the symbol). Found it? Reuse. See [anti-overengineering.md](anti-overengineering.md) § Reuse-First.

## Anti-patterns (do not)

- `pytest tests/` after every edit
- `pytest tests/test_cli.py tests/test_adapters.py tests/test_persona_integration.py` "just to be safe"
- Per-file timing sweeps to "see what's slow" — read this file instead
- Re-running a green test "to make sure"
