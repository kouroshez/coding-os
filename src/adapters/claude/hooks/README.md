<!-- domain:ADAPTERS | layer:reference | ssot:false | updated:2026-05-05 -->
# Claude-private hooks

Scripts here are **only installed into `.claude/hooks/`** of consumer
projects whose adapter is `claude`. They are NOT visible to Codex,
Gemini, or any future adapter.

Use this directory when a hook depends on an event/matcher that ONLY
the Claude SDK fires (`SubagentStart`, `PostToolUseFailure`,
`PermissionRequest`, …) or on Claude-specific environment variables
(`CLAUDE_PROJECT_DIR`, `CLAUDE_AGENT_SDK_VERSION`, …).

If a hook is genuinely cross-adapter, keep it under `src/core/hooks/` and
declare its capabilities through `src/adapters/<agent>/adapter.yaml`.

## Render order (D4)

`src/cli/hook_renderer.py` walks both directories. Adapter-private files
take precedence on name clash, so a `src/core/hooks/foo.sh` can be replaced
by `src/adapters/claude/hooks/foo.sh` without touching the registry.

`src/core/scripts/install-adapter.sh` symlinks core hooks first, then the
adapter-private layer second — `ln -sf` rebinds the symlink atomically,
so the adapter-private file wins by the end of install.

## Conventions

- Each script must source `cos-env.sh` for shared env (`COS_AGENT_DIR`,
  `COS_DB_PATH`, …).
- Each script must `exit 0` on unexpected input (fail-open) unless it is
  a deny / block hook (`exit 2`, with a clear stderr message).
- Register the hook in `src/core/hooks/registry.yaml` using
  `adapter_scope: claude` so the renderer emits it only for Claude.
- Keep cross-adapter scripts under `src/core/hooks/`. Move into this
  directory ONLY if the script can never serve another adapter.

## Existing scripts

(currently empty — see checklist `T4.4`–`T4.5` for
pending Claude-only scripts that move here from src/core/hooks.)
