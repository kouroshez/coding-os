<!-- domain:INFRA | layer:reference | ssot:false | source:outcome_history#1055 | updated:2026-08-14 -->
# TASK-971: Source-tree green is not distribution green, and a packaging gate is worthless until proven red — setuptools' reused ./build staging dir silently makes it pass on files the config no longer ships. Any check of an artifact must delete the staging dir, build with --no-cache, and be verified against the pre-fix tree; then install the artifact and RUN it, because import-time failures like a package missing from pyproject only appear outside the source tree.

**Date:** 2026-08-14  
**Domain:** INFRA  
**Source task:** [TASK-971](../tasks/TASK-971-ship-the-hub-spa-inside-the-wheel-so-a-pypi-install-renders-.md)

## Key Insight

Source-tree green is not distribution green, and a packaging gate is worthless until proven red — setuptools' reused ./build staging dir silently makes it pass on files the config no longer ships. Any check of an artifact must delete the staging dir, build with --no-cache, and be verified against the pre-fix tree; then install the artifact and RUN it, because import-time failures like a package missing from pyproject only appear outside the source tree.

## What Failed

Trusting a green wheel-contents test. It passed against deliberately reverted packaging config because setuptools stages into ./build and REUSES that directory — the wheel inherited files the current config no longer included. The first fresh-install smoke test also errored on its first readiness poll because its HTTP helper raised on connection-refused instead of treating it as a status.

## What Worked

Deleting ./build and passing --no-cache inside the test fixture, then running the same test against `git show HEAD:pyproject.toml` to confirm it goes red. The end-to-end smoke (install the wheel into an empty venv, boot the ASGI app directly rather than via the singleton `cos hub start`, fetch / and a referenced /assets/* bundle) then surfaced two further defects no static check had: logging_os was absent from packages/package-dir, and a route rebuilt sys.path from source-tree depth.

## Links

- Pattern: `learned_patterns#374` — retrievable via `cos_details`
- History: `outcome_history#1055`
