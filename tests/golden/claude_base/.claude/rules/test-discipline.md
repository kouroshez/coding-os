# Test Discipline (Always Active)

> **Hard rule:** Run only the Verification-Matrix command for what changed (SSOT: **AGENTS.md § Verification Matrix** — deliberately not duplicated here). Never `pytest tests/` mid-task — the `test-governor` hook BLOCKs it without an audited override. The suite is ~4,850 tests / ~28 min wall-clock; a full sweep melts a laptop running concurrent sessions. Measurements + spec: [test-governance.md](../../docs/engineering/test-governance.md). If one file matches two matrix rows, run both — still cheaper than a sweep.

## Enforcement + the verify ledger

1. **Dedup** — suite passes auto-record to `$COS_STATE_DIR/.last-verify.json` (keyed on git_head + dirty digest); re-running a suite already green on the same tree is BLOCKed — force with `COS_TEST_FORCE=1`. A tree change auto-invalidates.
2. **Run lock** — one heavy pytest per machine (`$COS_STATE_DIR/.test-run.lock`, TTL + liveness); a concurrent attempt is BLOCKed naming the holder.
3. **Full-sweep gate** — bare `pytest`, `pytest tests/`, or ≥3 test roots BLOCKed unless `COS_FULL_SWEEP_OK=1 COS_OVERRIDE_REASON='...≥15 chars'` (audited). Prefix heavy runs with `nice -n 19`. Slow-marked tests (314) run pre-merge via `make test-slow`, not mid-task.

## Run the deliverable, not just its proxy (Critical Rule 26)

A green pytest suite proves the *units* import under the harness — **not** that the delivered executable runs: `pytest` puts the package on `sys.path`; `python path/to/script.py` does not, so an import that passes under test still crashes as `ModuleNotFoundError` when run directly (the `nightly.py` incident). Before `cos task-move --to testing` and before handing the user any command or claiming a behaviour:

- **Smoke-run the artifact end-to-end** — `--help`, `--dry-run`, or a real invocation, from the same entry the user/cron uses. Reading the code is not verification; `--slug` vs `--project` is settled by running `--help`, never by reading the parameter name.
- **A command you paste to the user is a claim** — only paste one you executed this session.
- **New runnable entrypoint → add a smoke test** to its suite (`--help` or `python -c "import <module>"` via subprocess) so `enforce-verify.sh` covers the executable path, not just the units.

Runtime sibling of [api-contract-discipline.md](api-contract-discipline.md): don't guess a *behaviour* contract — verify by executing.

## Test cadence — the matrix says *which*, this says *when*

1. **During dev → ONE targeted test:** `pytest path/to/test.py::TestClass::test_name -v`; re-run the file only after the named test goes green. Re-running a ledger-green suite "to be sure" is the anti-pattern, not the safe choice.
2. **At task close → the matrix suite ONCE,** right before `cos task-move --to testing`; the ledger dedups it for the next agent on the same tree.
3. **Heavy suite (>~60s) → background it** (`run_in_background`) and keep reading/diffing/writing — never idle-wait. Don't start a second pytest until the first exits (run lock names you as the concurrent holder). Batch heavy suites across sibling tasks: park one in `testing`, finish a sibling, run once for the batch.
4. **docs-lint → once at close** (the ledger excludes `docs/tasks/` churn — per-message lint is pure latency), or when a non-task `.md` actually changes.

## Full sweep is allowed only for

Pre-merge / pre-release final gate · a cross-cutting refactor touching ≥3 matrix rows · explicit user ask ("run all tests"). Say so out loud first ("Running full sweep — expect ~30 min"), then:

```bash
COS_FULL_SWEEP_OK=1 COS_OVERRIDE_REASON='pre-merge final gate' nice -n 19 uv run pytest tests/ -q
```

## Before writing any test/script/function/feature

P1 reuse-first: check `cos_graph_context`/`cos_search` (code), `cos_doc_search` (spec), grep (literal) — found it → reuse ([anti-overengineering.md](anti-overengineering.md) § Reuse-First).
