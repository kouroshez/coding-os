<!-- domain:UNIVERSAL | layer:reference | ssot:true | updated:2026-06-04 -->
# Test Types — When Each Pays Off

> P: Pick the cheapest test that gives the confidence the change needs.
> R: Deciding what to test for a feature or bug fix.
> S: The repo's matrix-command discipline — [test-discipline.md](../../../rules/test-discipline.md).
> N: [SKILL.md](../SKILL.md), [test-review-checklist.md](../assets/test-review-checklist.md)

> Nav: [Skill](../SKILL.md)

## The pyramid (cost ↑, count ↓ as you go up)

| Type | Proves | Cost | Use a lot? |
|---|---|---|---|
| unit | one function/branch, pure logic | ms | yes — the base |
| integration | modules + a real dependency (DB, queue) | 10s–100s ms | moderate |
| contract | producer/consumer agree on a shape | fast | per API boundary |
| end-to-end | a full user journey across the stack | seconds | few, critical only |
| property-based | invariants over generated inputs | medium | for logic with many cases |
| mutation | the tests actually catch bugs | slow | periodic audit |
| fuzz | crashes on malformed input | slow | parsers, untrusted input |

Most confidence per dollar is at the unit + integration layer. End-to-end is the
tip ([end-to-end-testing](../../end-to-end-testing/SKILL.md)) — reserve it for
journeys that mean "product is down" if broken.

## Choosing for a change

- **Pure function / business rule** → unit (+ property-based if many input classes).
- **Repository / query / migration** → integration against a real DB (testcontainers / a test schema).
- **HTTP/MCP endpoint shape** → contract test (schema assertion) so consumers don't break.
- **Critical journey (checkout, login)** → one end-to-end.
- **Bug fix** → a unit/integration test that fails on the old code, passes on the fix (regression lock).

## Coverage is a floor, not a goal

```bash
python3 scripts/coverage_gate.py coverage.json --min 80    # CI gate
```

100% line coverage with no assertions proves nothing; 80% with error-path tests
proves a lot. Gate a **floor** to stop regressions, but chase *behavior* coverage
(every branch + every error path) not a number. Mutation testing
(`mutmut`/`stryker`) measures whether tests actually catch bugs — the real signal.

## Test quality (F.I.R.S.T)

Fast · Isolated (no shared state/order dependence) · Repeatable (no clock/network
flake) · Self-validating (a clear pass/fail, no manual inspection) · Timely
(written with the code). A test that needs another test to run first, or a fixed
clock it doesn't control, is a liability — fix it or delete it.
