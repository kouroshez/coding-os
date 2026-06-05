<!-- domain:META | layer:asset | ssot:false | updated:2026-06-04 -->
# Hook Authoring Checklist

Run before shipping a new or modified hook. Full procedure: docs/playbooks/hook-authoring.md.

## Scaffold + structure
- [ ] `bash scripts/new_hook.sh --name <id> --category <c>` used (or matches its shape).
- [ ] `set -euo pipefail` at the top.
- [ ] Sources `cos-env.sh` (Rule 3); `cos_log_hook` enter/ok/warn calls.
- [ ] Reads stdin via `cos_read_stdin_bounded`; `jq` with safe defaults.

## Agent-agnostic (Rule 1, P2)
- [ ] Never hardcodes `.claude/` — uses `$COS_AGENT_DIR`/`$COS_STATE_DIR`/`$COS_PANEL_DIR`.
- [ ] `grep -oE`/`grep -c` wrapped with `|| true` (no pipefail kill on zero match).
- [ ] No `$(python3 - <<HEREDOC)` — extract to `_helpers/<name>.py` (Rule 8).
- [ ] `Path(...).resolve()` before `relative_to()` (Rule 5) in any helper.

## Exit codes + fail mode
- [ ] Exit `0` = pass/warn (stderr message); `2` = BLOCK. No other codes.
- [ ] Enforcement/safety = fail-closed (block); observability/reminder = fail-open (always exit 0).
- [ ] Debounce via a per-session/per-input marker where it would fire repeatedly.

## Registration + render (Rule 10)
- [ ] Registered ONCE in `src/core/hooks/registry.yaml` with id/script/category/phase/timeout/events.
- [ ] `make regen-adapter-templates` run; Codex dispatcher updated if the event coalesces.
- [ ] `bash src/adapters/claude/install.sh` (or `make dogfood-full`) re-rendered.

## Verify
- [ ] `make verify-hooks` (bash -n + shellcheck warning) — clean.
- [ ] Manual smoke: pipe a synthetic JSON input, assert exit code + stderr.
