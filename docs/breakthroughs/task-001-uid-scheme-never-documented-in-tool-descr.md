<!-- domain:INFRA | layer:reference | ssot:ref | source:outcome_history#183 | updated:2026-04-27 -->
# TASK-001: uid scheme never documented in tool description

> P: Captured insight from TASK-001 — the graph uid scheme was never surfaced in the MCP tool descriptions, so agents could not query the graph correctly.
> R: Touching tool descriptions or graph uid generation; investigating why agents misuse cos_graph_*.
> S: Looking up the current uid format — read [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md) instead.
> N: [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md)

**Date:** 2026-04-27  
**Domain:** INFRA  
**Source task:** [TASK-001](../tasks/TASK-001.md)

## Key Insight

uid scheme never documented in tool description

## What Failed

raw paths passed to cos_graph_impact returned not_found

## What Worked

auto-resolve prefix fallback in _resolve_uid

## Links

- Pattern: `learned_patterns#15` — retrievable via `cos_details`
- History: `outcome_history#183`
