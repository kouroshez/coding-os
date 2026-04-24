---
id: TASK-060
title: "Phase O.2.c — Service auto-install prompt on first cos run"
swimlane: core
kind: feature
epic: phase-o
labels: [hub, bootstrap, install-ux]
status: icebox
priority: P2
appetite: "4h"
created: 2026-04-24
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-060: Phase O.2.c — Service auto-install prompt on first cos run

**Outcome (one sentence):** After uv tool install coding-os, the first cos invocation detects no hub service and interactively offers cos service install.

## Read First
- [cli/main.py](../../cli/main.py) — `_bootstrap_hub_dir_if_first_run` is the integration point
- [cli/hub_commands.py](../../cli/hub_commands.py) — `service_install`, `_launchd_plist_path`, `_systemd_unit_path`
- [core/hooks/ensure-hub-up.sh](../../core/hooks/ensure-hub-up.sh) — precedent for the "is hub already serving" probe

## Deliverables
1. **Extend `_bootstrap_hub_dir_if_first_run` in `cli/main.py`** to also drop a sentinel `~/.coding-os/.bootstrap-prompt-seen` the FIRST time it runs. Absence of that file AND absence of the platform's service unit = trigger the prompt.
2. **New helper `_maybe_prompt_service_install(click.Context)`** in `cli/main.py`:
   - skip entirely when `stdin`/`stdout` is not a TTY (non-interactive CI, MCP subprocess, etc.)
   - skip when `COS_NO_BOOTSTRAP_PROMPT=1` is set
   - skip when a service unit already exists at `_launchd_plist_path()` (macOS) or `_systemd_unit_path()` (Linux)
   - else `click.confirm("Install the coding-os Hub as a background service? [Y/n]", default=True)` → on yes, invoke `ctx.invoke(service_install, port=DEFAULT_HUB_PORT)`
   - write the sentinel regardless of the user's answer so we never nag twice
3. **Wire-point:** call `_maybe_prompt_service_install(ctx)` at the end of `_bootstrap_hub_dir_if_first_run` via `click.get_current_context(silent=True)`. Must not raise on any path — wrap the entire prompt in a single `try/except Exception as exc: logger.debug(...)` guard so a broken launchctl doesn't brick every `cos ...` call.
4. **Tests in `tests/test_bootstrap_prompt.py`:**
   - non-TTY input → prompt skipped, sentinel still written
   - sentinel present → prompt skipped
   - `COS_NO_BOOTSTRAP_PROMPT=1` → skipped
   - TTY + no sentinel + no unit + user answers "n" → sentinel written, no unit created
   - TTY + user answers "y" → patched `service_install` invoked once with `port=DEFAULT_HUB_PORT`
   - Unsupported platform (`platform.system()` returns "FreeBSD" say) → skipped gracefully

## Acceptance (G/W/T)
- **Given** a fresh machine where `~/.coding-os/` does not exist and no launchd plist / systemd unit is installed
- **When** the user runs `cos --help` (or any `cos` subcommand) from an interactive terminal
- **Then** they see exactly ONE prompt `"Install the coding-os Hub as a background service? [Y/n]"`, `~/.coding-os/.bootstrap-prompt-seen` is written, and subsequent `cos` calls in the same or future sessions do NOT re-prompt.

## Verification
- `uv run pytest tests/test_bootstrap_prompt.py -q`
- `uv run pytest tests/test_cli.py -q` (no regression)
- Manual: `HOME=/tmp/fresh-home-$$ cos --help` inside a real TTY shows the prompt; running it a second time does not.

## Non-goals
- No auto-start of a background daemon without the user's "y" — consent first.
- Windows service install is out of scope; keep the macOS/Linux split that `cos service install` already enforces.
- No GUI toast / notification — TTY prompt only.

## Work Log
