<!-- domain:CORE | layer:reference | ssot:false | source:outcome_history#996 | updated:2026-08-10 -->
# TASK-926: A module with dual import identity has FOUR ways to break when you split it, not one: flat import, package import, spec_from_file_location by path, and tests that read its source text. An import grep only finds the first two. Before splitting such a module, enumerate its consumers by all four mechanisms — and verify each entry point by running it, because a green suite on one identity proves nothing about the other.

**Date:** 2026-08-10  
**Domain:** CORE  
**Source task:** [TASK-926](../tasks/TASK-926-refactor-split-database-py-2917-lines-into-paths-the-append-.md)

## Key Insight

A module with dual import identity has FOUR ways to break when you split it, not one: flat import, package import, spec_from_file_location by path, and tests that read its source text. An import grep only finds the first two. Before splitting such a module, enumerate its consumers by all four mechanisms — and verify each entry point by running it, because a green suite on one identity proves nothing about the other.

## What Failed

Verifying the database.py split with the flat import path only — `python server.py --test` plus `pytest test_db.py`. Both exercise `import database` with the package dir on sys.path, so all four downstream break modes stayed invisible until CI: (1) `from thinking_os.database import project_root` in the CLI hit ModuleNotFoundError on the bare sibling import, (2) tests importing moved private helpers via `core.thinking_os.database`, (3) a test loading database.py by file path with spec_from_file_location and reading `_migrate_v13_board_os` off it, (4) two tests that read database.py's SOURCE TEXT looking for `_ROOT_MARKERS` and a model-id literal. Grepping for `from database import` found none of 2-4.

## What Worked

Wrapping the new sibling imports in try (relative) / except ImportError (flat) so both identities resolve, then verifying each entry point separately by execution: server.py --test, `from thinking_os.database import ...`, cos board, cos doctor. For the consumers, following the private helpers to their new home rather than re-exporting 53 private names through the facade.

## Links

- Pattern: `learned_patterns#355` — retrievable via `cos_details`
- History: `outcome_history#996`
