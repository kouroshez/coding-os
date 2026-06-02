<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-10 -->
# Docs-First Protocol

> P: Mandatory procedure — docs are SSOT; code follows. Every code edit must trace to a doc and verify the doc still matches BEFORE writing.
> R: Any Write/Edit on `.py` `.ts` `.tsx` `.go` `.js` `.jsx` `.rs` `.sh` (production code, not tests/migrations/scaffold).
> S: Editing docs themselves, tests, fixtures, or governance-marked tasks.
> N: [docs-system.md](docs-system.md), [critical-rules.md](critical-rules.md#rule-0--docs-first), [agent-workflow.md](agent-workflow.md)

> Nav: [Governance Index](./00-index.md) | [Docs Index](../00-index.md)

## Why

Code rots in isolation. Docs rot when nothing reads them. The protocol below binds both directions so a code change CAN'T land without the spec being current — and a doc edit surfaces every code site that drifts.

Two rules in the critical-rules table back this:

- **Rule 0 — Docs-first** ([critical-rules.md#rule-0](critical-rules.md#rule-0--docs-first)): every code Write/Edit must trace to a `.doc-anchor` (BLOCKING hook).
- **Rule 19 — Docs are the contract** ([critical-rules.md#rule-19](critical-rules.md#rule-19--docs-are-the-contract--never-extend-code-beyond-doc-spec)): edit the doc BEFORE extending the code; `enforce-doc-sync.sh` surfaces drift PostToolUse.

This file is the procedural reference both rules point to.

## The protocol — five steps, every code edit

```
1. CLASSIFY → 2. LOCATE DOC → 3. READ DOC → 4. ANCHOR → 5. EDIT
                  ↓ (no doc?)
                  2b. WRITE DOC FIRST → loop back to 3
```

### 1. Classify

Run the Complexity Gate (Q1 Cynefin × Q2 dimensions). `CLEAR 1` (trivial typo / docstring) is the only path that skips Steps 2–4. Record the gate via the semantic op `cos_classify_prompt` (it classifies AND records — Rule 25); only if it returns `recorded=false` (no panel session resolvable from the MCP server) use the `write-state.sh` fallback it hands back — the low-level contract the gate hook reads:

```bash
# fallback only — cos_classify_prompt is the primary path
bash src/core/hooks/write-state.sh .thinking_os-gate "CLEAR 1"
```

Anything else → continue.

### 2. Locate the doc

Order of attempts — stop at the first hit:

| Question | Tool |
|---|---|
| "Which doc is SSOT for the topic I'm about to edit?" | `cos_doc_headers_by(domain=..., ssot="true")` |
| "What's the spec?" | `cos_doc_search "<topic>"` |
| "What does the read_next chain say to read?" | `cos_graph_context "doc:file:docs/..."` |
| "Which doc has the function I'm changing?" | `cos_graph_references "<symbol>"` then follow `doc_anchor` edges |
| "Is there a playbook for this kind of work?" | Load matching playbook skill |

If nothing matches → go to **2b**.

### 2b. No doc? Write doc first.

Open [`_templates/doc-cheat-sheet.md`](_templates/doc-cheat-sheet.md), pick the layer (adr · playbook · spec · policy · runbook · reference), create the file, commit it as a separate change BEFORE the code change. Rationale: a code change that needs a NEW spec is by definition not "trivial" — splitting them keeps blame + review clean.

Anti-pattern: writing code "first to see what shape it takes" then back-filling the spec. Use a `*spike*` or `*exploratory*` task marker if you genuinely need this path; the hook then exempts you, but the code is throwaway by contract.

### 3. Read the doc

Cheapest read first — `cos_doc_header(path)` returns frontmatter + `Purpose / Read when / Skip when / Read next` for ~100 tokens. Only full-read the body if the header signals the doc is in-scope.

If the doc cites other docs via `Read next:` / `> N:` lines, walk **one hop** of those. Do not depth-first the whole graph — token waste.

### 4. Anchor

The anchor is normally set **for you** — `cos task-start TASK-NNN` derives it from the task file's `Read First` section (Rule 25). Prefer that.

Set it by hand only for ad-hoc work covered by a `*docs-update*` / `*governance*` task marker. The bare basename `.doc-anchor` routes to `$COS_PANEL_DIR/.doc-anchor` via `cos_state_path` (per-panel; see [state-files.md](../engineering/state-files.md)):

```bash
bash src/core/hooks/write-state.sh \
  .doc-anchor \
  "$(cat <<'EOF'
ses-<session-id> task:<task-id>
- docs/engineering/<spec>.md
- docs/api-contracts/<contract>.md
EOF
)"
```

If the anchor exists but came from a previous session, the hook BLOCKS — re-run `cos task-start TASK-NNN` to refresh.

### 5. Edit

- Smallest correct change (P1, P4).
- Behavior must match the doc you anchored to. If reality forces divergence → STOP, edit the doc first, refresh the anchor, then continue.
- After the edit, `enforce-doc-sync.sh` (PostToolUse) lexically scans for symbols you removed/renamed that still appear in docs. Treat its WARNs as TODOs — either update the doc or revert the rename.

## What the hooks actually enforce

| Hook | Phase | Action | Trigger |
|---|---|---|---|
| `enforce-doc-anchor.sh` | PreToolUse Write/Edit | **BLOCK** | Code file edit with no populated `.doc-anchor` or `CLEAR 1` gate |
| `enforce-doc-sync.sh` | PostToolUse Write/Edit | WARN | Code symbol removed/renamed/signature-changed AND doc still mentions it |
| `check-doc-size.sh` | PostToolUse Write/Edit | WARN | Doc exceeds per-layer line budget |
| `auto-regen-doc-index.sh` | PostToolUse Write/Edit | regen | `docs/<dir>/00-index.md` rebuilt from frontmatter (5s debounce) |
| `auto-reindex-docs.sh` | PostToolUse Write/Edit | reindex | RAG chunks + graph nodes refreshed for the touched file |
| `nudge-docs-first.sh` | UserPromptSubmit | hint | Prompt mentions code change with no `.doc-anchor` yet → recommends `cos_doc_search` first |

Bypass paths (use sparingly, all logged):

- `CLEAR 1` gate — trivial fixes only.
- `*spike*` / `*exploratory*` / `*scratch*` task name — throwaway code.
- `*docs-update*` / `*governance*` task name — when the edit IS the doc.
- `touch $COS_PANEL_DIR/.doc-anchor-override` — one-shot, consumed on use (panel-scoped; falls back to `$COS_AGENT_DIR/.doc-anchor-override` in legacy layouts).

## When the doc is wrong

The doc is SSOT, but SSOT is not infallible. When code reality contradicts the doc:

1. Stop the code change.
2. Verify the contradiction with `cos_graph_contracts` (for HTTP/MCP surfaces) or `cos_graph_impact` (for code symbol churn).
3. Edit the doc, increment frontmatter `updated:`.
4. Append the prior decision to the audit trail: `cos_audit_log_record(doc_path, action="updated", supersedes_id=<prior>)`. Reverts are new rows; never rewrite the old one.
5. Refresh the anchor, then resume the code change.

This is **not** a bypass — it is the protocol. A code agent that updates a doc to match reality is doing higher-value work than one that ships code matching nothing.

## Domain-specific entry points

| Edit target | First doc to read |
|---|---|
| `src/core/thinking_os/**` | [docs/architecture/meta-project.md](../architecture/meta-project.md), [docs/engineering/mcp-error-envelope.md](../engineering/mcp-error-envelope.md) |
| `src/core/graph_os/**` | [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md), [docs/engineering/graph-hallucination-cures.md](../engineering/graph-hallucination-cures.md) |
| `src/core/board_os/**` | [docs/governance/task-lifecycle.md](task-lifecycle.md), [docs/engineering/board-thinking-os-coupling.md](../engineering/board-thinking-os-coupling.md) |
| `src/core/hooks/**` | [docs/engineering/hooks-reference.md](../engineering/hooks-reference.md), `src/core/hooks/registry.yaml` |
| `src/adapters/<id>/**` | [docs/playbooks/adapter-authoring.md](../playbooks/adapter-authoring.md), [docs/adapters/claude-sdk.md](../adapters/claude-sdk.md) |
| `src/templates/<id>/**` | [docs/playbooks/template-authoring.md](../playbooks/template-authoring.md), [docs/governance/anatomy-contract.md](anatomy-contract.md), [docs/governance/scaffold-boundary-contract.md](scaffold-boundary-contract.md) |
| `src/cli/**` | [docs/architecture/meta-project.md](../architecture/meta-project.md) |

Beyond `src/core/**`, the `Dimension Registry` routes per-stack edits to the right doc set.

## Verification

After any non-trivial code change, before `task-done`:

1. `make docs-lint` — frontmatter + nav + dead-link sweep.
2. Confirm `cos_doc_search "<changed concept>"` still returns the doc you anchored to.
3. If the change altered a contract — re-run the contract producer test (`tests/test_mcp_schema_traps.py` for MCP, `tests/test_adapter_parity.py` for adapters).

## Anti-patterns

- ❌ Editing code, then editing the doc to match.
- ❌ Treating `enforce-doc-anchor` BLOCKs as friction; bypassing with overrides.
- ❌ Anchoring to a doc you didn't actually read (cargo-cult anchor).
- ❌ Filing a `*spike*` task to dodge anchor enforcement on real production work.
- ❌ Renaming a symbol without checking `cos_graph_references` for doc citations first.

## See also

- [Rule 0 — Docs-first](critical-rules.md#rule-0--docs-first)
- [Rule 19 — Docs are the contract](critical-rules.md#rule-19--docs-are-the-contract--never-extend-code-beyond-doc-spec)
- [docs-system.md](docs-system.md) — taxonomy, headers, navigation
- [doc-cheat-sheet.md](_templates/doc-cheat-sheet.md) — pick the right layer
- [agent-workflow.md](agent-workflow.md) — Core Loop (Classify → Orient → Plan → Execute → Verify)
