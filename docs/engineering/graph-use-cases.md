<!-- domain:ALL | layer:engineering | ssot:true | updated:2026-05-06 -->
# Graph-OS — Complete Use-Case Catalogue

> P: Definitive list of every situation where calling a `cos_graph_*` tool
>    saves tokens, prevents hallucination, or reveals an answer no other
>    layer can. Pairs with the hallucination-cure matrix.
> R: Daily reference for agents and developers deciding "graph or grep?".
> S: Internals of any single tool — see [graph_os-queries.md](graph_os-queries.md).
> N: [graph-hallucination-cures.md](graph-hallucination-cures.md), [retrieval-routing.md](retrieval-routing.md), [rename-workflow.md](rename-workflow.md), [core/skills/graph-explorer/SKILL.md](../../core/skills/graph-explorer/SKILL.md)

The hallucination-cures doc lists the 17 distinct hallucinations the
graph eliminates. This doc is wider — every concrete situation in
day-to-day work where the graph wins, grouped by intent.

## At a glance — 16 tools, 60+ situations

```
DISCOVERY     query · resolve         "find me X"
LOCAL CONTEXT context                 "what's around X?"
RELATIONSHIPS references · path       "who connects to X?"
RISK          impact · rename_plan    "what breaks if X changes?"
EXECUTION     trace                   "how does data flow?"
SIMILARITY    similar                 "anything like X?"
SURFACE       contracts · entrypoints "what is X exposing?"
STRUCTURE     communities · centrality · ranking   "what is X made of?"
DELTA         detect_changes          "what did X just change?"
ARTIFACTS     export                  "show me X visually"
HEALTH        doctor                  "is X working?"
```

---

## A. DISCOVERY — "find me X"

### A1. `cos_graph_query(q, kinds, limit)`

The first call you should make when you don't know the canonical uid.

| Situation | Query | Wins over |
|---|---|---|
| "Where is the dispatch function?" | `cos_graph_query("dispatch", kinds=["function","method"])` | Multi-grep `def dispatch(`, `def Dispatch(`, ... |
| "Find the User model" | `cos_graph_query("User", kinds=["class"])` | grep `class User` (catches subclasses, decorated names) |
| "Anything called *config*" | `cos_graph_query("config", limit=20)` | grep noise from comments, strings |
| "MCP tools matching *graph*" | `cos_graph_query("graph", kinds=["mcp_tool"])` | manual scan of `@mcp.tool(name=...)` |
| "Hooks matching *enforce*" | `cos_graph_query("enforce", kinds=["hook"])` | scan `core/hooks/` |
| Resolve a path → uid | `cos_graph_query("adapters/claude/sdk_dispatcher.py")` | (auto-fallback in 1 call) |

**TIP:** prefer SHORT terms or paths. Long natural-language queries
("functions classes entry points") return weak matches because the
index is built from labels + docstrings, not free text.

**FALLBACK:** if the lexical pass returns nothing AND your query looks
like a path (`/`, `::`, ext), the tool transparently runs `_resolve_uid`
so you get a single-item hit instead of empty results.

### A2. `cos_graph_resolve(name_or_path)` *(implicit, via query fallback)*

Get the canonical uid for a label / path / partial uid. The graph_query
fallback covers this — pass any of:
- `"sdk_dispatcher.py"` → `code:file:adapters/claude/sdk_dispatcher.py`
- `"adapters/claude/sdk_dispatcher.py"` → same
- `"ClaudeSDKDispatcher.dispatch"` → `code:method:...::ClaudeSDKDispatcher.dispatch`

---

## B. LOCAL CONTEXT — "what's around X?"

### B. `cos_graph_context(uid, depth)`

The pre-edit hygiene call. Always cheaper than reading 5–10 neighbour files.

| Situation | Why graph wins |
|---|---|
| About to edit a function — what does it call? | Single envelope, all out-edges. |
| About to read a file — what's the imports + types? | One subgraph vs N opens. |
| Onboarding a contributor to a subsystem | depth=2 reveals 2-hop neighbours instantly. |
| "What's the contains-spine for this file?" | `include_spine=True` adds `repo→folder→file→class→method`. |
| Refactor scope sanity check | All call edges grouped by direction. |

| Edge types in the response | Meaning |
|---|---|
| `contains` | parent–child (folder→file, file→class, class→method) |
| `calls` | function call site |
| `imports` | module import |
| `inherits_from` | base class / Protocol / ABC |
| `has_param_type`, `returns_type` | type annotation |
| `field_of_type` | dataclass / Pydantic field type |
| `is_decorated_by` | decorator usage |
| `constructs` | object instantiation |
| `links_to`, `cites_heading`, `references_doc` | doc cross-link |
| `handles_route`, `handles_tool`, `handles_event` | API surface |

---

## C. RELATIONSHIPS — "who connects to X?"

### C1. `cos_graph_references(uid)` — inbound

