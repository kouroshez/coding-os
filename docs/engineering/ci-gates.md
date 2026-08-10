<!-- domain:OPS | layer:engineering | ssot:true | updated:2026-08-08 -->
# CI Quality Gates — SSOT

Every blocking gate in `.github/workflows/ci.yml`, what it enforces, and how its
baseline moves. GOVERNANCE.md points here; this doc owns the detail.

## The gates

| Gate | Command | Baseline / threshold | Direction |
|---|---|---|---|
| ruff lint | `uv run ruff check .` | 0 findings; burndown ignores in `pyproject.toml` (`SIM105`, `SIM102`, `E741`) | ignore list may only shrink |
| ruff format | `uv run ruff format --check .` | exact | — |
| Complexity | part of `ruff check` — `C901` (mccabe ≤20), `PLR0912` (branches ≤24), `PLR0913` (args ≤10), `PLR0915` (statements ≤100) | per-file baseline in `pyproject.toml` `per-file-ignores` (101 violations / 40 files, 2026-08-08) | baseline may only shrink; never add a file |
| mypy ratchet | `uv run python src/scripts/mypy_ratchet.py` | error count ≤ `BASELINE` in the script (4649, 2026-08-08 — see the exception log below) | count may only fall; lower `BASELINE` when you fix errors |
| Tests + coverage | `make coverage` | `fail_under` in `pyproject.toml` (62; measured 63) | ratchet toward 70 → 80 |
| Slow suite (nightly) | `make test-slow` + the graph phantom gate, on the `schedule` trigger only | 0 failures; phantom count ≤ baseline | **surfaced, not gating** — `CI Pass` emits a warning; see the order-fragility note below |
| diff-cover (PRs only) | `diff-cover coverage.xml --fail-under 80` | 80% on changed lines | fixed — see the scope note below |
| File-size ratchet | `tests/test_file_size_budget.py` | per-file `BASELINE` (48 files over the 800-line `SOFT_LIMIT`, 2026-08-10) | each entry may only fall; a file outside `BASELINE` may never cross `SOFT_LIMIT` |
| shellcheck | `shellcheck -S warning src/core/hooks/*.sh src/core/scripts/*.sh` | 0 warnings | fixed |
| docs-lint | `make docs-lint` | 0 findings | fixed |
| CodeQL / dependency-review | GitHub-native | high severity | fixed |

## Write-time counterparts (the same standards, earlier)

A CI gate tells you at merge time; a hook tells you before the edit lands. Two
of the standards above have a write-time half so the feedback is not a 20-minute
round trip:

| Standard | Write-time | Merge-time |
|---|---|---|
| File-size budget (500 backstop, 400 warn) | `block-bad-patterns.sh` — BLOCKs a `Write` that authors a file over 500, warns from 400 and on an `Edit` that grows one | `tests/test_file_size_budget.py` per-file ratchet |
| Whole-tree budget (consumers) | — | `make check-file-size` → `src/core/scripts/check_file_size.py` |

The two halves run at **different numbers on purpose, and the gap is the
burndown**. Write-time and the consumer script read `COS_MAX_FILE_LINES`
(default 500) / `COS_WARN_FILE_LINES` (default 400), so nothing NEW crosses 500.
The merge-time ratchet still uses `SOFT_LIMIT = 800` because 114 files in this
repo are already over 500; dropping it now would mean adding ~100 `BASELINE`
entries, which the ratchet's own protocol forbids. Lower `SOFT_LIMIT` toward 500
as the burndown deletes entries — never by widening `BASELINE`.

The consumer script is likewise absent from *this* repo's CI: it would fail on
every run today. coding-os uses the per-file ratchet until the burndown lands; a
fresh consumer project starts clean and can gate on the script from day one.

## Ratchet protocol (applies to every "may only shrink" baseline)

