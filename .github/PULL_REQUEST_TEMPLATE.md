<!--
Thanks for contributing to coding-os. Fill every section. A PR that
explains *why* gets reviewed faster than one that only shows *what*.
-->

## What

<!-- One paragraph: what does this PR change? -->

## Why

<!-- The motivation. Link the issue: Closes #NN / Refs #NN -->

## Layer touched

<!-- Tick all that apply. -->

- [ ] `src/core/` — agent-agnostic kernel
- [ ] `src/adapters/` — a specific agent
- [ ] `src/templates/` — a specific stack
- [ ] `src/cli/` — the `cos` command
- [ ] `src/core/web/` — the Hub (backend or UI)
- [ ] `docs/` — documentation only
- [ ] CI / tooling / repo config

## Test plan

<!--
Which matrix-targeted command(s) did you run? Paste the result.
See src/core/rules/test-discipline.md for the matrix.
-->

```
# e.g. uv run --extra rag pytest src/core/thinking_os/tests/ -q
```

## Checklist

- [ ] Branch is up to date with `main`.
- [ ] Conventional Commit subject + body explain the **why**.
- [ ] Matrix-targeted tests pass locally.
- [ ] `make verify-hooks` passes (if `src/core/hooks/` touched).
- [ ] `make docs-lint` passes (if `docs/**/*.md` touched).
- [ ] `CHANGELOG.md` NOT edited (release-please generates it from commit titles).
- [ ] New MCP tool wrapped with `@safe_tool` returning `ok / fail` (Rule 13).
- [ ] New hook registered in `src/core/hooks/registry.yaml` + templates regenerated.
- [ ] No secrets, no absolute developer paths, no client-specific identifiers.
- [ ] One PR = one concern (refactors split out).

## Notes for the reviewer

<!-- Anything that needs special attention, known limitations, follow-ups. -->
