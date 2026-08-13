<!-- domain:OPS | layer:engineering | ssot:true | updated:2026-08-13 -->
# CI Quality Gates — SSOT

Every blocking gate in `.github/workflows/ci.yml`, what it enforces, and how its
baseline moves. GOVERNANCE.md points here; this doc owns the detail.

## The gates

| Gate | Command | Baseline / threshold | Direction |
|---|---|---|---|
| ruff lint | `uv run ruff check .` | 0 findings; burndown ignores in `pyproject.toml` (`SIM105`, `SIM102`, `E741`) | ignore list may only shrink |
| ruff format | `uv run ruff format --check .` | exact | — |
| Complexity | part of `ruff check` — `C901` (mccabe ≤20), `PLR0912` (branches ≤24), `PLR0913` (args ≤10), `PLR0915` (statements ≤100) | per-file baseline in `pyproject.toml` `per-file-ignores` (101 violations / 40 files, 2026-08-08) | baseline may only shrink; never add a file |
| mypy ratchet | `uv run python src/scripts/mypy_ratchet.py` | error count ≤ `BASELINE` in the script (1100, 2026-08-11 — kernel source only, `/tests/` excluded) | count may only fall; lower `BASELINE` when you fix errors |
| mypy fatal codes | same command | `FATAL_CODES` in the script — **0 occurrences**, over a wider scope than the count baseline | zero-tolerance; a code leaves the set only with a recorded exception |
| Tests + coverage | `make coverage` | `fail_under` in `pyproject.toml` (62; measured 63) | ratchet toward 70 → 80 |
| Slow suite (nightly) | `make test-slow` + the graph phantom gate, on the `schedule` trigger only | 0 failures; phantom count ≤ baseline | **surfaced, not gating** — `CI Pass` emits a warning; see the order-fragility note below |
| diff-cover (PRs only) | `diff-cover coverage.xml --fail-under 80` | 80% on changed lines | fixed — see the scope note below |
| File-size ratchet | `tests/test_file_size_budget.py` | `SOFT_LIMIT = 500` with three recorded `BASELINE` exceptions (2026-08-11) | each entry may only fall; a file outside `BASELINE` may never cross `SOFT_LIMIT` |
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

**All three halves now run at 500.** They were deliberately split for a
while — write-time and the consumer script read `COS_MAX_FILE_LINES` (default
500) / `COS_WARN_FILE_LINES` (default 400), while the merge-time ratchet sat at
`SOFT_LIMIT = 800` because 120 files in this repo were already over 500 and
dropping the number would have meant adding ~100 `BASELINE` entries, which the
ratchet's own protocol forbids.

The burndown closed that gap the only way the protocol allows: by deleting
entries, never by widening `BASELINE`. Every tracked Python file outside the
exclusion prefixes is now under 500 except the three recorded exceptions below,
so `SOFT_LIMIT` is 500 and write-time and merge-time finally agree. A file that
crosses 500 from here is a new offender, not legacy debt — split it; do not add
a `BASELINE` key.

## Split parity — prove the move was a move

`uv run python src/scripts/check_split_parity.py <pre-split-ref> <old-path> <dir>`
re-parses the pre-split module and every module in the post-split package, and
reports any function that vanished or whose body is no longer byte-identical.
Pass the **directory**, not a hand-written file list — naming files by hand
produces false VANISHED reports for functions that landed somewhere unlisted.

It runs in seconds where the equivalent suite takes minutes, and it catches the
class of defect a suite cannot: an edit that rides along inside a "move" commit.
Deliberate edits are reported too, which is the point — land them separately.

## Why the mypy gate has two tiers

A count ratchet cannot tell a genuine new bug from noise. On 2026-08-10 a module
split dropped the `return normalized` line from a function annotated
`-> dict[str, Any]`; mypy reported `Missing return statement [return]` and the
gate still passed, because that one error sat inside a 4,482-error budget. The
shipped effect was silent: the function returned `None`, every hook-map
comparison became `None != None`, and `cos doctor` reported a stale adapter as
healthy. Only a test that asserted the FAIL severity caught it.