| Situation | Without graph | With graph |
|---|---|---|
| "Who calls this function?" | grep variants × N + Read of each hit | one call, all call-sites with confidence |
| "Is this dead code?" | impossible to know reliably with grep | `count==0` is the only authoritative dead-code signal |
| "Audit before delete" | risk of deleting load-bearing code | full callers list, cross-file |
| "Find all decorators using my factory" | grep `@my_factory` (misses imported alias) | all `is_decorated_by` edges where target=my_factory |
| "Who imports module X?" | `grep -rn "from X import"` | `imports` edges to module:X |

### C2. `cos_graph_path(source_uid, target_uid)`

| Situation | Why graph wins |
|---|---|
| "How does ModuleA depend on ModuleB?" | shortest hop sequence as a list of edges |
| "Are these two functions in the same call chain?" | empty path = independent; path length = coupling depth |
| Reverse-engineer a dataflow | step-by-step concrete edges |

---

## D. RISK — "what breaks if X changes?"

### D1. `cos_graph_impact(uid, direction, depth, confidence_min)`

The pre-refactor call. Returns nodes grouped by risk tier.

| direction | meaning |
|---|---|
| `downstream` | what depends on X (default — what breaks if X changes) |
| `upstream` | what X depends on (what to read before changing X) |
| `both` | full neighbourhood |

| Risk tier (in response) | Edge confidence | Meaning |
|---|---|---|
| `will_break` | ≥0.85 | strong code edge — must be reviewed |
| `should_review` | 0.6–0.85 | likely affected — review |
| `context` | 0.3–0.6 | weakly related — usually noise |

| Situation | Concrete win |
|---|---|
| "Can I delete this function?" | combine references count + impact downstream |
| "Pre-refactor blast radius" | depth=3 reveals indirect dependents |
| "Find blast radius of a config flag" | works for any node — file, function, contract |
| "Who depends on a doc heading?" | links_to + cites_heading edges |

### D2. `cos_graph_rename_plan(uid, new_name)`

The full rename target list — call-sites, doc refs, tests, fixtures, string literals.

| Situation | What you'd miss with grep alone |
|---|---|
| Rename `User` → `Customer` | grep `User` matches `UserAgent`, `username`, … (false positives); rename_plan returns precise call-sites |
| Rename a public API method | doc refs in markdown, test fixtures, OpenAPI specs |
| Rename an MCP tool | per-line locations in `@mcp.tool(name=)`, dispatcher map, audit doc |
| Rename a hook script | registry.yaml entry, install.sh, adapter dispatcher |
| Rename a TASK-XXX swimlane label | task body, sync state, board UI |

### D3. `cos_graph_detect_changes(files)`

Pre-commit blast-radius — pass changed files, get affected graph nodes.

| Situation | Use |
|---|---|
| Pre-commit gate | `cos_graph_detect_changes(files=git_diff)` |
| "Did I just break something else?" | response shows `affected_uids` and `breaking_edges` |
| Reviewer checklist | groups changes by risk tier |

---

## E. EXECUTION — "how does data flow?"

### E. `cos_graph_trace(entry_uid)`

Forward execution walk from an entry point.

| Situation | Outcome |
|---|---|
| "Trace from `main` to result" | ordered call chain |
| "Map an HTTP handler's full path" | route → handler → service → repo → DB |
| Fault isolation | reverse trace from suspected node to entry |
| Async flow | follows await edges where extractor captured them |

---

## F. SIMILARITY — "anything like X?"

### F. `cos_graph_similar(uid, top_k)`

| Situation | Outcome |
|---|---|
| "Refactor candidate detector" | top-k near-duplicates by embedding similarity |
| "Avoid re-implementing" | before writing a new helper, check similar |
| Code review — "didn't we have this?" | yes, here it is |
| Onboard to unfamiliar code | "find me functions like this one I understand" |

---

## G. API SURFACE — "what is X exposing?"

### G1. `cos_graph_contracts(kinds)`

| `kinds` value | Returns |
|---|---|
| `["http"]` | every Flask/FastAPI/Fiber route node |
| `["mcp"]` | every `@mcp.tool` registration |
| `["event"]` | every event handler |
| `["http","mcp"]` | union |
| omitted | all of them |

| Situation | Win |
|---|---|
| "List all MCP tools" | one call vs grep-all + scan |
| "Compare API surfaces between branches" | snapshot before / after |
| Security audit — input handlers | every entry to `verify_auth` |
| OpenAPI generation seed | structural source for spec gen |

### G2. `cos_graph_entrypoints()`

Returns scored entry-point candidates: HTTP, MCP, CLI, scheduled, signal handlers.

| Situation | Use |
|---|---|
| Onboarding | "where do users actually enter this code?" |
| Coverage analysis | every entry should have a test |
| Architecture review | the entry list IS the surface |

---

## H. STRUCTURE — "what is X made of?"

### H1. `cos_graph_communities()`

