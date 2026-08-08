<!-- domain:CORE | layer:reference | ssot:false | source:outcome_history#977 | updated:2026-08-08 -->
# TASK-898: Never trust ruff unsafe fixes on SIM118/SIM401 patterns: they assume dict semantics, but sqlite3.Row and dict-like wrappers (__contains__/__getitem__ without .get) break at runtime. Always run the affected test suites after --unsafe-fixes before committing.

**Date:** 2026-08-08  
**Domain:** CORE  
**Source task:** [TASK-898](../tasks/TASK-898-ruff-hardening-fix-b023-b904-b905-autofix-sweep-make-ruff-ch.md)

## Key Insight

Never trust ruff unsafe fixes on SIM118/SIM401 patterns: they assume dict semantics, but sqlite3.Row and dict-like wrappers (__contains__/__getitem__ without .get) break at runtime. Always run the affected test suites after --unsafe-fixes before committing.

## What Failed

ruff --unsafe-fixes silently rewrote dict-like access on non-dict objects: sqlite3.Row keys()-check became row.get() (Row has no .get) and StackLoadResult ternary became stacks.get() — 65 tests failed across learning/init/render.

## What Worked

Reverting the two sites to keys()/ternary form with noqa: SIM118/SIM401 + a why-comment, then re-running the full sweep to green.

## Links

- Pattern: `learned_patterns#346` — retrievable via `cos_details`
- History: `outcome_history#977`
