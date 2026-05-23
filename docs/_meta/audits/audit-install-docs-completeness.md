<!-- domain:ALL | layer:engineering | ssot:false | updated:2026-05-23 -->
# Audit — Install/Setup Docs Completeness (2026-05-23)

> User mandate: "
> ". Enterprise product, zero ambiguity in install path.
> Sweep covers README, CONTRIBUTING, and the actual artifacts on disk
> (Dockerfile, compose, install scripts, MCP wiring).

## Ground truth on disk

| Artifact | Path | Documented in README? | Documented in CONTRIBUTING? |
|---|---|---|---|
| Dockerfile (multi-stage UI + Python runtime, non-root, healthcheck) | `Dockerfile` | ❌ | ❌ |
| docker-compose.yml (single-service Hub, named volume) | `docker-compose.yml` | ❌ | ❌ |
| MCP wiring file | `.mcp.json` | mentioned at line 187 only | ❌ |
| Adapter installers | `src/adapters/{claude,codex,cursor}/install.sh` | implicit via `cos init` | ❌ |
| Cursor adapter | `src/adapters/cursor/` | listed but install path silent | ❌ |
| `cos doctor` 14-point health | `src/cli/doctor.py` | mentioned (no troubleshooting) | mentioned (no troubleshooting) |

## Mandatory category table

| # | Gap | Severity | Fix |
|---|---|---|---|
| 1 | README has no Docker quickstart even though `Dockerfile` + `docker-compose.yml` ship in the repo | HIGH | Add "Run with Docker" subsection after the uv quickstart |
| 2 | README quickstart doesn't state prerequisites (Python, Node, uv versions) | HIGH | Add "Prerequisites" block before quickstart |
| 3 | README's "MCP tools (79 tools …)" heading is stale (now 56 unique `def cos_*`) | MEDIUM | Soften to "MCP tools (`cos_*` family, …)" — defer count to inventory doc |
| 4 | README doesn't explain MCP wire-up for Claude/Codex/Cursor consumers | HIGH | Add explicit step: "Adapter install wires `.mcp.json`" + one-liner per agent |
| 5 | README has no troubleshooting / FAQ section | MEDIUM | Add "Troubleshooting" with the 3 most common failures (uv missing, port in use, mcp not registered) |
| 6 | CONTRIBUTING Development Setup has no Docker option | HIGH | Add Docker dev path so contributors can run the Hub without local Python/Node |
| 7 | CONTRIBUTING doesn't note `cursor` adapter or its install entry-point | MEDIUM | Mention three adapters by name in install context |
| 8 | No single SSOT install doc for consumers (different from contributors) | MEDIUM | Reuse the new README "Run with Docker" + "Adapter install" subsections; defer separate INSTALL.md until needed |

## Scope (files touched by remediation)

- `README.md` — Prerequisites, Run with Docker, Adapter install, Troubleshooting, soft tool-count
- `CONTRIBUTING.md` — Docker dev path, three-adapter note

## Resume Marker

- 2026-05-23 — audit complete; 7 gaps closed in README + CONTRIBUTING,
  1 deferred. Re-grep AFTER:
  - README "## Prerequisites" section: present ✓
  - README "## Run with Docker" section: present ✓
  - README "## MCP server wire-up": present ✓
  - README "## Troubleshooting" section: 8 common failures table ✓
  - README "79 tools" stale heading: removed ✓
  - CONTRIBUTING "Option B — Docker" subsection: present ✓
  - CONTRIBUTING three-adapter inline list: present ✓
  - docs-lint: link audit clean.

## ExhaustiveEvidence

```
counts_before = {
  install_doc_gaps: 8,
}
counts_after = {
  install_doc_gaps_closed: 7,
  install_doc_gaps_deferred: 1,  # separate INSTALL.md — README covers
}
categories_covered = [
  "Prerequisites block (versions + macOS install hints)",
  "Docker quickstart in README",
  "MCP server wire-up explanation",
  "Troubleshooting table (8 common failures)",
  "Tool-count claim softened (no stale '79')",
  "CONTRIBUTING Docker dev path",
  "Three adapters named (claude, codex, cursor)"
]
gaps_remaining = [
  "Dedicated docs/install.md SSOT — DEFERRED, README covers without churn (Rule 22)"
]
```
