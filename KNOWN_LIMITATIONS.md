# Known Limitations

Honest constraints as of 2026-08-08. Each entry says what holds today and where
the ratchet (if any) lives. Gate detail: [docs/engineering/ci-gates.md](docs/engineering/ci-gates.md).

## Type safety

- mypy runs as a **count-ratchet**, not a zero-error gate: 4,649 baseline
  errors across the kernel (`src/scripts/mypy_ratchet.py`). Strict typing is
  enforced only on `thinking_os.tools.*`, `graph_os.backends.*`, and
  `board_os.workflow`; the rest is promoted package-by-package.

## Code health baselines

- 101 functions across 40 files exceed the complexity thresholds
  (C901>20 / branches>24 / args>10 / statements>100) and are baselined in
  `pyproject.toml` per-file-ignores — new code is gated, old code is a
  shrink-only burndown.
- Coverage is 63% measured, gated at `fail_under = 62`; the target ratchet is
  70 → 80. PRs additionally need ≥80% coverage on changed lines (diff-cover).
- 48 files exceed 800 lines, the largest being `thinking_os/server.py` at
  3,159. Each is pinned at its current size by the per-file ratchet in
  `tests/test_file_size_budget.py`, so they can shrink but never grow, and no
  new file may cross 800 lines. Paying the debt down is unscheduled.

## Platform

- Primary platform is macOS: scheduled jobs use launchd plists, and path
  handling special-cases `/tmp ↔ /private/tmp`. Linux works for CI and the
  kernel; Windows is unsupported.
- The full test suite is ~4,850 tests / ~28 min wall-clock; contributors are
  expected to run the per-subsystem matrix commands, not the sweep.

## Agent-runtime parity

- Hook parity is bounded by each runtime's capabilities: Codex has no
  `PostToolUseFailure` event and no `Skill` matcher
  ([adapter-parity.md](docs/engineering/adapter-parity.md)). Protected
  workflows (gates, doc-anchor) need a runtime where hooks fire; plain human
  editing relies on the installable git hooks instead.

## Knowledge graph

- Static extraction cannot resolve module-alias attribute calls
  (`import database as db; db.init_db()`) or calls inside string literals, so
  `cos_graph_references` is a lower bound for those; security-critical sweeps
  pair the graph with grep
  ([graph-hallucination-cures.md](docs/engineering/graph-hallucination-cures.md)).
- Edge confidence is heuristic; low-confidence edges are surfaced in a
  separate tier rather than hidden, but they can still be wrong.

## Benchmarks

- The third-party token benchmark covers two pinned repos (requests, fastapi)
  and measures token cost with the production chars/4 estimator — not
  wall-clock speed, not answer quality
  ([third-party-token-bench.md](docs/engineering/third-party-token-bench.md)).

## Project maturity

- Single maintainer (bus factor 1). Mitigations: GOVERNANCE.md, quality gates
  as reviewer-of-record, agent-reproducible workflow in CONTRIBUTING.md.
- `0.x`: no stability guarantee yet — the surface being frozen for 1.0 is
  [docs/governance/stability-contract.md](docs/governance/stability-contract.md).
- No production deployments outside the maintainer's own projects yet; the
  design-partner program is open (see the pinned issue).
