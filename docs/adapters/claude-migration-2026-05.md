<!-- domain:ADAPTERS | layer:reference | ssot:true | updated:2026-05-05 -->
# Claude Adapter Migration Guide — Q-bundle + Q.deep (2026-05)

What consumer projects must do to pick up TASK-002 (Q-bundle) and TASK-003 (Q.deep) changes.

## TL;DR

```bash
cos sync-all              # propagate hook symlinks, re-render adapter template
cos doctor                # verify scaffold health
uv sync --extra rag       # pull claude-agent-sdk>=0.1.73
```

## Breaking changes

None. All changes are additive. The dispatcher falls back to the
`DefaultDispatcher` (DB-only) when `claude-agent-sdk` is not installed.

## What changed

### Q-bundle (TASK-002, 2026-05-04)

| Area | Change | Action required |
|---|---|---|
| **SDK floor** | `claude-agent-sdk>=0.1.73,<0.2.0` added to `pyproject.toml` | `uv sync --extra rag` |
| **MCP permissions** | `mcp__coding-os__*` added to `settings.local.template.json` | `cos sync-all` re-renders |
| **Hook events** | `SubagentStart`, `SubagentStop`, `PostToolUseFailure` in `adapter.yaml` | Auto via `cos sync-all` |
| **Skill descriptions** | `search/SKILL.md` frontmatter YAML-quoted | No action (auto via `cos update`) |

### Q.deep wave 1 (TASK-003, 2026-05-05)

| Area | Change | Action required |
|---|---|---|
| **DB schema** | Migration v23: 6 nullable columns on `formula_dispatches` | `cos sync-all` applies automatically |
| **`.claude/agents/`** | Symlinks deleted from scaffold | `cos sync-all` cleans up; or run `adapters/claude/install.sh` |
| **Role frontmatter** | `structured_output: true` on implementer/reviewer/debugger/refactorer | No action (roles shipped in `core/`) |
| **Role frontmatter** | `long_context: true` on researcher | No action |
| **Role frontmatter** | `enable_file_checkpointing: true` on implementer/refactorer | No action |

### Q.deep wave 2 (TASK-003 T18, 2026-05-05)

| Area | Change | Action required |
|---|---|---|
| **AGENT STREAM** | `_detect_agent_session_default()` in `server.py`; hub shows "Cl" instead of "H" | **Restart Claude/MCP server** |
| **cost_usd columns** | `_persist_dispatch_output` now writes v23 columns | No action; takes effect on next dispatch |

## Verifying the migration

```bash
# 1. Schema migration applied
sqlite3 .coding-os/coding-os.db ".schema formula_dispatches" | grep cost_usd

# 2. Dispatcher options regression test
uv run pytest tests/test_claude_dispatcher_options.py -v

# 3. Skill frontmatter gate
uv run pytest tests/test_skill_frontmatter.py -v

# 4. AGENT STREAM session id resolved
python scripts/probe_agent_session_resolver.py

# 5. Hub cost endpoint (hub must be running)
curl -s http://127.0.0.1:9188/api/cognition/cost | python -m json.tool
```

## Rollback

See [claude-rollback.md](claude-rollback.md).

## References

- [claude-deepening-checklist.md](claude-deepening-checklist.md)
- [TASK-002](../tasks/TASK-002-phase-q-bundle-claude-sdk-integration.md)
- [TASK-003](../tasks/TASK-003-phase-q-deep-claude-adapter-optimization-claude-only-focus.md)
