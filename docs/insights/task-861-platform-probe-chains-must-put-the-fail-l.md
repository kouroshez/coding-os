<!-- domain:n/a | layer:reference | ssot:false | source:outcome_history#943 | updated:2026-08-03 -->
# TASK-861: Platform-probe chains must put the FAIL-LOUD variant first: a probe that "succeeds with garbage" (GNU stat -f %m) poisons every fallback chain that trusts exit codes. When a CI failure is Linux-only, reproduce in a container with CI-faithful dependency resolution before touching code — three of seven "Linux" failures were actually fresh-latest-deps or env-tool differences, not the OS.

**Date:** 2026-08-03  
**Domain:** n/a  
**Source task:** [TASK-861](../tasks/TASK-861-fix-7-linux-only-full-sweep-failures-unmasked-once-the-ci-ga.md)

## Key Insight

Platform-probe chains must put the FAIL-LOUD variant first: a probe that "succeeds with garbage" (GNU stat -f %m) poisons every fallback chain that trusts exit codes. When a CI failure is Linux-only, reproduce in a container with CI-faithful dependency resolution before touching code — three of seven "Linux" failures were actually fresh-latest-deps or env-tool differences, not the OS.

## What Failed

Assuming `stat -f %m FILE 2>/dev/null || stat -c %Y FILE` is a safe cross-platform mtime probe. On GNU/Linux `stat -f` means "filesystem status", so the call EXITS 0 and prints multi-line filesystem info (treating %m as a file operand) — the GNU fallback never runs and every age computation silently breaks (stale git index.lock never reaped, orphan panels never GC'd). Also assumed "passes locally" covers CI: three of seven Linux-only failures were env-shape differences (starlette 1.3 _IncludedRouter route introspection, Linux MAX_ARG_STRLEN 128KiB per argv element, fresh-resolve dependency drift because uv.lock is gitignored).

## What Worked

Reproduce in a linux/arm64 Docker container with the same fresh `uv sync` CI does (plus jq+sqlite3 — CI runners preinstall them, containers don't), probe the exact primitive (`stat -f %m` on a file) to capture the failure mode, then order probes GNU-first: `stat -c %Y || stat -f %m || echo 0` — macOS `stat -c` fails loudly so the chain stays deterministic on both platforms. For route introspection use app.openapi()["paths"] instead of app.routes. For huge inputs to bash, feed stdin, never a single argv element.

## Links

- Pattern: `learned_patterns#336` — retrievable via `cos_details`
- History: `outcome_history#943`
