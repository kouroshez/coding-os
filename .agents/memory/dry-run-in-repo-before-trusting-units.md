---
name: dry-run-in-repo-before-trusting-units
description: Green unit tests hid a false user-facing claim; running the command in the meta-repo itself exposed it in one line.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: db0f3780-7625-4641-9033-0cbc5a01ec6d
  modified: 2026-08-16T23:02:01.907Z
---

A new `cos update` path passed 8 unit tests and three scripted end-to-end scenarios on fresh `cos init` scaffolds, then printed "Kept your edited stack rule …" for four files nobody had edited the moment it ran **in the meta-repo**. Fixtures are born consistent; a real install carries history — here a mirror frozen months earlier — and that history is the input the tests did not have.

**Why:** the failure was ordering-dependent and only reachable when three files disagree in a way a fresh scaffold cannot produce. Both a passing suite and a passing scripted scenario read as proof; neither was.

**How to apply:** after a change to any `cos` command, run it (`--dry-run` first) inside `/Users/ciro/Files/Project/coding-os` itself before claiming done, and read every line it prints as a claim to verify. Running it there also surfaced three genuinely stale `.codex/rules/` files — the very bug the change existed to fix, present in the repo that ships it.

Related: [[measure-per-profile-never-summed]], [[sample-test-lint-gate-blindspot]].
