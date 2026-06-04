<!-- domain:DOCS | layer:reference | ssot:true | updated:{{DATE}} -->
# Doc Cheat Sheet — Decide Structure Before Writing

Purpose: Single decision guide an agent reads BEFORE creating any new documentation file. Maps task intent → layer → directory → template → token budget.
Read when: About to create or scaffold a new `.md` file under `docs/`.
Skip when: Editing an existing doc (use `enforce-doc-sync` + read the existing file).
Read next: [docs-system.md](../docs-system.md), [decision-records.md](../decision-records.md)

> Nav: [Templates Index](../00-index.md) · [Docs Index](../../00-index.md)

---

## 1. Decision Tree (read first)

```
What are you documenting?

├─ A binding architecture/technology decision        →  ADR
│   path: docs/architecture/adr/ADR-NNN-slug.md
│   template: decision-records.md
│   token budget: 800–1500
│
├─ A repeatable workflow / "how to perform X"        →  playbook
│   path: docs/playbooks/<kebab>.md
│   template: playbook-template.md
│   token budget: 1000–2500
│
├─ Operational steps for an alert/incident type      →  runbook
│   path: docs/ops/runbooks/<kebab>.md
│   template: runbook-template.md
│   token budget: 800–2000
│
├─ Post-incident review (something broke)            →  post-mortem
│   path: docs/governance/postmortems/YYYY-MM-DD-<slug>.md
│   template: post-mortem-template.md
│   token budget: 1500–3000
│
├─ API/contract for an endpoint or service           →  spec
│   path: docs/api-contracts/<service>-endpoints.md
│   template: api-contract-template.md
│   token budget: 1500–4000
│
├─ Engineering rule that constrains future code      →  policy/rule
│   path: docs/engineering/<topic>.md
│   token budget: 800–2000
│
├─ Domain glossary / lexicon                          →  reference
│   path: docs/governance/glossary.md (single file)
│   token budget: append rows only
│
├─ Security review for a change/feature              →  checklist
│   path: docs/playbooks/security-review.md (extend)
│   template: security-review-template.md
│   token budget: 600–1500
│
├─ Architecture overview / system map                →  index/spec
│   path: docs/architecture/NN-<domain>.md
│   token budget: 1200–3000
│
└─ Task execution log                                →  task
    path: docs/tasks/TASK-NNN-slug.md
    template: task-detail.md
    token budget: ≤1500 (lint warns), <3000 (lint blocks)
```

If the answer doesn't fit any branch above, the doc probably doesn't belong in `docs/` — it's either code-comment territory, a CHANGELOG entry, or it should be subsumed into AGENTS.md / a CLAUDE.md.

---

## 2. Mandatory Header (every new file)

Two equivalent authoring styles. Pick one per file. Mixing both inside a single doc is allowed but discouraged — pick one and stick with it.

### 2a. Long form (default — readable, ~100 tokens)

```html
<!-- domain:XXX | layer:LAYER | ssot:true|ref | updated:YYYY-MM-DD -->
# H1 Title (concise, no decoration)

Purpose: One sentence; what this doc covers and why it exists.
Read when: One bullet describing the trigger condition.
Skip when: One bullet describing when NOT to read.
Read next: 1–3 relative links.

> Nav: [Parent Index](./00-index.md)
```

### 2b. Short form (token-tight — ~30% smaller, same semantics)

```html
<!-- domain:XXX | layer:LAYER | ssot:true|ref | updated:YYYY-MM-DD -->
# H1 Title

> P: One-sentence purpose.
> R: trigger condition.
> S: when NOT to read.
> N: link1, link2, link3
```

Use short form for high-traffic routing files (`docs/governance/*`, every `00-index.md`, every `references/anatomy.md`) where the same opening block is parsed by every agent on every task. Reserve long form for human-onboarding docs (`getting-started.md`, `README.md`) where prose flow matters.

**Sunset plan:** long form is the legacy default. New files SHOULD prefer short form. Long form remains accepted indefinitely for back-compat — the next breaking-version of `doc-cheat-sheet.md` may flip the default. Migration is opt-in; no auto-rewrites.

Both forms are accepted by `docs-lint`, parsed by `cos_doc_header`, and emit `read_next` graph edges via `md_links` extractor. Mechanical surface is identical — only the byte count differs.

