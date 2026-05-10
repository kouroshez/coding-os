<!-- domain:ADAPTERS | layer:reference | ssot:true | updated:2026-05-05 -->
# Claude Adapter Rollback Guide

> P: Procedure for reverting a Claude-adapter upgrade in a consumer project if the new bundle breaks production.
> R: Post-deploy regression in `adapters/claude/` — agent boot failures, dispatcher errors, hook misfires after `cos update`.
> S: Investigating a known-good adapter — see `claude-sdk.md` instead.
> N: [claude-migration-2026-05.md](claude-migration-2026-05.md), [claude-sdk.md](claude-sdk.md)

> Nav: [Adapters Index](./00-index.md) | [Docs Index](../00-index.md)

## Git revert window

TASK-002 and TASK-003 shipped on 2026-05-05. The revert window (before dependent
consumer projects pull `cos update`) is approximately 7 days.

```bash
# Revert TASK-003 Q.deep changes only
git revert <TASK-003-commit-sha>..HEAD

# Revert both Q-bundle + Q.deep
git revert <TASK-002-commit-sha>..HEAD
```

Identify the commit SHAs:
```bash
git log --oneline | grep -E "TASK-002|TASK-003|Q-bundle|Q.deep"
```

## Pinning a consumer to a coding-os tag

Consumer projects that ran `cos init` reference `coding-os` via symlinks into
`$COS_META_ROOT`. To freeze at a known-good state:

```bash
# 1. Tag the good state in this repo
git tag v0.2.x-stable

# 2. In the consumer project
cos update --pin-tag v0.2.x-stable   # (planned — see T14.x roadmap)

# Until --pin-tag lands: override the meta root
export COS_META_ROOT=/path/to/coding-os-v0.2.x-stable
cos sync-all
```

## DB schema rollback

Schema migrations are **append-only** (Rule 9). Migration v23 added 6 nullable
columns — reverting it does NOT break existing code paths; the old 9-column
INSERT still works (new columns stay NULL).

If you need to drop the v23 columns entirely (e.g. storage budget):

```bash
# Dump + recreate without v23 columns
sqlite3 .coding-os/coding-os.db .dump > backup.sql
# Edit backup.sql — remove v23 columns from CREATE TABLE formula_dispatches
# Recreate DB
sqlite3 .coding-os/coding-os.db < backup.sql
```

**Warning:** This destroys v23 cost_usd / usage_jsonb data. Back up first.

## AGENT STREAM rollback

If the `_detect_agent_session_default()` resolver causes issues:

1. `COS_AGENT_SESSION_ID=""` — forces NULL attribution (old H-badge behavior).
2. Or revert `core/thinking_os/server.py` to the pre-T18.1 state:
   ```bash
   git show HEAD~1:core/thinking_os/server.py > server.py
   # Then restart the MCP server / Claude
   ```

## Adapter template rollback

```bash
# Re-render from current registry (removes any Q.deep template additions)
make regen-adapter-templates

# Re-apply to a specific consumer
cd /path/to/consumer
cos update
```

## See also

- [claude-migration-2026-05.md](claude-migration-2026-05.md)
- [AGENTS.md Rule 9](../../AGENTS.md) — append-only migrations
