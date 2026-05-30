<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-30 -->
# Using RTK (Rust Token Killer) with coding-os

**Audience:** any coding-os user/consumer who also runs [RTK](https://github.com/rtk-ai/rtk)
— a CLI proxy that compresses command output to cut LLM tokens 60–90%.

**TL;DR:** RTK is optional and safe to keep, but its compression is **lossy by
design**. Exclude the three commands whose exact output the agent reasons on
(`grep`, `rg`, `sqlite3`) so RTK never corrupts coding-os's structural ground
truth. Everything else (the big savers) stays.

## Why it matters

RTK intercepts Bash tool calls and rewrites them to compressed `rtk <cmd>`
equivalents (filtering / truncating / dedup). For most output (logs, `ls`,
`git status`, file reads) lossy compression is fine. But for three command
classes, lossy = **wrong answer**:

| Command | What lossy compression breaks |
|---|---|
| `grep` / `rg` | collapses/renames symbols — e.g. `compose_chain` rendered as `n`, identifiers merged. An agent renaming or tracing on that output acts on wrong names. |
| `sqlite3` | truncates/dedups DB rows — exact values (counts, ids, NULLs) get mangled, so data audits read false numbers. |

coding-os leans on exact symbol/row fidelity (graph-first discipline, the
`search` skill's ground-truth counting, doctor DB audits). RTK's lossy filter
on those commands silently undermines all three.

> Note: RTK does **not** touch the built-in `Read`, `Grep`, `Glob` tools —
> those bypass the hook entirely. coding-os already tells agents to prefer
> those tools over Bash `grep`/`cat` (see the `search` + `graph-explorer`
> skills), so a disciplined agent rarely hits RTK at all. The exclusion below
> protects the cases where Bash *is* used.

## The fix — exclude three commands

Add to RTK's config:

```toml
[hooks]
exclude_commands = ["grep", "rg", "sqlite3"]
```

This preserves ~all of RTK's savings — the bulk comes from `rtk read` / `git`
/ `ls` (skim-tolerant), which stay proxied.

### ⚠️ macOS gotcha — edit the RIGHT config file

RTK reads **two** possible paths, and on macOS the **Library** one wins
(Rust's platform config dir):

| Path | macOS active? |
|---|---|
| `~/Library/Application Support/rtk/config.toml` | ✅ **yes** — this is the `rtk init`-generated config |
| `~/.config/rtk/config.toml` | usually ignored on macOS |

Editing only `~/.config/...` has **no effect** on macOS. Set
`exclude_commands` in the **Library** file (or both, to be safe). The Library
file is the full config (`[tracking]`, `[filters]`, `[limits]`, `[hooks]`, …);
its `[hooks] exclude_commands` defaults to `[]`.

## Verify it works (deterministic)

RTK caps a *proxied* grep at `grep_max_results` (default 200). So:

```bash
# Run a grep that matches >200 lines. If RTK still proxies it, output caps
# at ~200; if excluded, you get the raw full count.
grep -n "e" <a-file-with-300+-lines>.py | wc -l    # >200 => excluded (raw) ✓
```

Or check `rtk gain --history`: an excluded `grep` does **not** appear (it ran
raw, unproxied).

## Should I run RTK at all with coding-os?

Optional. coding-os is already token-efficient by design (graph envelopes
~300 tok replace 5–50K-token reads; token-budgeted MCP meta; deferred tool
schemas). RTK adds savings on verbose Bash output but is redundant with the
Read/Grep tools. If you keep it, apply the exclusion above. If you remove it,
nothing in coding-os depends on it.

## See also
- [src/core/skills/search/SKILL.md](../../src/core/skills/search/SKILL.md) — grep discipline + ground-truth counting (use the Grep tool, not Bash grep).
- [graph-hallucination-cures.md](graph-hallucination-cures.md) — why structural fidelity matters.
