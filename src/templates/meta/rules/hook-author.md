---
description: Rule for authoring shell hooks under src/core/hooks/. Enforces SSOT registration, $COS_* env discipline, fail-closed exception handling, shellcheck compliance, and the regen pipeline that propagates a new hook to every adapter.
globs: "src/core/hooks/*.sh,src/core/hooks/_helpers/*.py,src/core/hooks/registry.yaml"
alwaysApply: false
---

# Hook Authoring Rule

The full anatomy, helper pattern, state-file table, debounce recipes, and test harness live in `Skill hook-authoring` — load it before touching `src/core/hooks/**`. This rule keeps only the non-negotiables:

1. `set -euo pipefail` + `source cos-env.sh` at the top (Rule 3); fail-open stub for `cos_log_hook`.
2. Never hardcode `.claude/` — use `$COS_AGENT_DIR` / `$COS_STATE_DIR` / `$COS_PANEL_DIR` (Rule 1, P2).
3. Register ONCE in [src/core/hooks/registry.yaml](../../../core/hooks/registry.yaml) (SSOT), then `make regen-adapter-templates` + re-run the adapter installer.
4. Exit codes: `0` = pass/warn (stderr shown), `2` = BLOCK with a remediation message. Nothing else.
5. Enforcement/safety hooks fail closed; observability/reminder hooks fail open (always exit 0).
6. >~30 lines of logic or any parsing → Python helper in `_helpers/` (bash heredoc deadlock, Rule 8). `grep -oE` needs `|| true` under pipefail.
7. Codex dispatcher: if the event is coalesced (UserPromptSubmit / Stop / SessionStart), also add the script to `src/adapters/codex/adapter.yaml::hook_dispatchers` + the dispatch loop.

Verify: `make verify-hooks` (syntax + shellcheck) · `make test-hooks` (smoke) · manual: pipe synthetic JSON, assert exit code + stderr.