`domain` values (canonical — SSOT [docs-system.md](../docs-system.md#header-contract), validated by docs-lint): `ALL` · `CORE` · `META` · `ADAPTERS` · `DOCS` · `OPS` · `INFRA` · `SECURITY` (meta-repo) · `PRODUCT` · `BACKEND` · `FRONTEND` · `AI` · `MOBILE` (consumer). `XXX`/`STACK_DOMAIN` = template placeholders.
`layer` values: `index` · `policy` · `playbook` · `spec` · `adr` · `reference` · `runbook` · `postmortem` · `task` · `engineering` · `architecture` · `template` · `plan` · `contract` · `checklist`.
`ssot`: `true` if this file is the source of truth on its topic; `ref` if it points elsewhere.

The four `Purpose / Read when / Skip when / Read next` (or `P/R/S/N`) lines are how agents decide in <100 tokens whether to keep reading.

### 2c. Optional frontmatter extras

Three optional keys ride along in the same HTML comment when the doc benefits from them:

- `tokens:NNNN` — author's token budget estimate. Surfaces in `00-index.md` so the agent can fan-out costs.
- `priority:0.X` — float 0.0–1.0. Routes higher-priority docs to the top of `00-index.md` and `cos_doc_headers_by` results.
- `reads:[a.md, b.md]` — short-form vector that emits one `read_next` graph edge per target (substitute for a long-form `Read next:` line on a doc with no body to host one).

---

## 3. Anti-Patterns (don't write these)

- ❌ Code dumps. If a reader needs the code, link to it; don't paste it. Code rots; links don't.
- ❌ Step-by-step API call documentation duplicating the source. Document *intent* and *contract*, link to the endpoint code.
- ❌ "What this function does" prose. Function name + signature is the doc.
- ❌ Walls of bullet points without structure. If the section is >12 bullets, it's two sections.
- ❌ Restating CLAUDE.md / AGENTS.md content. Reference back, don't duplicate.
- ❌ "Future work" sections that are actually just TODOs. Use the Scrumban board.
- ❌ Diagrams without a one-line caption explaining what to look for.
- ❌ Versioned files (`feature-v2.md`, `feature-final.md`). Edit the canonical file; let git track history.

---

## 4. Required Sections by Layer

| Layer | H1 → required H2s |
|---|---|
| **adr** | Status · Context · Decision · Consequences · Alternatives Considered |
| **playbook** | When to use · Inputs · Steps · Verification · Failure modes |
| **runbook** | Trigger / Alert · Pre-conditions · Steps · Verification · Rollback · Escalation |
| **post-mortem** | Summary · Timeline · Impact · Root cause · Contributing factors · Action items · Lessons |
| **spec** (API) | Endpoint surface · Request schema · Response schema · Error contract · Examples · Deprecation policy |
| **policy** | Scope · Rule · Rationale · Enforcement · Exceptions |
| **reference** | Index of items · Cross-links |
| **task** | Outcome · Read First · Acceptance · Work Log |

Hooks (`enforce-template`) check ADR / task / PRD / breakthrough structure. Other layers are convention-enforced via review.

---

## 5. Token-Efficiency Rules

- **Compress prose, preserve structure.** "Use the X library to validate input" → "Validates via X."
- **One concept per sentence.** Multi-clause sentences cost more to parse.
- **Lead with verbs.** "Returns the user record." not "This function will return the user record."
- **Tables beat bullets** for matrices (input/output, role/permission, status/transition).
- **Code blocks only for verbatim contracts.** A function signature, an error envelope, a config schema.
- **No screenshots in docs/** — link out or describe the state. (Diagrams as `.svg`/`.mermaid` are fine.)

Target: a competent agent who has the codebase + AGENTS.md should be able to act on the doc in **<5 minutes of reading**. If yours takes longer, it's too long.

---

## 6. Where to Link, Where to Inline

| Information | Place |
|---|---|
| Decision rationale ("why we chose X") | ADR — link from playbooks/specs |
| Step-by-step procedure | Playbook — link from runbooks/post-mortems |
| Domain term definition | Glossary — never re-define inline |
| Constraint on future code | `docs/engineering/*.md` rule |
| Error envelope shape | `docs/api-contracts/error-format.md` |
| Permission/access matrix | `docs/playbooks/security-review.md` |
| Pricing / external SLA | `docs/ops/external-services.md` |
| Roadmap / phase plan | `docs/development-roadmap.md` (single file) |

If you find yourself describing the same thing twice, extract to one location and link.

---

## 7. After Writing — Verification Loop

1. `make docs-lint` (frontmatter + nav + dead-link check).
2. Confirm `cos_doc_search "<your title>"` finds the new file (FTS5 indexed).
3. Confirm `cos_graph_query "<filename>"` shows the file as a node with link edges.
4. If the doc spec'd new code, anchor with `bash .claude/hooks/write-state.sh .doc-anchor "<doc path>"` before coding (bare basename auto-routes to `$COS_PANEL_DIR/.doc-anchor` via `cos_state_path` — see [state-files.md](../../engineering/state-files.md)).

---

## 8. Quick Tells: which template am I missing?

If your task is…

- Wiring a third-party service (Stripe, Twilio) → ADR + playbook
- Adding a new MCP tool → spec + AGENTS.md routing line
- Hardening an existing flow → security-review checklist
- Naming a new domain term → glossary row
- Documenting a recurring failure → runbook + post-mortem (if recent)
- Capturing a permanent rule (no Postgres, etc.) → policy under `docs/engineering/`

When in doubt, read [docs-system.md](../docs-system.md) and ask which existing doc this belongs INSIDE before creating a new file.
