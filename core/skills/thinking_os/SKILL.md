---
name: thinking_os
description: >
  Cognitive operating system for structured problem solving. Use when
  designing features, planning projects, debugging issues, implementing
  solutions, analyzing requirements, writing specs, breaking down tasks,
  investigating bugs, architecting systems, reviewing designs, or
  thinking through any non-trivial problem. Supersedes genius-thinking.
---

# Thinking OS — Full Methodology

## Purpose

Complement the always-active Kernel rule (`.claude/rules/thinking_os.md`) with the complete Zoom cycle, Process Manager, and 10 Thinking Tools. Load this skill when the Complexity Gate returns COMPLICATED or COMPLEX. Source of truth: `docs/workflow-docs/thinking_os-final-edition.md`.

---

## Kernel Decisions (Detailed)

### Complexity Gate (Depth Routing)

Gate classification (Q1 + Q2) is handled by the always-active rule. Use this matrix to determine **depth of analysis**:

```
                │ 1 dim         │ 2-4 dim         │ 5+ dim
────────────────┼───────────────┼─────────────────┼─────────────────
CLEAR           │ Just do it    │ Quick checklist  │ Rare — batch it
COMPLICATED     │ Single Zoom In│ Light Zoom cycle │ Full Zoom cycle
COMPLEX         │ Probe + test  │ Zoom + test/dim  │ Full Zoom + prototype
CHAOTIC         │ Act now       │ Act now, Zoom    │ Act now, Zoom later
CONFUSION       │ Break it down │ Break it down    │ Separate problems
```

For COMPLEX problems, activate **Experiment Protocol** before full Zoom In:
1. HYPOTHESIS: "I believe [X] will work because [Y]."
2. SMALLEST TEST: cheapest/fastest way to validate
3. SUCCESS/FAILURE SIGNALS: measurable metrics
4. TIMEBOX: max time before deciding
5. LEARN: update Orient and continue

### Zoom Out

**First Zoom Out (before any work):**
1. IDENTIFY DIMENSIONS — independent aspects of the problem
2. PRIORITY HEURISTIC — which dimension first?
   - (a) DEPENDENCY: most dependencies → build first
   - (b) UNCERTAINTY: most unknowns → validate early
   - (c) BOTTLENECK: blocks others → unblock it
   - (d) EVOLUTION (Wardley): novel → deep analysis, commodity → best practice
   - Priority: (c) > (a) > (b) > (d)
3. ASSIGN DEPTH per dimension: Deep / Medium / Light
4. ASSIGN PHASE per dimension: MVP / v1 / v2
5. FLAG UNKNOWNS — state assumptions explicitly

**Subsequent Zoom Outs:**
1. Ask Process Manager: "What's done? Pending? Needs revisit?"
2. Consistency check: cross-dimension outputs compatible?
3. Cross-dimension insights: patterns to unify? shared components duplicated?
4. Reframe Trigger check (4 conditions)
5. Max iteration check (3rd cycle? → deliver with caveats)
6. Route: highest priority pending dimension → Zoom In

### System Sketch (First Cycle Only)

Before going deep on ANY dimension, draw a rough map of the whole system. For each dimension: PURPOSE (1 sentence), KEY ENTITIES, CONNECTIONS to other dimensions, RISK SMELL (most likely failure). Must fit one screen. Max 10% of total effort.

### Orient (Separate Phase in Core Loop — Between Classify and Plan)

Orient is a **dedicated phase** in the Core Loop, not just a transition step. It is the ONLY phase where targeted file reading happens. From John Boyd's OODA Loop — the most critical step.

**In the Core Loop context:**

- Classify phase produces a Dimension Map + Read List (dry, no files read)
- Orient phase reads ONLY the files from that Read List
- Plan phase synthesizes Orient findings into an action plan

**Orient steps:**

1. **TARGETED READ** — Read each file from the Classify Read List. After each file, note key findings in task Notes. Don't rely on raw file staying in context. Do NOT read files not in the Read List.
2. **MEMORY CHECK** (3-layer protocol, max 500tok total):
   - **Step 1 — Search:** `thinking_os_search(query="{domain} {task_title}", limit=5)` → index-level results (~50tok)
   - **Step 2 — Suggest:** `cos_learn_suggest(domain="{domain}", complexity="{complexity}")` → actionable patterns with spaced repetition
   - **Step 3 — Details (if high-confidence hit):** `thinking_os_details(pattern_id, source)` for patterns with confidence > 0.7 (~500tok)
   - **Post-task:** After task-done, call `cos_learn_validate(pattern_id, was_helpful)` for each pattern used
   - **Empty result:** If no patterns found, proceed normally — "No relevant past patterns found"
   - **Token guard:** Drop lowest-confidence results first if budget exceeded
3. **REPO SEARCH** — Grep/Glob for existing code related to the task. [P1] If found, diff against spec. [P2]
4. **MODEL UPDATE**: "Has my understanding changed? Adjust Dimension Map? New files to read?"
   - If new dimensions discovered → read new files, update map
   - If Reframe Trigger fires (problem redefined, actor missing, boundary changed, constraint changed) → back to Classify
