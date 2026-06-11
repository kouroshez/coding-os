<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-06 -->
# Extension Manager — Architecture & Security/Trust Model

Purpose: SSOT contract for adding / removing / uploading **skills** and **MCP servers** to a coding-os project from the Hub panel — the unified `CatalogUnit` model, the per-project `extensions.json` manifest, the trust state machine, the fail-closed security gate, the API + UI surface, the adapter-parity fan-out, and the phased P0–P5 rollout.
Read when: implementing any slice of the Extension Manager (Hub routes under `src/core/web/`, the manifest/render pipeline in `src/cli/`, or the security scanner) — and before shipping any code, because this doc is the contract that the code must satisfy.

> Nav: [docs/](../) · [engineering/](./)

**Status: DESIGN (contract before code).** No Extension Manager code ships until this doc is reviewed. v1 installs **skills + MCP**; hooks/rules/commands are **read-only** in v1 (they are DNA — see [Scope](#v1-scope)).

## Why this exists

Today, adding a skill means editing `src/core/skills/<name>/SKILL.md` (meta) or a consumer-local skill and re-running the adapter render; adding an MCP server means hand-editing `mcp.json` / the adapter config. That is fine for an agent working *on* coding-os, but the product's consumers run the gamut from a beginner vibe-coder to an enterprise team — none of whom should hand-edit kernel files. The Extension Manager makes "install this skill", "remove that MCP server", "upload my own skill" first-class, data-driven Hub operations, governed by the same fail-closed discipline the rest of the kernel enforces.

The cost of getting this wrong is high: a **skill is instructions injected into the agent's context** (an instruction-poisoning / prompt-injection vector) and an **MCP server is an endpoint the agent executes** (an RCE / SSRF / data-exfiltration vector). Installing either is *installing code*. The security model is therefore the centre of this design, not an afterthought.

## Stakeholders & their primary need

| Stakeholder | Primary need | Design consequence |
|---|---|---|
| Beginner consumer | One-click install of a vetted skill/MCP; never sees a config file | Builtin catalog + auto-trust for first-party units |
| Professional consumer | Add a custom MCP (their company API) + their own skills | URL-preferred MCP + upload path with scan + approval |
| Enterprise team | Org policy: allow/deny lists, audit trail, no unreviewed code | Policy layer (P5), audit-log on every mutation, signed catalogs |
| coding-os maintainer | New adapter/stack inherits EM for free | Data-driven from `extensions.json` → render pipeline; no per-adapter EM code |
| The agent itself | Must not be poisoned by an installed unit | Fail-closed trust gate; quarantine before any unit reaches the live context |

## Unified model — `CatalogUnit`

One abstraction over every installable kind, so the catalog, manifest, API, and UI never special-case a kind beyond its `kind` field.

```
CatalogUnit:
  id:             str            # stable slug, e.g. "skill:redis" / "mcp:github"
  kind:           skill | mcp    # v1; hook/rule/command reserved (read-only)
  name:           str
  version:        str            # semver; "builtin" units track the meta-repo
  source:         builtin | registry | url | upload
  origin:         str            # path / URL / registry-id (provenance)
  manifest_digest: str           # sha256 of the unit's bytes — trust is pinned to this
  trust_state:    TrustState     # see state machine below
  scope:          project | agent  # where it installs (mirrors $COS_*_DIR tiers)
  enabled:        bool           # active only when trusted AND enabled
  installed_at:   epoch
```

`manifest_digest` is load-bearing: **trust is pinned to the exact bytes that were scanned**. Any change to the unit (re-upload, registry bump) resets `trust_state` — you cannot trust a moving target.

## Per-project manifest — `extensions.json`

SSOT (P1) for what is installed in one project, at `.coding-os/extensions.json` (project scope — shared across that project's agents) with an `agent`-scoped overlay where a unit is agent-specific. Shape:

```jsonc
{
  "version": 1,
  "units": [
    { "id": "skill:redis", "kind": "skill", "source": "builtin",
      "version": "...", "manifest_digest": "sha256:…",
      "trust_state": "trusted", "scope": "project", "enabled": true }
  ]
}
```

The **render pipeline reads `extensions.json`** and materializes each enabled+trusted unit into the per-adapter surface (`.claude/skills/<name>/`, `mcp.json`, `.codex/…`). The manifest — not the materialized files — is the source of truth; the materialized files are derived artifacts (consistent with the Modularity Map). `cos sync-doctor` reconciles drift between manifest and materialized state.

## Trust state machine (fail-closed)

```
            scan(pass)                 approve (Hub auth)
 unknown ───────────────► scanned ──────────────────────► trusted ──► enabled
    │          │                                              │
    │          └── scan(hit) ──► quarantined                  │
    │                                                          ▼
    └──────────────────────── revoked ◄──────────── remove / digest-change
```

- A unit is **active only in `trusted` + `enabled`**. Every other state is inert — the render pipeline skips it (fail-closed).
- `builtin` units (from `src/core/skills/` / a maintainer-signed registry) enter at `scanned` and are auto-`trusted` (first-party). Everything else requires an explicit Hub approval after a clean scan.
- A **digest change revokes trust** — a re-uploaded skill or a bumped MCP version drops back to `unknown` and must be re-scanned + re-approved.

## Security gate — the heart of the design

Every transition into `scanned`/`trusted` runs a fail-closed gate. A check that errors = quarantine, never silent-pass.

### Skills (instruction-poisoning surface)

- **SKILL.md injection scan** — flag instruction-override patterns ("ignore previous/all instructions", "disregard CLAUDE.md / critical rules", role-reassignment, tool-permission escalation, "exfiltrate"/"send to" + URL), hidden/zero-width unicode, base64/obfuscated blobs, and oversized frontmatter. Any hit → `quarantined` with the finding shown in the UI.
- **Structure validation** — valid frontmatter, name/description present, size caps, no executable payloads bundled in the skill dir.
- Skills cannot install hooks/rules/commands transitively (v1 scope guard).

### MCP servers (execution / SSRF surface)

- **URL-preferred** — a remote HTTPS MCP endpoint is preferred over a local stdio binary; HTTPS required (no plaintext).
- **Allow-list** — stdio `command` must be on a maintained allow-list or carry an explicit, audited approval; arguments are validated, not free-form shell.
- **SSRF guard** — URL targets resolved and rejected if they hit private/link-local/loopback ranges unless the org policy explicitly allows (enterprise intranet MCP).
- The MCP tool surface is **namespaced** so an installed server cannot shadow `cos_*` (Rule 2).

### Upload jail

Uploaded bytes land in a **quarantine dir** (`.coding-os/extensions/_quarantine/<digest>/`), never directly in the live skills/MCP path. Extraction is path-traversal-safe (no `..`, no absolute paths, no symlink escape). Promotion to the live path happens **only** after a clean scan + Hub approval. Rejected uploads are retained for audit, then GC'd.

### Hub auth

Mutating endpoints (`install`/`remove`/`upload`/`trust`) require auth. The Hub is loopback-bound by default (single-user), where the auth is the local session; for shared/enterprise deployments a Hub token is required (P5). Every mutation writes a who · what · which unit · digest · when log row.

## API surface (Hub routes)

Under `/api/p/<slug>/extensions` (per-project, mirrors the existing hub routing). Every response uses the `ok(data)` / `fail(category, message)` envelope (Rule 13).

| Method · path | Purpose |
|---|---|
| `GET  …/extensions` | List catalog (builtin + registry) + installed units with trust badges |
| `POST …/extensions/install` | Install a catalog unit → manifest + render (fail-closed on trust) |
| `POST …/extensions/scan` | Run the security gate on a unit; return findings |
| `POST …/extensions/trust` | Approve a `scanned` unit → `trusted` (Hub auth + audit) |
| `POST …/extensions/upload` | Upload a skill/MCP into the quarantine jail |
| `DELETE …/extensions/{id}` | Remove a unit → manifest + re-render; trust → `revoked` |

## UI surface (Hub "Extensions" panel)

Catalog browser (filter by kind/source), installed list with **trust badges** (unknown/scanned/quarantined/trusted), per-unit actions (install · remove · scan · approve · upload), a scan-result viewer that shows findings before approval, and a trust-approval modal. Field names are read from the producer envelope, never guessed ([api-contract-discipline](../../src/core/rules/api-contract-discipline.md)).

## Adapter-parity fan-out

Install/remove mutates `extensions.json`, then the **existing render pipeline** re-materializes the per-adapter surface for every installed adapter — data-driven, so a new adapter (gemini/opencode) inherits the Extension Manager with zero EM-specific code, bounded only by that adapter's declared capability (e.g. an adapter that cannot host MCP renders only skills). This mirrors the hook-capability filtering already used for adapter templates.

## v1 scope

| Kind | v1 | Rationale |
|---|---|---|
| skill | ✅ installable | High demand; risk contained by the injection scan + quarantine |
| mcp | ✅ installable | High demand; risk contained by allow-list + SSRF guard + namespacing |
| hook · rule · command | ❌ read-only (viewable) | These are DNA / safety-critical kernel; consumer-mutable hooks would defeat the enforcement layer. Listed in the UI for transparency, never installable from the Hub in v1 |

## Phased plan

| Phase | Deliverable |
|---|---|
| **P0** | This design doc + `CatalogUnit` type + `extensions.json` schema (read-only: list installed) |
| **P1** | Read path — Hub Extensions panel lists builtin + installed units (no mutation) |
| **P2** | Install/remove **builtin skills** from the `src/core/skills` catalog (auto-trust) → re-render adapters |
| **P3** | MCP install from allow-listed registry/URL + trust-approval flow + audit log |
| **P4** | Upload path — skill upload → quarantine → scan → approve → enable; custom MCP URL with SSRF guard |
| **P5** | Enterprise — Hub auth tokens, org allow/deny policy, signed catalogs, hooks/rules/commands read-only viewer |

## Failure modes designed against

| Failure mode | Mitigation |
|---|---|
| Poisoned SKILL.md overrides critical rules | Injection scan → quarantine; fail-closed trust gate; builtin rules still load first |
| Malicious MCP exfiltrates repo / hits intranet | URL-preferred HTTPS + allow-list + SSRF guard + `cos_*` namespace protection |
| Path-traversal via uploaded archive | Quarantine jail + traversal-safe extraction; no direct write to live path |
| Trusted unit silently mutated later | Trust pinned to `manifest_digest`; any change revokes trust |
| Manifest ↔ materialized drift | `extensions.json` is SSOT; `cos sync-doctor` reconciles; render is idempotent |
| New adapter silently lacks EM | Fan-out is data-driven from the manifest; capability-filtered, no per-adapter code |
| Unaudited install in a shared deploy | Hub auth on mutations + audit-trail row per mutation |

## See also

- [hub-architecture.md](hub-architecture.md) — the Hub daemon + per-project routing this feature plugs into.
- [mcp-tool-inventory.md](../governance/mcp-tool-inventory.md) — the `cos_*` namespace MCP units must not shadow.
- [src/core/rules/api-contract-discipline.md](../../src/core/rules/api-contract-discipline.md) — producer-verified envelope fields for the UI.
- [docs/governance/critical-rules.md](../governance/critical-rules.md) — Rule 2 (namespace), Rule 13 (envelope), the enforcement layer EM must not weaken.
