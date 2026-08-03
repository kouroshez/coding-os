<!-- domain:INFRA | layer:reference | ssot:false | source:outcome_history#941 | updated:2026-08-02 -->
# TASK-859: When an enforcement chain silently never fires, check the CLASSIFIER at its head before the enforcer at its tail — a language/locale-blind classifier (English-only verb regex vs Persian operator) disables every downstream gate while each gate looks correct in isolation. And forensics shortcut: task_status_history reason=NULL means a bare transition() caller; sync writes 'file-sync', reclaim writes 'reclaim:…' — the reason field fingerprints the writer.

**Date:** 2026-08-02  
**Domain:** INFRA  
**Source task:** [TASK-859](../tasks/TASK-859.md)

## Key Insight

When an enforcement chain silently never fires, check the CLASSIFIER at its head before the enforcer at its tail — a language/locale-blind classifier (English-only verb regex vs Persian operator) disables every downstream gate while each gate looks correct in isolation. And forensics shortcut: task_status_history reason=NULL means a bare transition() caller; sync writes 'file-sync', reclaim writes 'reclaim:…' — the reason field fingerprints the writer.

## What Failed

Assuming task-lifecycle enforcement was language-neutral and that zombie icebox cards were agent negligence. Also: blaming sync/tests/hub for unattributed board reverts before checking hub request metrics (zero move requests exonerated it) and the NULL-reason signature (sync always writes a reason — only a bare transition() leaves NULL).

## What Worked

Evidence-first chain: task_status_history timestamps proved TASK-843 was created AFTER its work (born-zombie); classify-task-mode.sh verb regexes were English-only despite a Bilingual header comment, so every Persian implementation prompt ran adhoc and enforce-task-start exempted it; enforce-task-start's own block message advertised the .task-current manual bypass; reconcile/warn hooks had no icebox-with-completion-evidence detector. Fixed all four surfaces in place + hub human-actor attribution on move/reposition.

## Links

- Pattern: `learned_patterns#335` — retrievable via `cos_details`
- History: `outcome_history#941`