So the script enforces two things from one mypy run:

- **Count** — total ≤ `BASELINE`, over `SCOPE` (the three kernel packages the
  baseline was measured against). Legacy-debt pressure.
- **Fatal codes** — `FATAL_CODES` must stay at **zero**, over `FATAL_SCOPE`,
  which is wider (`src/cli` and `src/core/web` included) because those packages
  carry no count baseline and were therefore ungated entirely. Each code in the
  set was measured at zero when added and names a bug class that a refactor
  actually produces: `return` (a dropped `return` on a value-returning
  function), `call-arg` (a moved function called with the old signature),
  `used-before-def` (a reordered module-level statement).

Adding a code to `FATAL_CODES` requires it to be at zero first — fix the
occurrences, then add it, in that order. Removing one requires a recorded
exception below.

### The count tier measures source only; the fatal tier still reads tests

`SCOPE` is three package directories and each contains its own `tests/`, so the
count used to include every untyped pytest fixture in the repo — 3,205 of 4,605
errors, 70% of the gate. That made a volume gate hostage to test refactors:
splitting the oversized suites on 2026-08-11 copied each module's untyped
preamble into its siblings, mypy counted the same errors several times, and the
count rose 4490 → 4621 without a single new type defect. The fatal tier measured
zero on that same run — the tier that would have caught a real one.

`COUNT_EXCLUDE = r"/tests/"` now applies to the count run only (TASK-936). The
volume gate measures kernel source; `FATAL_SCOPE` is unchanged, so a genuine
`return` / `call-arg` / `used-before-def` bug in a test still fails the build.

### Why `import-not-found` cannot reach zero (TASK-925)

The kernel is imported under two conventions that both work at runtime because
`src/` and `src/core/` are both on `sys.path`: `from thinking_os.tools import …`
(220 files) and `from core.thinking_os.tools import …` (172 sites, kept alive by
an explicit `packages` entry in `pyproject.toml`). mypy can only give a file one
module name, and `src/core/__init__.py` forces it to be the `core.`-prefixed
one — so the other spelling is unresolvable by construction. Pointing
`MYPYPATH` at `src/core` does not help; it makes every kernel file resolve twice
and mypy stops with `Source file found twice under different module names`.

Two consequences worth knowing before touching this:

- The `strict = true` overrides are spelled **twice**, once per convention. The
  bare spelling alone bound to nothing in the crawl, so the strict promise did
  not reach the source it named. Binding it cost zero new errors.
- The unresolvable names are silenced per-package (`board_os.*`, `graph_os.*`,
  `thinking_os.*`) rather than one module at a time, so a module split no longer
  adds a line. The remaining flat spellings (`from database import …`) stay
  enumerated: mypy's `*` matches a whole dotted component, never a bare prefix.

Collapsing to one convention would delete the whole class, but it is a ~400-site
import migration plus a packaging change — not a config fix.

## Ratchet protocol (applies to every "may only shrink" baseline)

