---
id: TASK-998
title: "governance: fix the eight defects the adversarial review confirmed before pushing"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: complete
priority: P1
appetite: 1d
created: 2026-08-17
started: 2026-08-16
completed: 2026-08-16
agent_session: ses-claude-20260814-120316-413b
depends_on: []
blocked_by: []
references: []
---
# TASK-998: governance: fix the eight defects the adversarial review confirmed before pushing

**Outcome (one sentence):** Nothing in the unpushed range publishes a false remediation, a false credential green, or a stack rule that silently stays stale in a second adapter.

## Read First
- src/scripts/ablation_probe.py

## Repro Steps
1. `ANTHROPIC_MODEL=claude-opus-5 uv run python src/scripts/ablation_probe.py --preflight` printed `[OK] model credential: present: ANTHROPIC_MODEL` — a non-secret config var read as a key, so the probe would call itself fundable with no credential at all.
2. The same command printed `[OK] container runtime: 4.8 GiB total` on a machine with ~1.5 GiB actually free, because MemTotal was reported where headroom was meant.
3. In a project where two adapters hold the same untouched stack rule, `cos update` printed both `Refreshed` and `Kept` for one file: the shared mirror advanced inside the per-adapter pass, so the first adapter refreshed and every later one read its own untouched copy as a user edit, permanently.
4. The documented fix for the failing control-agent check was `uvx mini-swe-agent`, which installs nothing into the interpreter the check imports from — following the doc leaves the check failing.

Expected: a preflight that fails on a machine it cannot run on, and a refresh that moves every adapter.
Actual: two false greens and one adapter frozen stale forever.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ANTHROPIC_MODEL exported and no real key, **When** preflight runs, **Then** the credential check still fails.
- **Given** two adapters holding the same untouched rule, **When** cos update refreshes, **Then** every adapter's copy moves and no file is both refreshed and kept.
- **Given** a stale or absent mirror, **When** cos update runs, **Then** it reports the baseline is missing rather than asserting the user edited the file.

## Work Log
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit ablation_probe.py
- 2026-08-17 [claude]: Edit _init_scaffold.py
- 2026-08-17 [claude]: Edit _init_scaffold.py
- 2026-08-17 [claude]: Edit _init_scaffold.py
- 2026-08-17 [claude]: Edit update.py
- 2026-08-17 [claude]: Edit update.py
- 2026-08-17 [claude]: Edit update.py
- 2026-08-17 [claude]: Edit test_stack_rule_refresh.py
- 2026-08-17 [claude]: Edit ablation-protocol.md
- 2026-08-17 [claude]: Edit ablation-protocol.md
- 2026-08-17 [claude]: Edit AGENTS.md
- 2026-08-17 [claude]: commit cf62f5d26c — fix(eval): stop the preflight greening on config vars and VM total
- 2026-08-17 [claude]: Edit TASK-998-governance-fix-the-eight-defects-the-adversarial-review-conf.md
- 2026-08-17 [claude]: Status transitioned to complete via cos task-done.
