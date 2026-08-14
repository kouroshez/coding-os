<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-25 -->
# Risk Register

Purpose: Canonical list of active project, architecture, and workflow risks that still require mitigation or follow-up.
Read when: Planning work, reviewing blind spots, or deciding whether a task can proceed safely.
Skip when: The task is tightly scoped and all relevant risks are already captured in the task file.
Read next: Relevant ADR in `../architecture/adr/` or the domain architecture doc.

> Nav: [Docs Index](../00-index.md) | [ADR Index](../architecture/adr/00-index.md)

## Active Risks

<!-- Format (review-by + tracking are REQUIRED — `make docs-lint` flags a missing
     field or a past-due review-by so tolerated risk is re-triaged, not accreted):
       - `RISK-NNN` Description. owner: <name> · review-by: YYYY-MM-DD · tracking: TASK-NNN | #issue
     Example:
     - `RISK-001` Backup automation needs an owner before production. owner: ops · review-by: 2026-09-01 · tracking: TASK-123
-->

- `RISK-001` Bus factor 1 — 2,655 of 2,690 commits are from one maintainer, who also holds the only PyPI publish path. owner: maintainer · review-by: 2026-11-01 · tracking: #41
- `RISK-002` No external production validation; every effectiveness claim is self-measured. owner: maintainer · review-by: 2026-11-01 · tracking: #41
- `RISK-003` 16 of 27 advertised stacks have no real toolchain CI (scaffold-verify covers node/python/go only), so "advertised" is not "proven". owner: maintainer · review-by: 2026-10-01 · tracking: TASK-975
- `RISK-004` Nightly slow suite is non-gating pending order-independence; a regression it catches can still reach `main`. owner: maintainer · review-by: 2026-10-01 · tracking: TASK-974
- `RISK-005` Hub binds loopback without authentication by default and does not refuse a non-loopback bind when `COS_HUB_TOKEN` is unset. owner: maintainer · review-by: 2026-10-01 · tracking: TASK-977

> **Risk vs Known Limitation.** A *limitation* is a bounded property we accept
> and document ([KNOWN_LIMITATIONS.md](../../KNOWN_LIMITATIONS.md)); a *risk* is
> a limitation whose blast radius is not yet bounded and which therefore needs
> an owner and a review date. Coverage at 63% is a limitation. "A defect class
> can reach `main` because the suite that would catch it does not gate" is a
> risk. When a risk is bounded, move it to KNOWN_LIMITATIONS and drop it here.

## Usage Rules

- Risks stay here while active.
- Once resolved, move the resolution into the relevant ADR, architecture doc, or change log entry and remove or downgrade the risk.
- Historical risk analysis belongs in archive docs, not active architecture indexes.
- Each risk needs an ID (`RISK-NNN`), a one-line description, and ideally an owner and mitigation plan.
- Each risk MUST carry a `review-by: YYYY-MM-DD` date and a `tracking:` ref (task or issue); `make docs-lint` flags a missing field or a past-due `review-by` so a stale risk is re-triaged, not silently accumulated.