1. Fix the underlying finding (refactor below threshold, type the module, split the file).
2. Shrink the baseline in the same commit — delete the per-file-ignore entry,
   lower `BASELINE` (mypy count, or the file's line entry) / raise `fail_under`.
3. Never widen a baseline to land a change; the gate exists to make regressions
   loud. A deliberate exception needs a task + a line here explaining why.

Recorded exceptions:

- 2026-08-10 (TASK-928): `src/core/thinking_os/embeddings.py` (943 lines) keeps
  its `BASELINE` entry and is **not** split. It has clean cohesion seams (model
  config, encoding, similarity, storage, search, outbox/reindex) but no seam that
  survives its test contract: `is_available`, `_get_model` and `embed_text` are
  patched with `patch.object(embeddings, …)` in six suites, and every other
  section calls them — `cosine_similarity_with_meta`, `upsert_embedding`,
  `search_similar`, `drain_outbox` and `reindex_all` each call `is_available()`
  directly. The module is deliberately written that way (see the comment at
  `embed_text`: "…so existing tests that patch it keep working"), so moving any
  caller to a sibling means the facade patch stops reaching it and the test
  silently exercises the real encoder. The same class of blocker as
  `pr_commands.py` below; the next attempt starts from the patch strategy, not
  from the module.

- 2026-08-10 (TASK-928): the `_shared.py` file-size entry (947) was deleted
  rather than lowered — the split dropped the facade to 398, under `SOFT_LIMIT`.
  The five `_envelope_*` siblings carried the flat-sibling `import-not-found`
  class again; this time it was silenced precisely at each fallback import
  (`# type: ignore[no-redef,import-not-found]`) instead of via a bare-name
  `ignore_missing_imports` glob, because those globs are inert — mypy reports the
  whole list under `warn_unused_configs`. Typing the trimmers' `dict`/`list`
  parameters took the local count to 4,482; `BASELINE` stays at 4,500 because it
  is a CI-measured number and this one is not.

- 2026-08-10 (TASK-927): `src/cli/pr_commands.py` (2,024 lines) was split into a
  `_pr_shared` leaf plus a `pr_reap_commands` module and then **reverted**. The
  split itself worked — `cos pr/reap/heal` all smoke-ran and the command count
  held at 99 — but its test suite patches eleven private helpers directly on the
  `pr_commands` module. Once a helper moves, a patch on the facade no longer
  reaches calls made from inside the sibling, so ~20 tests fail for reasons that
  have nothing to do with behaviour. Making them pass means either patching two
  namespaces per helper or rewriting the suite's patch strategy — a change to the
  *tests'* design that deserves its own task rather than riding a file move.
  The file stays on the backlog with this note so the next attempt starts from
  the test suite, not from the module.

- 2026-08-10 (TASK-928): mypy BASELINE 4524 → **4500** and the `workflow.py`
  file-size entry (964) deleted — the split dropped it to 422. The +2 the split
  first introduced were the flat-sibling `import-not-found` class again, so
  `board_os.config` and the three `transition_gates*` names joined
  `ignore_missing_imports` rather than widening the count; that fix cleared 24
  errors repo-wide. All five new `_workflow_*` siblings were added to the mypy
  strict list so the split does not silently drop the strict coverage
  `board_os.workflow` had. Ruff `PLR0915` is no longer needed on `workflow.py`
  (4 ignores → 3). Behaviour verified by a 20-scenario differential against the
  pre-split module comparing every `TransitionResult` field, the tasks row, the
  `task_status_history` entry, and the written frontmatter.

- 2026-08-10 (TASK-928): mypy BASELINE 4540 → **4524** and the `code_php.py`
  file-size entry (979) deleted rather than lowered — the split dropped it to
  300, under `SOFT_LIMIT`. The ruff `C901`/`PLR0915` per-file ignore moved from
  `code_php.py` to `_php_symbols.py`, the one function that earns it; the facade
  now passes with no ignore at all. Verified by a differential that runs the
  pre-split module and the facade over the same corpus in both parse modes and
  compares nodes, edges and parse errors exactly.

- 2026-08-10 (TASK-927): mypy BASELINE 4599 → **4540**, tightened not widened.
  Four more god-file splits pushed the count up +46 by repeating flat sibling
  imports and by the dual-identity `try/except` guards reading as `no-redef`.
  Both are artifacts of the split mechanics, so they were fixed at the source —
  the `ignore_missing_imports` list now covers every flat sibling name and each
  guard's fallback branch carries one `type: ignore[no-redef]`. Net for the
  session: 4651 → 4540.

- 2026-08-10 (TASK-926): mypy BASELINE 4687 → 4567 → **4599**, a net fall of 88
  across the session. The `ignore_missing_imports` override for the flat sibling
  names removed 120 `import-not-found` errors; the try/except import guard in
  `database.py` then made the *relative* branch resolvable, so mypy started
  type-checking through `_db_migrations` instead of treating it as `Any` and
  surfaced 32 real errors it had been blind to. A rise that buys visibility is
  not the same as a rise that hides regressions — this one is the former.

- 2026-08-10 (TASK-926): `src/core/thinking_os/_db_migrations.py` stays at ~2,240
  lines, over the 500 backstop, and is baselined in the file-size ratchet rather
  than split. It is the append-only schema ledger: Rule 9 freezes every entry the
  moment it ships, so the file has exactly one reason to change — appending. The
  only available cuts are by version range (arbitrary) or by subsystem (graph
  migrations sit at v12 *and* v28, so ordering breaks and reading the schema
  history becomes a four-file scan). Splitting here would produce exactly the
  incoherent fragments anti-overengineering.md sub-rule 6 forbids.

- 2026-08-08 (TASK-920): mypy BASELINE 4599 → 4649. The mcp_tools/doctor
  splits relocated 166 existing errors under new module identities and the
  dual `board_os.*`/`core.board_os.*` import paths double-count some of them;
  a pre/post error-list diff confirmed no new untyped code. The gate caught
  the +410 implicit-re-export regression first, which WAS fixed (`__all__`).
- 2026-08-10 (TASK-925): mypy BASELINE 4651 → 4687. The server.py split moved
  code verbatim into seven `_tools_*` siblings; each repeats the flat imports
  (`from _server_runtime import …`, `from tools._shared import …`) that mypy
  cannot resolve, so **one** `import-not-found` became seven. No new untyped
  code — the delta is entirely `[import-not-found]` on modules that were
  already unresolvable from server.py. The root fix is a `mypy_path` that makes
  the flat-import convention resolvable; a naive `MYPYPATH=src:src/core:…`
  produces a duplicate-module error (`dispatcher.py` reachable two ways) and
  needs `explicit_package_bases`, so it is tracked as its own task rather than
  bolted onto a refactor.
- 2026-08-09 (TASK-921): mypy BASELINE 4649 → 4651. The gate caught a real
  regression from the new repair tests (wrong import path + unnarrowed
  `Optional`s) and that WAS fixed; the residual +2 sits inside the
  local↔CI counting gap (local reports 4635 for the same tree), so the
  baseline is re-measured from CI. **Always re-measure from a CI log** — a
  laptop number will silently under-set the gate. The failure output now
  prints per-file counts so the next rise is diagnosable without a CI
  round-trip.

## What each gate does NOT cover (scope honesty)

The gates are real, but two of them only ever see pull requests, and this repo
is trunk-based — the maintainer pushes straight to `main`:

- **diff-cover ≥80%** and **dependency-review** run on `pull_request` only.
  In practice that means Dependabot and release-please PRs; a hand-written
  commit pushed to `main` is never measured by either. Treat them as gates for
  *external contributions*, not as a guarantee over all code.
  Worse until 2026-08-10: diff-cover fetched the base branch with `--depth=1`,
  so `origin/<base>...HEAD` had no merge base and the step *crashed* on every
  PR. The gate had never measured a single line — it failed closed, blocking
  the whole Dependabot queue. A gate that only ever fails is not a gate.
- **Branch protection** requires `CI Pass` with `enforce_admins: false`, which
  is what keeps trunk pushes working. For the maintainer the check is therefore
  *post-push reporting*, not a pre-merge block — a red `main` is visible and
  must be fixed forward, not prevented.
- **`make docs-lint`** hard-gates the link audit; its front-matter and staleness
  half is advisory locally and only strict-gated on *changed* docs in CI.
- **The nightly slow suite is order-fragile**, so it reports rather than gates.
  Measured 2026-08-09: two back-to-back `make test-slow` runs on an identical
  tree failed on *different* sets — the second run cleared five fixed failures
  and surfaced two new ones (`TestPersonaGoFiber`) that had passed an hour
  earlier. Root cause class: tests inheriting ambient `COS_*` env and shared
  scaffold state (issue #39). Until a run is reproducible, `CI Pass` emits a
  warning instead of failing; gating on a flaky suite would just teach everyone
  to ignore a red `main`.

## mypy promotion path

`[tool.mypy]` is lenient globally with per-package `strict = true` overrides
(`thinking_os.tools.*`, `graph_os.backends.*`, `board_os.workflow`). The ratchet
holds the total error count while packages are promoted one at a time: type a
package, add it to the strict list, lower `BASELINE`. mypy becomes a plain
zero-error gate when `BASELINE` reaches 0.

## Local mirror

`pre-commit` runs ruff, ruff-format, and shellcheck on staged files — the fast
subset. mypy, coverage, and the ratchets run in CI and via their commands above.
