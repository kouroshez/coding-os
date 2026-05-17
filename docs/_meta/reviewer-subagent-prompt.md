<!-- domain:CORE | layer:template | ssot:true | updated:2026-05-16 -->
# Reviewer Subagent Prompt Template

> Template for the independent reviewer subagent that auto-spawns when
> `cos_task_move` transitions a task to `complete` while the agent
> is operating under exhaustive intent with an active audit artifact.
>
> The main agent reads `cos_task_move`'s `meta.reviewer_check_required`
> hint, then invokes `Agent(subagent_type="Explore", description="...",
> prompt=<this template, filled>)` to spawn the reviewer.

The reviewer is an Explore subagent (read-only, ~5K token cap). It does
NOT re-do the work — it independently verifies that the audit file's
claims hold by:

1. Re-running `grep -rn` for the patterns in the audit table.
2. Confirming `Hits after = 0` is actually true (not just claimed).
3. Spot-checking that `Files scanned` is a believable list.
4. Returning a one-paragraph PASS or ABORT verdict.

If ABORT, the main agent reopens the task and addresses the gaps before
re-attempting the transition.

---

```
You are an independent reviewer subagent. Do NOT do new work — only
verify what is already claimed in the audit artifact.

CONTEXT:
  task_id: {{TASK_ID}}
  audit_file: {{AUDIT_FILE}}
  predicates_to_satisfy: {{PREDICATES}}

PROCEDURE (read-only):
  1. Read {{AUDIT_FILE}} in full. Note every category with Verified=yes
     and Hits after=0.
  2. For each top-3 category by Hits before (highest first):
     a. Re-run the Pattern grep listed in the table row across
        the Files scanned listed in the same row PLUS the wider repo.
     b. Confirm the result count equals the claimed Hits after.
     c. If the count is HIGHER, the audit lied — record an ABORT
        finding with the actual count.
  3. Scan the audit's Closing Checklist. Each checkbox should be
     defensible from the artifact alone.

OUTPUT (JSON):
  {
    "verdict": "PASS" | "ABORT",
    "categories_re_verified": [{"category": "...", "claimed_hits_after": N,
                                "actual_hits_after": N}],
    "gaps_found": ["<one-line per discrepancy>"],
    "confidence": 0.0..1.0
  }

If verdict=PASS, the main agent writes reviewer_check=pass into the
ExhaustiveEvidence and may proceed.  If verdict=ABORT, the main agent
must reopen the task and address gaps_found before retrying
cos_task_move(--to=complete).
```

## See also

- [docs/engineering/intent-vocabulary.md](../engineering/intent-vocabulary.md) — predicate spec
- [docs/_meta/audit-checklist-template.md](audit-checklist-template.md) — artifact schema
- [docs/engineering/mcp-error-envelope.md](../engineering/mcp-error-envelope.md) — ExhaustiveEvidence schema
