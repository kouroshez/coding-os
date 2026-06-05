<!-- domain:UNIVERSAL | layer:asset | ssot:false | updated:2026-06-04 -->
# Test Review Checklist

Run when adding tests or reviewing a PR's tests.

## Right type, right level
- [ ] Logic covered by unit tests; the dependency seam by integration; the journey by one end-to-end.
- [ ] No end-to-end test where a unit/integration test would give the same confidence cheaper.
- [ ] API/MCP boundaries have a contract test (shape can't silently drift).
- [ ] Bug fix ships with a regression test that fails on the old code.

## Quality (F.I.R.S.T)
- [ ] Fast — no unnecessary sleeps, real network, or full-stack spin-up for unit tests.
- [ ] Isolated — passes alone and in any order; no shared mutable state.
- [ ] Repeatable — clock/random/network controlled (no flake).
- [ ] Self-validating — explicit assertions, not manual inspection or print debugging.
- [ ] Error paths tested, not just the happy path (pairs with clean-code).

## Coverage
- [ ] `python3 scripts/coverage_gate.py <report> --min <floor>` → `pass`.
- [ ] Coverage is a floor against regressions, not the goal; branches + error paths covered.
- [ ] (Periodic) mutation testing confirms tests catch injected bugs.

## Repo discipline
- [ ] Ran the matrix-targeted command for what changed, not the full sweep (test-discipline.md).
