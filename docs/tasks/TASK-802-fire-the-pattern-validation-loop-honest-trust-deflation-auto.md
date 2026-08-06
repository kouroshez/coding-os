---
id: TASK-802
title: "Fire the pattern-validation loop + honest trust deflation (auto_compose\u2192learn_validate; re-point tier/decay/fading/digest to real times_validated)"
swimlane: "thinking_os"
kind: feature
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-07-05
started: 2026-07-06
completed: 2026-07-06
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-802: Fire the pattern-validation loop + honest trust deflation (auto_compose→learn_validate; re-point tier/decay/fading/digest to real times_validated)

**Outcome (one sentence):** Real pattern validations actually fire and flow into `times_validated`, and the trust-reading surfaces (pattern_tier, decay anti-forgetting, fading resurrection, digest) switch to the honest signal — completing the second half of the counter split (TASK-801).

## Read First
- src/core/thinking_os/auto_compose.py (~194 — populate `.learn-suggestions` for formal tasks, not only COMPLICATED/COMPLEX)
- src/core/hooks/session-context.sh (~145 — stop truncating `.learn-suggestions` before task-done consumes it)
- src/core/hooks/remind-learn-validate.sh · src/core/thinking_os/scheduled/auto_validate_lessons.py (the validate chain)
- src/core/thinking_os/tools/learning.py (`pattern_tier`:878, fading filter ~1393, `_boost_success`/`_penalize`) · src/core/thinking_os/decay.py (times_validated>=5 protection) · src/core/thinking_os/digest.py (~247)

## Scope (the deferred half of C — pairs deflation with its refill)
1. **Wire validation firing:** auto_compose populates `.learn-suggestions` for any formal task; session-context.sh stops truncating it; remind-learn-validate → auto_validate_lessons → `learn_validate` → `pattern_validations` records → `_boost_success`/`_penalize` move `times_validated`.
2. **Honest deflation (do WITH #1 so trust can be re-earned):** reset historical `times_validated` to 0 (baseline pattern_validations=0 — nothing real is lost); re-point the occurrence-reading consumers to `times_seen`: fading filter (learn_suggest), decay anti-forgetting (`effective_decay_rate`), digest listing. Keep `pattern_tier` on `times_validated` so "Trusted" now means genuinely validated.
3. Reconsider the monotonic `max(existing, new)` confidence at `_upsert_pattern` so LTD can actually lower a bad belief.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a formal task closes after using a suggested pattern,
- **When** the validate chain runs,
- **Then** `pattern_validations` gains a row and the pattern's `times_validated` increments; a penalized pattern's confidence drops; `pattern_tier` shows Trusted only for genuinely-validated patterns; decay/fading/digest read `times_seen` for established-ness; and the thinking_os matrix + `make verify-hooks` stay green.

## Dependencies
- TASK-801 (counter split — done): `times_seen` exists and carries occurrences.

## Work Log
- 2026-07-06 [claude]: Edit learning.py
- 2026-07-06 [claude]: Edit learning.py
- 2026-07-06 [claude]: Edit decay.py
- 2026-07-06 [claude]: Edit decay.py
- 2026-07-06 [claude]: Edit decay.py
- 2026-07-06 [claude]: Edit decay.py
- 2026-07-06 [claude]: Edit decay.py
- 2026-07-06 [claude]: Edit decay.py
- 2026-07-06 [claude]: Edit test_decay.py
- 2026-07-06 [claude]: Edit digest.py
- 2026-07-06 [claude]: Edit database.py
- 2026-07-06 [claude]: Edit database.py
- 2026-07-06 [claude]: Edit auto_compose.py
- 2026-07-06 [claude]: Edit auto_compose.py
- 2026-07-06 [claude]: Edit auto-compose-roles.sh
- 2026-07-06 [claude]: Edit test_learning.py
- 2026-07-06 [claude]: Edit test_digest.py
- 2026-07-06 [claude]: Edit test_digest.py
- 2026-07-06 [claude]: Edit test_db.py
- 2026-07-06 [claude]: Edit test_learning.py
- 2026-07-06 [claude]: Edit test_compose_trace_wiring.py
- 2026-07-06 [claude]: Edit learning-extraction.md
- 2026-07-06 [claude]: Edit learning-extraction.md
- 2026-07-06 [claude]: Edit test_digest.py
- 2026-07-06 [claude]: commit 300a8fdc3e — feat(learning): fire the validation loop for formal tasks + honest trust deflation
- 2026-07-06 [claude]: Implemented all 3 parts. Part 1 (firing): auto-compose-roles.sh + auto_compose.py now run learn_suggest recall for…
