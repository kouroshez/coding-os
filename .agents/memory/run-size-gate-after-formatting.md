---
name: run-size-gate-after-formatting
description: "ruff format adds lines, so run test_file_size_budget AFTER formatting — running it before gives a false green that CI catches."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 44379499-e86a-4baf-8fc4-1330b3aea96c
  modified: 2026-08-17T22:41:09.000Z
---

The file-size gate must be the **last** check before commit, run *after*
`ruff format` — never before it. `make lint` does not see it, so it is already
easy to miss (AGENTS.md's matrix calls this out), but the subtler trap is
ordering: formatting **adds** lines, so a file that passes at 497 can land at
501 after `ruff format` wraps a long call.

Observed 2026-08-17: `src/cli/hub_commands.py` passed
`tests/test_file_size_budget.py` (4 passed) when run right after the edit, then
`ruff format` split a `click.echo(...)` across lines and pushed it to 501. The
false green survived the commit and CI's "modularity safety net" job went red.
`cos doctor` caught it locally before the CI result came back — its
`quality.file_size` check is the cheapest way to re-verify after formatting.

**How to apply:** edit → `ruff check --fix` → `ruff format` → *then*
`uv run pytest tests/test_file_size_budget.py -q` (or `cos doctor`) → commit.
When a file does cross 500, split at an existing seam rather than inventing one:
`hub_commands.py`'s log-retention helper moved into `cli/_hub_paths.py`, which
already owned `_log_file()` and imports no sibling.

Related: [[dry-run-in-repo-before-trusting-units]] — same shape, a gate that
looks green because it was run against the wrong state.
