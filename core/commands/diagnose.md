Run system health diagnostics and interpret the results.

Steps:
1. Run `make cos-health` to check coding-os system health
2. Run project-specific diagnostics if available (make diagnose)
3. For each FAIL item: explain what's wrong and give the exact fix command
4. For each WARN item: explain if it matters for the current environment
5. Summarize: what's healthy, what needs attention, and prioritized fix order
