Run system health diagnostics and interpret the results.

Steps:
1. Run `cos doctor` — deep health check (scaffold, DB schema, adapter, symlinks). Use `cos health` for a fast summary if `doctor` is too slow.
2. For each FAIL item: explain what's wrong and give the exact fix command
3. For each WARN item: explain if it matters for the current environment
4. Summarize: what's healthy, what needs attention, and prioritized fix order