Louvain-detected subsystems — clusters of nodes more connected to each
other than the rest.

| Situation | Outcome |
|---|---|
| Onboard to a new repo | natural subsystems revealed without manual archaeology |
| "What are the modules really?" | community != folder layout — surfaces hidden cohesion |
| Refactor planning | move a community together, not file-by-file |
| Visualisation | colour graph by community in /graph UI |

### H2. `cos_graph_centrality(by="degree"|"betweenness")`

| Situation | Outcome |
|---|---|
| "Which functions are chokepoints?" | highest-degree nodes deserve extra review |
| "Where would a bug hurt the most?" | high-betweenness — every flow passes through |
| Test prioritisation | hub nodes get the integration tests |

### H3. `cos_graph_ranking(query)`

PageRank with optional query personalisation. Surfaces "important nodes
for this query."

| Situation | Outcome |
|---|---|
| Knowledge condensation | the top-N ranked nodes are the canonical concepts |
| Better search ordering | query-personalised PageRank beats fuzzy filename match |
| Documentation sourcing | rank `q="auth"` to find canonical auth nodes |

---

## I. ARTIFACTS — "show me X visually"

### I. `cos_graph_export(format, root_uid, max_nodes)`

| `format` | Use |
|---|---|
| `mermaid` | paste into markdown for review / docs |
| `dot` | feed to graphviz for static diagrams |
| `json` | drive the Hub UI's Sigma.js canvas |

| Situation | Win |
|---|---|
| Architecture doc snippet | always-fresh diagram, not hand-drawn drift |
| PR review aid | "here's the blast radius as mermaid" |
| Subsystem summary for onboarding | export a community's subgraph |

---

## J. HEALTH — "is X working?"

### J. `cos_graph_doctor()`

| Reports | Action |
|---|---|
| Orphan nodes (no edges) | likely indexer miss; consider re-extract |
| Dangling edges (target uid missing) | bug — file the issue |
| Duplicate uids | extractor regression |
| Backend status | which backend answered, fallback flag |

---

## K. Token economics — concrete savings table

| Workflow | Without graph | With graph | Saving |
|---|---|---|---|
| "Where is `cos_safe_tool` called?" | 6 grep variants + Read 4 hits = ~3920 tok | `cos_graph_references` ~280 tok | **93%** |
| Plan rename `foo` → `bar` | iterative grep + edit + re-grep × 3 cycles ≈ ~6000 tok | `cos_graph_rename_plan` ~450 tok | **92%** |
| Audit MCP API surface | Read 12 register files × 1500 tok = ~18000 tok | `cos_graph_contracts(kinds=["mcp"])` ~700 tok | **96%** |
| Onboard / find subsystems | Read 50 README+entry files = ~120K tok | `cos_graph_communities` + `cos_graph_export` ~3K tok | **97%** |
| Pre-commit blast-radius | git diff + manual chase ~5–10K tok | `cos_graph_detect_changes` ~600 tok | **>90%** |
| Find similar helper before writing | grep half a dozen candidates + read each = ~10K tok | `cos_graph_similar` ~400 tok | **96%** |

Cumulative on one COMPLICATED task: **15K–50K tok saved** — often
the difference between fitting in context and forcing a compact.

---

## L. When the graph is NOT the right call

| Need | Use instead |
|---|---|
| String literal in source (error message, log text, copy) | grep / `cos_doc_search` |
| Config value lookup | direct read |
| Memory of past sessions ("did I solve this?") | `cos_search`, `cos_timeline` |
| Spec / requirements | `cos_doc_search` |
| Task / ticket by topic | `cos_task_search` |
| Verifying a string-replace landed | `grep -rnF` |
| Search inside `node_modules/` / `.venv/` | grep (graph excludes) |

The graph is **structural**. For literal text, free-form facts, or
runtime state, use the appropriate other tool.

---

## M. Discovery & enforcement chain (this repo)

```
Prompt with structural words
    ↓
nudge-graph-os.sh (UserPromptSubmit) → inline tool recommendation
    ↓
Skill graph-explorer (auto-load on core/**/*.py via skill-enforcement)
    ↓
Agent calls cos_graph_*
    ↓
_ok() touches .graph-call-seen     ← session marker
    ↓
Edit attempt
    ↓
enforce-skill (BLOCKS if no graph-explorer) →
enforce-graph-context (warn/strict on load-bearing) →
enforce-graph-first-read (warn/strict if Read load-bearing w/o prior graph call)
    ↓
Edit lands → auto-reindex-docs (PostToolUse) keeps graph fresh
```

Toggles:
- `COS_ENFORCE_GRAPH_CONTEXT=off|1|strict` (default 1=warn)
- `COS_ENFORCE_GRAPH_FIRST=off|1|strict` (default 1=warn)
- `COS_ENFORCE_RENAME_PLAN=off|1|strict` (default 1=warn)

Promote to `strict` when you want hard blocks instead of warnings.