5. **EVOLUTION CHECK** (Wardley): Novel → deep. Emerging → research. Good Practice → adapt. Commodity → use off-the-shelf.
6. **BIAS CHECK**: "Am I anchored to first idea? Avoiding uncomfortable dimension? Over-engineering interesting one?"

### Stakeholder Checkpoint (First Cycle Only)

Present plan before diving deep:
1. "Here's how I understand the problem"
2. "I've identified these dimensions"
3. "Going deep on [X] first because [reason]"
4. "Final deliverable will be: [format from Q7]"
5. "Assuming [key assumptions]. Correct?"
6. "Anything missing or reprioritize?"

For AI agents: if prompt is ambiguous → ASK. If clear → "Here's my plan, proceeding unless you say otherwise."

### Zoom In

1. SCOPE this dimension — run Tool 1 (Problem Framing) scoped to it
2. SELECT TOOLS — use Tool Selection Guide below
3. SELECT DEPTH — Deep / Medium / Light from Zoom Out
4. EXECUTE — run selected tools at selected depth
5. VALIDATE — "Anything that affects other dimensions? Am I guessing? Is output testable?"

### Dimension Dependency Matrix

```
→ = outputs to    ← = depends on    ↔ = bidirectional    ↑↓ = constrains
```
When a dimension completes, check matrix for affected dimensions. Kernel decides: revisit now or defer.

---

## Process Manager

Prevents the most dangerous failure: **thinking you're done when you're not.**

### Dimension Map

```
Dimension        │ Status    │ Depth  │ Phase │ Revisit? │ Blocked by
─────────────────┼───────────┼────────┼───────┼──────────┼───────────
[fill per task]  │ ○/◐/✓    │ D/M/L  │ MVP/v1│ Yes/No   │ [dim]
```

### Assumption Registry

```
#  │ Assumption                    │ Source     │ Confidence │ Validated?
───┼───────────────────────────────┼────────────┼────────────┼───────────
[fill per task]                    │ Decision/  │ High/Med/  │ Yes/No/
                                   │ Assumption │ Low        │ Test!
```

### Cross-Dimension Conflict Log

```
# │ Dim A │ Dim B │ Issue │ Resolved?
```

### 7 Rules

1. **No Premature Completion** — never "done" while any MVP dimension is Pending
2. **Revisit Enforcement** — "Needs Revisit" must be revisited before completion
3. **Consistency Gate** — for each dependency pair (→ or ↔), verify outputs are compatible
4. **Phase Discipline** — all MVP dimensions complete before v1 starts. Exception: v1 blocks MVP → pull forward
5. **Assumption Review** — before final output, review all assumptions with confidence < High
6. **Conflict Resolution** — all Conflict Log items resolved before completion
7. **Mandatory Documentation** — Tool 10 (Record) MUST run before declaring completion

---

## The 10 Thinking Tools

Called BY the Kernel, not in fixed order.

### Tool 1 — Problem Framing
**When:** Starting any new problem or dimension.
7 questions: PROBLEM (testable), ACTORS/GOALS, BOUNDARY (data ownership), CONSTRAINTS, SUCCESS (measurable), ASSUMPTIONS (hidden assumption = future bug), OUTPUT FORMAT (determines analysis depth).
First Principles: "What is the source of truth?" · "What events change state?" · "Am I copying a pattern or solving MY problem?"

