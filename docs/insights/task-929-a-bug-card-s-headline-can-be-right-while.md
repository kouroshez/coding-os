<!-- domain:INFRA | layer:reference | ssot:false | source:outcome_history#1016 | updated:2026-08-11 -->
# TASK-929: A bug card's headline can be right while its stated mechanism is wrong — the author inferred it by reading, not by running. Reproduce the exact claim first: if it does not reproduce, the bug is usually real but one call site over, and the failed probe is what points at it. Fixing the mechanism the card names would have shipped a no-op with a green test.

**Date:** 2026-08-11  
**Domain:** INFRA  
**Source task:** [TASK-929](../tasks/TASK-929-fix-the-reindex-dispatch-sqlite-self-deadlock-on-extractor-f.md)

## Key Insight

A bug card's headline can be right while its stated mechanism is wrong — the author inferred it by reading, not by running. Reproduce the exact claim first: if it does not reproduce, the bug is usually real but one call site over, and the failed probe is what points at it. Fixing the mechanism the card names would have shipped a no-op with a green test.

## What Failed

Trusting the card's stated mechanism. TASK-929 said the prune transaction was left open on extractor failure. A probe showed delete_nodes_for_file commits and in_transaction stayed False — the described repro did not reproduce at all.

## What Worked

Probing the neighbouring write path instead: a statement that raises INSIDE upsert_node left in_transaction=True and a second connection hit 'database is locked'. upsert_edge already had try/except rollback; upsert_node, delete_node and delete_nodes_for_file did not. One _write() context manager gave all writers the same invariant.

## Links

- Pattern: `learned_patterns#365` — retrievable via `cos_details`
- History: `outcome_history#1016`