1. Fix the underlying finding (refactor below threshold, type the module, split the file).
2. Shrink the baseline in the same commit — delete the per-file-ignore entry,
   lower `BASELINE` (mypy count, or the file's line entry) / raise `fail_under`.
3. Never widen a baseline to land a change; the gate exists to make regressions
   loud. A deliberate exception needs a task + a line here explaining why.

Recorded exceptions:

- 2026-08-11 (TASK-933 → TASK-936): mypy count `BASELINE` **raised** 4490 →
  4621, the only rise on record. Cause: splitting the 41 oversized test suites
  copies each module's untyped pytest preamble into every sibling, so mypy
  counts the same errors several times. Evidence it is an artifact and not a
  regression: `FATAL_CODES` measured **zero** on the same CI run, and no source
  file changed in that commit range. The number is taken from the CI log of run
  31525204367, never from a local mypy. Retired the same day by TASK-936 below.
- 2026-08-11 (TASK-936): mypy count `BASELINE` **lowered** 4621 → 1100 by
  excluding `/tests/` from the count run. Local measurement 4605 → 1069; the
  baseline carries the usual CI headroom and is tightened to the exact CI number
  once a green run publishes it. This retires the rise above rather than
  inheriting it.

- 2026-08-11 (TASK-928): `src/core/hooks/session-context.sh` (729) **stays whole**.
  Its sibling `cos-env.sh` split cleanly 1301 → 350 because it is 22 order-
  independent function definitions: they moved to four leaves, the facade
  resolves its own symlink back to the meta-repo before sourcing them (so a
  consumer gets the leaves the instant core changes, with no `cos update`), and
  a snapshot of every `COS_*` value plus a sha of all 22 function bodies came
  back identical apart from the `COS_HOOK_T0` timestamp. `session-context.sh`
  has the opposite shape — one function and ~700 lines of order-dependent
  statements threading `$INPUT`, `$SOURCE` and the panel state through each
  other. Cutting it would mean `source part1.sh; source part2.sh` at fixed
  positions: indirection with no independently testable boundary, which
  anti-overengineering sub-rule 6 forbids ("never carve arbitrary fragments
  just to satisfy a number"). A real split needs the emitter restructured
  around the card sections first — its own task, not a move.

- 2026-08-10 (TASK-928): the `_mcp_reclaim.py` (935) entry was deleted rather
  than lowered — the facade is 47 over `_mcp_stranded` (458), `_mcp_reports`
  (309), `_mcp_pick` (189) and `_mcp_worklog` (138), named for what they own
  rather than keeping "reclaim" over four unrelated concerns. The gate was a
  real reclaim cycle, not an import check: a seeded five-task board with two
  cards stranded under dead sessions, run against a `git archive` of the
  pre-split tree — 34 keys covering reconcile, dry-run and live reclaim (which
  actually moves a card back to icebox), re-reclaim idempotence, pick, claim,
  daily, retro, WIP and work-log append, plus every private classifier. All
  identical; `daily.yesterday` matches as a set, its list order being a
  same-second `transitioned_at` tie. `board_os.mcp_tools` — the only real
  consumer — exports the same 122 names. Two traps the parity guard could not
  see and ruff did: an unused-import sweep deleted a function-LOCAL `import re`
  inside `_commits_referencing_batch` (the guard caught that one as EDITED), and
  `cos_task_daily` calls `cos_task_reclaim` across the new seam, which only
  `F821` surfaced. Silencing the repeated absolute-import blocks took mypy from
  4,478 to **4,474**.

- 2026-08-10 (TASK-928): the `backends/sqlite_backend.py` (1,052) entry was
  deleted rather than lowered — the facade is 31 and now declares only
  `SqliteBackend(_SqliteWriteMixin, _SqliteLinkMixin, _SqliteReadMixin)`. This
  one is a class, not a module of functions, so the split is by mixin over a
  `_sqlite_connection` base (204) that owns the write lock, the per-thread read
  pool, schema verification and the two row primitives; the write (294), link
  (249) and read (359) mixins each subclass it, which keeps `self._conn` and
  friends typed and cost mypy nothing — the count held at 4,478. The gate was a
  differential against a `git archive` of the pre-split tree over a seeded
  24-node/5-edge graph: 43 keys covering `GraphBackend` Protocol conformance,
  the full `dir(SqliteBackend)` surface, every read/write/link method, both the
  caller-supplied and standalone (own-connection, WAL, migrations) constructor
  paths, and the two raising paths — all identical. The delivered CLI was then
  smoke-run against the live 69,796-node graph (`graph-stats`, `graph-context`,
  `graph-references`, `graph-doctor`). No SQL moved out of the backend package,
  so the tool layer stays backend-agnostic.

- 2026-08-10 (TASK-928): the `tools/learning.py` (1,061) entry was deleted rather
  than lowered — the facade is 136 over four new siblings (`_learning_extract`
  329, `_learning_validate` 343, `_learning_generalize` 209, `_learning_suggest`
  169) alongside the four that already existed. The gate here is the tool surface
  plus behaviour: the live 87-tool MCP registry with every name, description and
  parameter list is byte-identical, `server.py --test` exits 0, and a functional
  differential against a `git archive` of the pre-split tree runs extract (three
  argument sets), suggest (three), generalize, both consolidation passes, the
  four `learn_validate` outcomes and `validate_surfaced_lessons` over one seeded
  corpus — 21 of 21 result keys identical, the 22nd being the module's incidental
  stdlib imports. One monkeypatch trap surfaced: five sites patched
  `tools.learning._read_session_id_for_validate`, which stops reaching
  `learn_validate` once that function resolves the name from its own module; they
  now target `tools._learning_validate`. Silencing the flat-sibling
  `import-not-found` class at each fallback import took mypy from 4,482 to
  **4,478** — the split paid for itself rather than costing.

- 2026-08-10 (TASK-928): the `routes/board.py` (1,086) entry was deleted rather
  than lowered — the facade is 89 over five parts (`_board_shared`,
  `_board_presence`, `_board_autospawn`, `_board_git`, `_board_tasks`,
  `_board_views`), largest 424. Same `APIRouter`-in-the-leaf shape `hub.py`
  needed: the router lives in `_board_shared`, no part imports a route module,
  and all seven import orders register 16 routes under both the `core.web.*` and
  `web.*` identities. Gated by a differential against a `git archive` of the
  pre-split tree — 24 live requests through `TestClient` (every route plus the
  400/404/traversal paths), byte-identical once the per-second
  `status_dwell_seconds` counter is normalized. One monkeypatch trap surfaced:
  `tests/test_hub_settings_auto_spawn.py` patched `_auto_spawn_enabled` on the
  board facade, which stops reaching `_auto_spawn_safe` once that function
  resolves the name from its own module; the patch now targets
  `_board_autospawn`, verified by confirming the old target no longer binds. The
  `PLR0913` per-file ignore moved from `board.py` to `_board_tasks.py` (12-arg
  `board_create`) rather than being widened, and mypy held at 4,482.

- 2026-08-10 (TASK-928): the `cognition.py` (1,237), `routes/hub.py` (1,217),
  `extractors/contracts.py` (1,196) and `doctor_extras.py` (1,121) entries were
  deleted rather than lowered — the facades are 81, 326, 310 and 85. Each gate
  was the runtime surface the file owns, captured before and after: the live
  87-tool MCP registry with every name, description and parameter list plus
  `server.py --test`; all 19 `/api/hub` routes plus ten live responses through a
  started Hub; the extractor over a pinned 1,270-file corpus plus a synthetic one
  covering all 25 scanner families, byte-identical; and `cos doctor` +
  `cos doctor --tokens` run end to end through both `cos` and `python -m
  cli.main`, 63 checks with matching severities. Two traps surfaced. `hub.py`
  could not keep the `APIRouter` in the facade: with `from .hub import router` in
  the part modules and the facade importing them back, importing any part module
  first raised `ImportError` on a partially-initialised sibling — a real failure a
  `-k` selection reproduced. The router and the `sys.path` bootstrap moved to the
  `_hub_shared` leaf, and all five import orders now register 19 routes.
  `tests/test_hub_init_route.py` patched `_run_cos_init` on the hub facade, which
  stops reaching the route once the route resolves the name from its own module;
  the patch now targets `_hub_init_routes`, verified by confirming the old target
  fails on the new layout.

- 2026-08-10 (TASK-928): `src/cli/main.py` (1,601 lines) was split into
  `_cli_paths` plus `init_command`, `adopt_command`, `install_commands` and
  `runtime_commands`; the entry was deleted rather than lowered — the facade is
  393 and now owns only the `cli` group and its registrations. The blast radius
  here is command registration, so the gate was a full CLI-surface snapshot
  (every command, its help line, and every option's flags and defaults) diffed
  before and after: 154 commands, byte-identical. Two monkeypatch traps surfaced
  and were fixed at the patch site, not papered over. Both predate the split and
  were only made visible by it: the autouse `_stub_initial_indexing` fixture
  patched `cli.main._initial_doc_index`, but the call site is
  `cli._init_phase`, so the stub never applied and every `cos init` in the suite
  ran the real doc + graph indexer; and six tests across three files reached the
  stdlib through `main.os` / `main.shutil` / `main.subprocess`, which worked only
  because the facade happened to import them. Both now patch the module that owns
  the call, which took `tests/test_cli.py` from 12m17s to 3m53s.

- 2026-08-10 (TASK-928): the `code_python.py` (1,454) and `code_go.py` (1,422)
  file-size entries were deleted rather than lowered — the facades are 242 and
  321. Both keep `extract()` and the whole pre-split public surface; the walkers
  live in leaves that import the uid module and never each other. Verified by a
  differential that runs the pre-split module and the facade over the same corpus
  in both parse modes and compares nodes, edges and parse errors byte-for-byte
  (Python: 158 sources x ast/tree-sitter; Go: 44 sources x tree-sitter/regex).
  `code_go`'s overlay handle is now bound by assignment rather than
  `import ... as`, so importers get an explicit export and mypy holds at 4,482.

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
  `ignore_missing_imports` glob, which at the time appeared inert. **Corrected
  2026-08-11:** the exact-name entries always worked; only the `_tools_*` entry
  was dead, because mypy's `*` matches a whole dotted component and never a
  prefix — so every split kept multiplying the class. Spelling the flat sibling
  names out dropped the local count 4,486 → **4,415**. Typing the trimmers'
  `dict`/`list` parameters had earlier taken it to 4,482; `BASELINE` moves only
  from a CI log, never a local run.

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

## External posture — the OpenSSF Scorecard (what it does and does not measure)

`scorecard.yml` publishes to `https://api.scorecard.dev/projects/github.com/kouroshez/coding-os`;
the README badge reads that API. The aggregate is a **risk-weighted mean** —
Critical checks weigh 10, High 7.5, Medium 5, Low 2.5, and a check scoring `-1`
(an internal error) is excluded from the mean entirely. Reproduced against the
2026-08-13 run: weighted sum 575 over weight 97.5 = **5.9**, matching the API.

That arithmetic is the point: it says which fixes move the number and which
cannot. Per-check impact on the aggregate, measured from the same run:

| Check | Was | Fix | Δ aggregate |
|---|---|---|---|
| Vulnerabilities (High) | 0 | 79 → 0 advisories; 72 of them were one stale `spring-boot-starter-parent` in a scaffold | +0.77 |
| Maintained (High) | 0 | nothing to do — the repo is <90 days old and the check refuses to score it | +0.77, on its own, in time |
| Code-Review (High) | 0 | needs reviewed PRs — see below | +0.77 |
| Fuzzing (Medium) | 0 | `fast-check` property tests (the check reads Go/Haskell/JS-TS/Erlang/C#, **not** Python) | +0.51 |
| Pinned-Dependencies (Medium) | 2 | 48 action refs pinned by SHA | +0.41 |
| Signed-Releases (High) | 8 | 8 is "signed"; 10 needs an `*.intoto.jsonl` provenance **asset** on the release | +0.15 |
| CII-Best-Practices (Low) | 0 | self-assessment at bestpractices.dev — passing 5, silver 7, gold 10 | +0.13 … +0.25 |
| SAST (Medium) | 8 | CodeQL must run on *every* commit, not most | +0.10 |
| Contributors (Low) | 0 | needs contributors from ≥3 companies — not reachable for a solo project | — |

**Measured outcome (2026-08-13, commit `b6704711`): 5.9 → 7.4.** Vulnerabilities
0→10, Fuzzing 0→10, Pinned-Dependencies 2→7. Signed-Releases stays at 8 until the
next release actually publishes the `*.intoto.jsonl` asset — the workflow change
cannot be observed before a release runs. Pinned-Dependencies stops at 7 rather
than 10 because the remaining warnings are `tests/golden/**` snapshots of the
template scaffolds, `install.sh`, and the pip/npm commands. The scaffold
Dockerfiles are left on tags **deliberately**: a consumer who runs `cos init`
should not inherit a base-image digest that was already stale the day it shipped,
and they are the ones who pin when they productionise.

### Branch-Protection must stay unscored while the repo is solo trunk-based

The check currently errors (`-1`, rendered as `?`) because the default
`GITHUB_TOKEN` cannot read classic branch-protection rules. The obvious fix —
hand `scorecard-action` a fine-grained PAT — **lowers the aggregate**. Scoring
is tiered and a tier must be satisfied in full before the next one counts:
Tier 1 (no force-push, no deletion) is met and is worth 3/10; Tier 2 requires at
least one review approval before merge, which trunk-based direct pushes do not
have. Entering the mean at 3 gives 597.5/105 = **5.69**, i.e. −0.2 for doing the
"right" thing. Adding the PAT is correct only in the same change that starts
requiring PR review — and 6/10 is where it merely breaks even.

Code-Review sits on the same fault line: it reads approvals over the last ~30
changesets, and this repo commits straight to `main` by design ([Rule 23](../governance/critical-rules.md#rule-23--trunk-based-git-workflow)).
1/30 approved is an accurate description of a one-maintainer trunk repo, not a
defect to engineer around. Scorecard's own docs say as much. Treat Code-Review,
Contributors, and Maintained as **facts about the project's shape**; the honest
ceiling while that shape holds is roughly 8.5, not 10.

### The 134 "code scanning alerts" are two populations

68 of them are the Scorecard SARIF upload re-reported as alerts
(`PinnedDependenciesID`, `MaintainedID`, `CodeReviewID`, …) — they clear when
the corresponding check score rises, and 61 were the unpinned actions. Only 66
were CodeQL findings about this codebase. Filter before triaging:

```bash
gh api "repos/kouroshez/coding-os/code-scanning/alerts?state=open" --paginate \
  --jq '.[] | select(.rule.id | test("ID$") | not) | [.number, .rule.id] | @tsv'
```

### Accepting an advisory that has no fix

`src/templates/go-fiber/scaffold/src/backend/osv-scanner.toml` is the worked
example: `GO-2026-5932` covers `golang.org/x/crypto/openpgp`, which is
unmaintained by design and therefore has no fixed version to move to. The
scaffold does not import it — proven by `osv-scanner --call-analysis=go`
reporting `called=false`, not by inspection — so the ID is ignored with that
evidence and an `ignoreUntil` date that forces re-review. An ignore without a
recorded reason and an expiry is just a suppressed alert.

## mypy promotion path

`[tool.mypy]` is lenient globally with per-package `strict = true` overrides
(`thinking_os.tools.*`, `graph_os.backends.*`, `board_os.workflow`). The ratchet
holds the total error count while packages are promoted one at a time: type a
package, add it to the strict list, lower `BASELINE`. mypy becomes a plain
zero-error gate when `BASELINE` reaches 0.

## Local mirror

`pre-commit` runs ruff, ruff-format, and shellcheck on staged files — the fast
subset. mypy, coverage, and the ratchets run in CI and via their commands above.