### Tool 2 — Decompose
**When:** Problem too big to tackle whole.
Two types needed for complex systems:
- **Technical** (how it's built): Backend, Database, API, Frontend, Infrastructure
- **Domain** (what it's about, from DDD): Identity & Auth, Content Management, Billing, etc.
Rules: no item in two parts, nothing important missing, clear membership criterion.

### Tool 3 — Behavior Modeling
**When:** Something changes over time with distinct states.
No independent dimensions → flat state machine. Independent dimensions → orthogonal regions. Shared behavior → hierarchical nesting.
Per transition: Event, Guard, Side Effect, Timeout.
Validation: impossible state combo? unhandled event? dead-end state?

### Tool 4 — Rules Modeling
**When:** 2-5 conditions combine to produce outcome. (6+ conditions → split tables or rule engine)
Build decision table. Every table specifies: default behavior, conflict resolution.
Collapse: remove impossible combos, merge same-result rows, use * for don't-care.

### Tool 5 — Scenario Modeling
**When:** Verifying real usage flows. Run AFTER Behavior (Tool 3) → Rules (Tool 4).
Three types: Happy Path, Alternate Path, Exception Path.
Per scenario: Trigger, Preconditions, Steps, Postconditions, User sees, System sees.
**Critical:** Run scenarios PER RELEVANT DIMENSION.

### Tool 6 — Risk Pass
**When:** Finding what could go wrong before it does.
Four lenses: Inversion, Pre-Mortem, Threat Modeling, Abuse Cases.
8 categories: Security, Data Integrity, UX Failure, Operational, Legal/Compliance, Abuse/Fraud, Performance/Scaling, Dependency/Vendor.
Output: Risk Register (# / Risk / Category / Severity / Mitigation / Phase).
This tool discovers risks — does NOT redesign. If new state/rule/actor found → flag for Kernel.

### Tool 7 — Second-Order Thinking
**When:** Important decision with lasting consequences.
Ask "And then what?" 2+ layers: Decision → 1st order → 2nd order → 3rd order.
Don't confuse with Tool 3: "What happens if we delete?" = consequences (here). "From which states is deletion allowed?" = behavior (Tool 3).

### Tool 8 — Simplify Without Lying
**When:** After divergent thinking (Tools 2-7), before output.
Remove: fake complexity, unrealistic scenarios, premature abstractions, duplicates, features nobody asked for.
Keep: real risks, legal constraints, genuine edge cases.
Phase: MVP ("broken if removed"), v1 ("users complain but survive"), v2 ("future speculation").
Mark "Deferred" not "Deleted." Deferred = wisdom, Deleted = negligence.

### Tool 9 — Convert to Action
**When:** Thinking done, time to make executable.
Per action: what to do, due, depends on, done-when (testable criteria), linked risks, linked states, phase.

### Tool 10 — Record and Communicate
**When:** Output needs capture or sharing.
Pyramid Principle: conclusion first → supporting branches → details.
Document type (Diátaxis): Tutorial / How-to / Reference / Explanation. Don't mix types.
Architecture docs only: C4 model (Context → Container → Component → Code).

---

## Tool Selection Guide

```
Dimension Type          │ Essential Tools            │ Notes
────────────────────────┼────────────────────────────┼──────────────────────
Core Logic (backend)    │ 1, 2, 3, 4, 5, 6, 7, 8, 9 │ Full analysis
Data / Schema (DB)      │ 1, 2, 3, 4, 8, 9          │ Behavior = states map to fields
Interface Contract (API)│ 1, 2, 4, 5, 8, 9          │ Scenarios matter
User Experience (FE)    │ 1, 2, 5, 6, 7, 8, 9       │ Scenarios per platform!
Security (auth, crypto) │ 1, 3, 4, 6, 8, 9          │ Risk Pass is king
Infrastructure (CI/CD)  │ 1, 2, 6, 8, 9             │ Risk = what breaks in prod
Standards / Style       │ 1, 2, 8, 9                │ Lightweight pass
Content / Marketing     │ 1, 2, 5, 7, 8, 9, 10      │ Scenarios + Record
```

If dimension spans multiple types → take UNION of tools for all applicable types.

## Depth Levels

- **Deep:** All selected tools run completely. Every state modeled, every scenario written, risk pass thorough. Use for: core business logic, security, primary user flows.
- **Medium:** Tools on critical paths only. Key states, main scenarios (happy + top 2 exceptions), quick risk scan. Use for: database schema, API contract, secondary flows.
- **Light:** Problem Framing + Decompose + Simplify only. No detailed modeling. Use for: code standards, peripheral features, v2 items.

## Safety Mechanisms

- **Max 3 Zoom cycles** — then deliver with caveats listing uncertainties
- **Max 8 MVP dimensions** — more = problem too big, break into separate problems
- **Reframe Trigger** — if during any Zoom In: problem redefined, actor missing, boundary changed, constraint changed → STOP → Tool 1 → restart
- **Experiment Protocol** — for COMPLEX: hypothesis → smallest test → success/failure signal → timebox → learn

---

## Domain Skills Registry

See `.claude/rules/skill-enforcement.md` for the full skill routing table. After Thinking OS analysis, defer to the appropriate domain skill(s) for implementation. Thinking OS provides analysis and thinking structure; domain skills provide implementation patterns.

---

## Integration with Core Loop

How Thinking OS maps to AGENTS.md 5-phase Core Loop:

1. **Rule** (always active) provides Complexity Gate → runs in **Classify** phase (dry, no reads)
2. **CLEAR** → skip to Execute phase directly, no skill needed
3. **COMPLICATED / COMPLEX** → load this skill:
   - **Classify phase** (dry): Complexity Gate + Dimension Map + Read List
   - **Orient phase** (read): Targeted file reads + Memory Check + Repo Search + Model Update
   - **Plan phase** (think): Zoom In/Out cycles (up to 3) using 10 Thinking Tools:
     - Zoom Out → identify dimensions, assign depth/phase
     - System Sketch → rough map of whole system
     - Stakeholder Checkpoint → confirm plan with user
     - Zoom In → execute tools on one dimension
     - Repeat until all MVP dimensions covered
   - **Execute phase** (do): implement the plan, on-demand reads only
4. Output of Plan phase feeds into Execute: domain skill selection, implementation plan, risk awareness
5. After task completion: outcome recorded to thinking_os.db via `cos_metric_record`. Every 10 tasks, Learning Loop extracts patterns and may promote them to rules or skill-enforcement updates.
