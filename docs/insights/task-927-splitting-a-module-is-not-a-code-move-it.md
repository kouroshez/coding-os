<!-- domain:INFRA | layer:reference | ssot:false | source:outcome_history#998 | updated:2026-08-10 -->
# TASK-927: Splitting a module is not a code move — it is a change to five different resolution mechanisms at once: import binding, monkeypatch target, decorator registration, fixture scope, and derived-artifact snapshots. Linters see none of them. Budget one verification run per mechanism, and put shared state in a leaf so no sibling ever imports another. The line count tells you a file is too big; only the question "what changes for a different reason?" tells you where to cut.

**Date:** 2026-08-10  
**Domain:** INFRA  
**Source task:** [TASK-927](../tasks/TASK-927-refactor-burn-down-the-oversized-file-backlog-largest-first-.md)

## Key Insight

Splitting a module is not a code move — it is a change to five different resolution mechanisms at once: import binding, monkeypatch target, decorator registration, fixture scope, and derived-artifact snapshots. Linters see none of them. Budget one verification run per mechanism, and put shared state in a leaf so no sibling ever imports another. The line count tells you a file is too big; only the question "what changes for a different reason?" tells you where to cut.

## What Failed

Across eleven god-file splits in one session, every single one broke in ways ruff and mypy could not see. Verifying by "it imports and lints" was wrong every time. The break modes, in the order they bit: (1) module-level globals left behind while the function that declares `global x` moved — the AST free-variable analysis reports nothing because `global x` marks the name as local; (2) monkeypatch transparency — tests patch the facade, but the moved implementation resolves the name through its OWN module globals, so half the call sites keep the real function; (3) CLI command registration — an ImportError in a command module silently drops a command from `cos --help` with no crash and no failing test, visible only by counting registered commands; (4) test fixtures — splitting a test file leaves `conn`/`project_conn` undefined in the new files, and pytest only reports "fixture not found" at run time; (5) derived artifacts — openapi.json, api-types.ts and tests/golden all drift and fail CI, not local runs.

## What Worked

A fixed sequence per split: find the seam by asking what changes for a different reason (not by line count); extract with an AST slicer; put anything two consumers need into a LEAF module that imports no sibling; have siblings reach facade helpers through the module object (`_cog._db_path()`) rather than by name, so a patch on the facade is visible everywhere; keep an explicit `__all__` on the facade for every private name a test reaches for; then verify by EXECUTING each entry point separately — flat import, package import, path-loaded import, the CLI command count, and the matrix suite — before pushing.

## Links

- Pattern: `learned_patterns#356` — retrievable via `cos_details`
- History: `outcome_history#998`
