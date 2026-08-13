<!-- domain:CORE | layer:reference | ssot:false | source:outcome_history#1043 | updated:2026-08-13 -->
# TASK-962: Fixing a static-analysis finding and clearing its alert are two separate jobs in this repo. CodeQL does not model safe_segment, _safe_seg, or Path.resolve().relative_to() as barriers, so a correct guard often leaves the alert open — and conversely an alert can close for the wrong reason (a line shift closes the old id and opens a new one, which reads as 'fixed' if you only count). Before claiming a security fix landed, re-query the API by rule id and compare, never by alert count. And when a dis

…[truncated]

**Date:** 2026-08-13  
**Domain:** CORE  
**Source task:** [TASK-962](../tasks/TASK-962-triage-the-remaining-60-codeql-alerts-path-injection-stack-t.md)

## Key Insight

Fixing a static-analysis finding and clearing its alert are two separate jobs in this repo. CodeQL does not model safe_segment, _safe_seg, or Path.resolve().relative_to() as barriers, so a correct guard often leaves the alert open — and conversely an alert can close for the wrong reason (a line shift closes the old id and opens a new one, which reads as 'fixed' if you only count). Before claiming a security fix landed, re-query the API by rule id and compare, never by alert count. And when a dis

…[truncated]

## What Failed

Adding hashlib's usedforsecurity=False to silence CodeQL py/weak-sensitive-data-hashing: the query classifies the INPUT as an id, not the algorithm's intent, so all three alerts reopened on the shifted line numbers and looked fixed only because the old alert numbers had auto-closed. Separately, assuming a correct guard clears the alert: cognition.py already validated segments with _safe_seg and server.py:220 already did resolve().relative_to() containment, and both were still reported.

## What Worked

Switch the algorithm (sha1 -> sha256) rather than annotate it — safe here because all three digests were derived content-addresses (recomputed per run or self-healing change-detection), never stored uids. For the barriers CodeQL cannot model, keep the guard AND write a mutation-checked regression test, then dismiss the alert naming that test as the evidence.

## Links

- Pattern: `learned_patterns#370` — retrievable via `cos_details`
- History: `outcome_history#1043`
