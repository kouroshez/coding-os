<!-- domain:CORE | layer:reference | ssot:false | source:outcome_history#999 | updated:2026-08-10 -->
# TASK-928: A facade split has a fourth silent breakage beyond import binding, monkeypatch target and decorator registration: type-checker re-export visibility. Green tests plus green ruff prove nothing about it — run the mypy ratchet before committing any split that re-exports moved names, and fix it with `X as X`, never by widening the baseline. Always pair the pre/post differential with a pre-vs-pre control run, otherwise nondeterministic tools read as regressions and a concurrent reindex silently invali

…[truncated]

**Date:** 2026-08-10  
**Domain:** CORE  
**Source task:** [TASK-928](../tasks/TASK-928-refactor-continue-the-oversized-file-burndown-code-php-workf.md)

## Key Insight

A facade split has a fourth silent breakage beyond import binding, monkeypatch target and decorator registration: type-checker re-export visibility. Green tests plus green ruff prove nothing about it — run the mypy ratchet before committing any split that re-exports moved names, and fix it with `X as X`, never by widening the baseline. Always pair the pre/post differential with a pre-vs-pre control run, otherwise nondeterministic tools read as regressions and a concurrent reindex silently invali

…[truncated]

## What Failed

Splitting a module and re-exporting the moved names through the old facade with a plain `from ._leaf import name  # noqa: F401`. Tests and ruff both stayed green, but mypy runs with no_implicit_reexport, so every sibling doing `from .graph import _ok` gained an `attr-defined` error — 50 new errors that a pytest run cannot see and that only the mypy ratchet catches.

## What Worked

The redundant-alias form `from ._leaf import _ok as _ok` marks the re-export explicit and clears every attr-defined error at once, with no `__all__` change and no semantic difference. Names already listed in the facade's `__all__` need no alias and no noqa; names absent from `__all__` still need `# noqa: F401` for ruff. Differential proof used a pinned tool-call corpus run against a `git archive` copy of the pre-split tree, plus a pre-vs-pre control run to separate genuine regressions from nondeterministic tools (community detection, PageRank).

## Links

- Pattern: `learned_patterns#357` — retrievable via `cos_details`
- History: `outcome_history#999`
