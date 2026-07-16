---
id: TASK-188
title: "Enterprise de-Persianization audit make product English-default not Persian-hardcoded"
swimlane: core
kind: chore
epic: agent-economy
labels: [ready]
status: archive
priority: P2
appetite: "1d"
created: 2026-06-06
started: 2026-06-05
completed: 2026-06-05
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-188: Enterprise de-Persianization audit make product English-default not Persian-hardcoded

**Outcome (one sentence):** Product layer reads as English-default for a global consumer base — presentation (banners, examples, comments, docs) is English, functional heuristic classifiers are language-neutral, and the commit prompt-leak guard's non-Latin detection is KEPT as a safety feature.

## Read First

- docs/engineering/agent-economy-and-identity-roadmap.md (Phase 4)
- docs/engineering/intent-vocabulary.md (the FA/EN SSOT)

## Why this is an epic, not a quick edit

~24 product files under `src/core` carry Persian, spanning three very different classes that must NOT be swept uniformly:

1. **Presentation (safe to English-ify):** Persian examples/comments in `transparency-banner.md`, primer cards, doc prose. Low risk — convert to English.
2. **Functional heuristic classifiers (needs a product decision + golden/test regen):** FA keyword matching in `detect-exhaustive-intent.sh`, `nudge-thinking-os.sh`, `classify-task-mode.sh`, and `intent-vocabulary.md`. These are bash pre-classifiers; the LLM agent itself understands any language regardless. Removing FA keywords makes them English-default; doing so changes hook output → triggers `make golden-capture` across sections and may touch tests.
3. **Safety feature (KEEP — do not remove):** `check_commit_message.py` detects Persian/Arabic char runs to BLOCK user-prompt leakage into commits. That is *aligned* with "nothing Persian in the product" — it keeps Persian OUT of git history. Keep it.

## Decision required before starting

English-only heuristics (simplest; loses keyword pre-detection for non-English prompts, but the LLM still comprehends them) **vs** lightweight multilingual heuristics (more robust for the "or other languages" consumer base, more maintenance). Recommendation: **English-only heuristics** — the deterministic hooks are belt-and-suspenders over the model's own comprehension, so English-default keeps the product professional without a multilingual-maintenance burden.

## Verification (when done)

Per-file matrix for each touched class + `make golden-capture` for hook changes + full `pytest tests/ -q` (audit-class) + grep proves 0 Persian outside the kept safety guard.

## Work Log
- 2026-06-06 [claude]: Status transitioned to complete via cos task-done.
