<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-06 -->
# Thinking OS — Final Edition

> Nav: [Docs Index](../../docs/00-index.md)

Purpose: Comprehensive reference for the Thinking OS cognitive methodology — Cynefin Complexity Gate, Zoom cycles, dimension mapping, and 10 thinking tools.
Read when: Onboarding to Thinking OS, designing the methodology, or studying the full theoretical framework.
Skip when: Already familiar — use the kernel rule in `src/core/rules/thinking_os.md` instead.
Read next: `src/core/skills/thinking_os/SKILL.md` for the executable workflow.

### A Cognitive Operating System for Genius-Level Problem Solving

---

> **This is not a formula. It's a mind.**
>
> A formula says "do step 1, then step 2."
> A mind sees the whole, decides where to go deep,
> goes deep, comes back, checks what changed, adapts.
>
> That's the difference between a junior and a genius.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  KERNEL — The Decision-Making Mind                   │
│  Classifies problems, assigns depth, routes tools,   │
│  runs the Zoom cycle, triggers reframes              │
├─────────────────────────────────────────────────────┤
│  PROCESS MANAGER — The Coverage Guardian             │
│  Maintains Dimension Map, tracks progress,           │
│  enforces consistency, logs assumptions              │
│  (data provider to Kernel — Kernel decides,          │
│   Process Manager informs)                           │
├─────────────────────────────────────────────────────┤
│  MEMORY — Experience & Knowledge (future layer)      │
│  Patterns, lessons, past mistakes, project context   │
│  Searched automatically before every Kernel decision │
├─────────────────────────────────────────────────────┤
│  APPS — 10 Thinking Tools                            │
│  Called by Kernel on whichever dimension,             │
│  at whatever depth, in whatever order needed         │
└─────────────────────────────────────────────────────┘
```

**Key boundary:** Kernel is the decision-maker. Process Manager is the
data provider. Kernel asks "what should I do next?" Process Manager
answers "here's what's done, pending, and inconsistent." Kernel decides.

**Memory (Designed, implementation in v4):** Three types planned —
Procedural (how I did it), Semantic (what I know), Episodic (what I
experienced). SQLite + embedding search. Confidence scores: validated /
observed / assumed. Orient step already has Memory Check placeholder —
when Memory layer is implemented, Orient will auto-search before
every Zoom In. Thinking OS works without Memory; Memory makes it wiser.

---

## The Kernel

The Kernel runs a continuous **Zoom cycle** with **System Sketch**,
**Orient** step (from John Boyd's OODA Loop), and **Stakeholder
Checkpoint**, and makes six types of decisions:

```
┌──────────────┐
│ ZOOM OUT     │ → See the whole picture
│              │   Classify, decompose, prioritize
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ SYSTEM SKETCH│ → Quick breadth-first pass (first cycle only)  ← NEW
│              │   "What does the whole system look like?"
│              │   Rough map of ALL dimensions before going deep
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ ORIENT       │ → Update your mental model
│              │   "Has my understanding changed?"
│              │   "What do I know now that I didn't before?"
│              │   This is where experience/intuition speaks
└──────┬───────┘
       │
       ▼
┌──────────────────┐
│ STAKEHOLDER CHECK│ → Confirm plan before going deep            ← NEW
│  (first cycle)   │   "Here's my plan. Does this match
│                  │    what you need?"
└──────┬───────────┘
       │
       ▼
┌──────────────┐
│ ZOOM IN      │ → Go deep on ONE dimension
│              │   Select tools, set depth, execute
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ ZOOM OUT     │ → Come back up and check
│              │   Coverage, consistency, what's next
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ ORIENT       │ → Update mental model again
└──────┬───────┘
       │
       ▼
   (repeat Zoom In → Zoom Out → Orient
    until all dimensions covered
    or max 3 full cycles reached)
```

**Why Orient matters (from OODA Loop, John Boyd 1960s):**
Boyd argued that Orient is the most critical step — not Observe
or Decide. Orient is the moment where you UPDATE YOUR UNDERSTANDING
of the situation based on what you've learned. Without it, you keep
acting on stale mental models. In Thinking OS, Orient happens twice:
between Zoom Out and Zoom In (before going deep), and as part of
Zoom Out (after coming back up). It's the "flash" where accumulated
knowledge reshapes how you see the problem.

---

### Kernel Decision 1: Complexity Gate

Before anything else, classify the problem using two questions.

**Question 1 — What is the nature of this problem?**

Adapted from the Cynefin framework (Dave Snowden, 1999; Harvard
Business Review, 2007). Cynefin classifies problems by the relationship
between cause and effect:

```
CLEAR
  I know the input, I know the output, I know how to get there.
  → Just do it. No Zoom cycle needed.

  Signal words: "standard", "CRUD", "same as before", "boilerplate"
  Example: "Write an endpoint that returns a list of blog posts."
  Response: Sense → Categorize → Respond (apply best practice)

COMPLICATED
  I know the TYPE of answer needed, but details require analysis.
  → Zoom cycle: light to medium.

  Signal words: "design", "architect", "implement", "integrate"
  Example: "Design the JWT authentication system with refresh tokens."
  Response: Sense → Analyze → Respond (apply good practice with expertise)

COMPLEX
  I don't know the right answer until I test and learn.
  → Zoom cycle: full, with emphasis on Scenarios and prototyping.
  → Activate Experiment Protocol (see below).

  Signal words: "best way to", "optimize", "user experience", "strategy"
  Example: "What's the best onboarding UX for new blog subscribers?"
  Response: Probe → Sense → Respond (experiment with safe-to-fail probes)

  EXPERIMENT PROTOCOL (from Scientific Method — activated for Complex):
  When Complexity Gate returns Complex, before full Zoom In:
  1. HYPOTHESIS: "I believe [X] will work because [Y]."
  2. SMALLEST TEST: "What's the cheapest/fastest way to test this?"
     (prototype, A/B test, paper mockup, spike, proof-of-concept)
  3. SUCCESS SIGNAL: "If hypothesis is right, I will see [metric]."
  4. FAILURE SIGNAL: "If hypothesis is wrong, I will see [metric]."
  5. TIMEBOX: "I will spend max [time] testing before deciding."
  6. LEARN: "What did I learn? Update Orient and continue."

  This prevents spending weeks designing something that could have
  been validated (or killed) in a day with a quick experiment.

CHAOTIC
  No time to analyze. Something is broken NOW.
  → Act first, then Zoom cycle afterward to prevent recurrence.

  Signal words: "down", "broken", "crash", "emergency", "data loss"
  Example: "Production server is down and users can't log in."
  Response: Act → Sense → Respond (stabilize, then analyze)

CONFUSION
  I don't know which of the above applies.
  → Break the problem into smaller pieces and classify each piece.

  Signal: you can't clearly place it in any domain above.
  Response: Decompose → Classify each piece → Proceed per piece.
```

**Question 2 — How many independent dimensions does this have?**

```
1 dimension     → Single Zoom In is enough
                  Example: "Write a database migration"

2-4 dimensions  → Standard Zoom cycle
                  Example: "Build a new API endpoint" (Backend + API + maybe Frontend)

5+ dimensions   → Full Zoom cycle with Dimension Map
                  Example: "Build user system" (Backend + DB + API + Frontend +
                           Mobile + Security + SEO + Code Standards)

8+ dimensions   → Problem is probably too big. Break into 2+ separate problems
                  first, then Thinking OS each one.
```

**Combined decision matrix:**

```
                │ 1 dim         │ 2-4 dim         │ 5+ dim
────────────────┼───────────────┼─────────────────┼─────────────────
CLEAR           │ Just do it    │ Do it, quick     │ Rare. If truly
                │               │ checklist        │ clear, batch it.
────────────────┼───────────────┼─────────────────┼─────────────────
COMPLICATED     │ Single        │ Light Zoom       │ Full Zoom
                │ Zoom In       │ cycle            │ cycle
────────────────┼───────────────┼─────────────────┼─────────────────
COMPLEX         │ Probe + test  │ Zoom cycle       │ Full Zoom +
                │               │ + test per dim   │ prototype
────────────────┼───────────────┼─────────────────┼─────────────────
CHAOTIC         │ Act now       │ Act now, Zoom    │ Act now, Zoom
                │               │ later            │ later
────────────────┼───────────────┼─────────────────┼─────────────────
CONFUSION       │ Break it      │ Break it         │ Break it into
                │ down          │ down             │ separate problems
```

---

### Kernel Decision 2: Zoom Out (See the Whole)

**First Zoom Out (before any work):**

```
1. IDENTIFY DIMENSIONS
   What are the independent aspects of this problem?
   Each dimension may need different tools at different depths.

2. PRIORITY HEURISTIC — which dimension first?

   a) DEPENDENCY: Which dimension creates the most dependencies?
      → Build it first. (Usually: data model / core business logic)

   b) UNCERTAINTY: Which dimension has the most unknowns?
      → Validate it early. (Usually: UX, third-party integrations)

   c) BOTTLENECK: Which dimension blocks others?
      → Unblock it. (Whatever other dimensions are waiting for)

   d) EVOLUTION (from Wardley Mapping): Is this dimension novel or commodity?
      → Novel = needs more time and deeper analysis
      → Commodity = use standard solution, don't reinvent
      (Example: JWT auth = commodity, use best practice.
       AI Agent access control = novel, needs deep thinking.)

   If (a), (b), (c), (d) point to different dimensions,
   prioritize (c) > (a) > (b) > (d).

3. ASSIGN DEPTH per dimension:

   Deep    → Core business logic, security, primary user flows
   Medium  → Database schema, API contract, secondary flows
   Light   → Code standards, peripheral features, v2 items

4. ASSIGN PHASE per dimension:

   MVP → "If I removed this, would the system be broken or unsafe?"
   v1  → "Users would complain but survive without this."
   v2  → "Driven by future speculation, not current demand."

5. FLAG UNKNOWNS
   What don't I know? Can I ask? If not, state assumptions
   explicitly and take the ambitious path (cover more),
   then phase into MVP/v1/v2.
```

**Subsequent Zoom Outs (between dimensions):**

```
1. ASK PROCESS MANAGER:
   "What's done? What's pending? What needs revisit?"
   (Process Manager provides data, Kernel decides action)

2. CONSISTENCY CHECK:
   "Does dimension A's output work with dimension B's output?"
   Use the Dependency Matrix to know which pairs to check.

3. CROSS-DIMENSION INSIGHTS:
   "Patterns I should unify? Shared components I'm duplicating?"

4. REFRAME TRIGGER — check if the whole problem needs re-definition:
   "Did I discover that...
    - the original problem was defined wrong?
    - a critical actor was missing from the start?
    - the system boundary needs to change?
    - a fundamental constraint changed?"
   If ANY of these → STOP. Go back to Problem Framing (Tool 1).
   Restart Zoom cycle from scratch with new framing.

5. MAX ITERATION CHECK:
   "Is this my 3rd full Zoom cycle?"
   If yes → deliver output with caveats listing remaining
   uncertainties. Don't loop forever.

6. ROUTE:
   "Which pending dimension is highest priority?"
   → Zoom In on that dimension.
```

---

### Kernel Decision 2: System Sketch (First Cycle Only)

**Runs once, between first Zoom Out and first Orient.**

Before going deep on ANY dimension, draw a rough map of the
whole system. This prevents the #1 failure mode discovered in
testing: spending 80% of effort on 1 dimension while 7 others
get nothing.

```
WHAT TO SKETCH (keep it rough — 1-2 sentences per dimension):

For each dimension identified in Zoom Out:
  1. PURPOSE: What does this dimension do in the system?
  2. KEY ENTITIES: What are the main things in this dimension?
  3. CONNECTIONS: How does it connect to other dimensions?
  4. RISK SMELL: What's the one thing most likely to go wrong here?

FORMAT: A simple map showing all dimensions and their connections.
Can be text, diagram, or table. Must fit on one page / one screen.
```

**Example for NakoAI (Content Platform):**

```
┌─────────────┐     ┌──────────────┐     ┌────────────┐
│ Auth &       │────→│ Backend Core │────→│ API        │
│ Dual-Actor   │     │ (content,    │     │ Contract   │
│ (novel!)     │     │  voting,     │     │ (2 flows:  │
│              │     │  reviews)    │     │  human+agent)
└──────┬───────┘     └──────┬───────┘     └─────┬──────┘
       │                    │                    │
       ↓                    ↓                    ↓
┌──────────────┐     ┌──────────────┐     ┌────────────┐
│ Database     │     │ Moderation   │     │ Frontend   │
│ (states map  │     │ (trust-based │     │ (dual-actor│
│  to fields)  │     │  workflow)   │     │  UI badges)│
└──────────────┘     └──────────────┘     └────────────┘
```

**Why this matters:** The Sketch reveals connections that pure
dimension listing misses. You see that API Contract needs two
flows (human + agent) BEFORE you deep-dive into Backend.
You see that Moderation is connected to Auth (trust system)
BEFORE you design them separately and discover the overlap later.

**Time budget:** Max 10% of total effort on Sketch.
If you're spending more, you're going too deep — that's Zoom In's job.

---

### Kernel Decision 3: Orient (Update Mental Model)

**Runs between every Zoom Out and Zoom In.**

Adapted from John Boyd's OODA Loop. Boyd insisted Orient is the
most important step because "you will always have an understanding
of the world that is some distance from reality due to bias,
out-of-date info, and lack of data."

```
Before each Zoom In, ask:

1. MODEL UPDATE
   "Based on what I just saw in Zoom Out, has my understanding
    of the problem changed?"
   "Do I need to adjust the Dimension Map, priorities, or phases?"

2. EVOLUTION CHECK (from Wardley Mapping)
   "The dimension I'm about to Zoom Into — is it:
    - Novel (never solved before → needs deep original thinking)
    - Emerging (solved by some, no standard → needs research + adaptation)
    - Good Practice (well-known solutions exist → apply with adaptation)
    - Commodity (completely standardized → use off-the-shelf, don't reinvent)"

   Novel/Emerging → Deep analysis, possibly Experiment Protocol
   Good Practice  → Medium analysis, adapt known patterns
   Commodity      → Light analysis, use best practice directly

3. MEMORY CHECK (when Memory layer is active)
   "Have I seen a similar dimension/problem before?"
   "What happened last time? What worked? What failed?"
   "What confidence level does that memory have?"

4. BIAS CHECK
   "Am I anchored to my first idea?"
   "Am I avoiding a dimension because it's uncomfortable?"
   "Am I over-engineering because it's interesting?"
```

**Why this matters:** Without Orient, you Zoom Out (see the picture)
and immediately Zoom In (start solving). That skips the crucial moment
where your understanding crystallizes and priorities shift. Orient is
where the "flash of insight" happens — where accumulated knowledge
reshapes how you see the next problem.

---

### Kernel Decision 4: Stakeholder Checkpoint (First Cycle Only)

**Runs once, after first Orient, before first Zoom In.**

Before diving deep, present your plan and get confirmation:

```
PRESENT TO STAKEHOLDER:

1. "Here's how I understand the problem: [1-2 sentences]"
2. "I've identified these dimensions: [list]"
3. "My plan is to go deep on [X] first because [reason]"
4. "The final deliverable will be: [output format from Q7]"
5. "I'm assuming [key assumptions]. Are these correct?"
6. "Anything I'm missing or should prioritize differently?"
```

**Why this matters:** In the NakoAI test, the Agent assumed Backend
should go first based on dependency analysis. But the stakeholder
might have said "Agent Orchestration is the core of this product,
start there." This single checkpoint could redirect the entire analysis.

**When to skip:** If stakeholder is unavailable or explicitly said
"just do it," proceed with stated assumptions and flag them clearly.

**For AI Agents:** If the user's prompt is ambiguous about priorities,
ASK before proceeding. If the prompt is clear and detailed, a brief
"Here's my plan, proceeding unless you say otherwise" is sufficient.

---

### Kernel Decision 5: Zoom In (Go Deep)

```
1. SCOPE THIS DIMENSION
   "What exactly am I solving in THIS dimension?"
   Run Tool 1 (Problem Framing) scoped to this dimension.

2. SELECT TOOLS
   Use the Tool Selection Guide to pick which of the 10 tools
   this dimension needs. If the dimension spans multiple types
   (e.g. Payment Gateway = Core Logic + Security + Interface),
   take the UNION of tools for all applicable types.

3. SELECT DEPTH
   Deep / Medium / Light — assigned during Zoom Out.

4. EXECUTE
   Run selected tools at selected depth.

5. VALIDATE BEFORE ZOOM OUT
   "Did I discover anything that affects other dimensions?
    If yes → flag it for Process Manager."
   "Am I guessing anywhere? Flag it with confidence level."
   "Is my output testable and concrete?"
```

---

### Kernel Decision 6: Dimension Dependency Awareness

The Kernel uses a dependency matrix to know which dimensions
affect each other. Without this, consistency checks are guesswork.

**Template (filled per project):**

```
               Backend  Database  API  Frontend  Mobile  Security
Backend          -        →       →      →        →        ↔
Database         ←        -       ↑      -        -        ↑
API              ←        ↓       -      →        →        ↔
Frontend         ←        -       ←      -        -        ↑
Mobile           ←        -       ←      -        -        ↑
Security         ↔        ↓       ↔      ↓        ↓        -

→ = outputs to    ← = depends on    ↔ = bidirectional    ↑↓ = constrains
```

**How it's used:**
When Backend is completed or changed, Process Manager checks the matrix
and flags: "API, Frontend, Mobile, Security may need revisit."
Kernel then decides whether to revisit immediately or defer.

---

## The Process Manager

The Process Manager prevents the most dangerous failure:
**thinking you're done when you're not.**

### It maintains:

**1. Dimension Map**

```
Dimension        │ Status    │ Depth  │ Phase │ Revisit? │ Blocked by
─────────────────┼───────────┼────────┼───────┼──────────┼───────────
Backend Logic    │ ✓ Done    │ Deep   │ MVP   │ No       │ -
Database Schema  │ ○ Pending │ Medium │ MVP   │ -        │ Backend
API Contract     │ ○ Pending │ Medium │ MVP   │ -        │ Backend
Frontend UX      │ ○ Pending │ Deep   │ MVP   │ -        │ API
Mobile UX        │ ○ Pending │ Medium │ v1    │ -        │ API
Security         │ ◐ Partial │ Deep   │ MVP   │ Yes      │ Frontend
SEO              │ ○ Pending │ Light  │ v1    │ -        │ Frontend
Code Standards   │ ○ Pending │ Light  │ MVP   │ -        │ -
```

**2. Assumption Registry**

```
#  │ Assumption                              │ Source     │ Confidence │ Validated?
───┼─────────────────────────────────────────┼────────────┼────────────┼───────────
1  │ Email is primary identifier             │ Decision   │ High       │ Yes
2  │ All users have valid email              │ Assumption │ Medium     │ No — test!
3  │ Stripe uptime > 99.9%                   │ External   │ High       │ Accepted
4  │ Mobile and Web share same auth flow     │ Assumption │ Medium     │ No — verify
```

**3. Cross-Dimension Conflict Log**

```
Conflict │ Dim A     │ Dim B    │ Issue                        │ Resolved?
─────────┼───────────┼──────────┼──────────────────────────────┼──────────
1        │ Backend   │ Frontend │ Token storage strategy       │ No
         │           │          │ Backend says JWT, Frontend   │
         │           │          │ needs to decide memory vs    │
         │           │          │ HttpOnly cookie              │
```

### Process Manager Rules:

```
Rule 1: NO PREMATURE COMPLETION
  Never say "done" while any MVP dimension is ○ Pending.

Rule 2: REVISIT ENFORCEMENT
  If a dimension is marked "Needs Revisit" → must be revisited
  before declaring completion.

Rule 3: CONSISTENCY GATE
  Before final output, for each pair in Dependency Matrix that
  has → or ↔, verify outputs are compatible.

Rule 4: PHASE DISCIPLINE
  All MVP dimensions complete before v1 dimensions start.
  Exception: if a v1 dimension blocks an MVP dimension, pull forward.

Rule 5: ASSUMPTION REVIEW
  Before final output, review all assumptions with confidence < High.
  Either validate, ask, or explicitly accept the risk.

Rule 6: CONFLICT RESOLUTION
  All items in Conflict Log must be resolved before completion.

Rule 7: MANDATORY DOCUMENTATION
  Tool 10 (Record) MUST run before declaring completion.
  Raw analysis is not a deliverable. The output must be
  structured per Q7 (Output Format) from Problem Framing.
```

---

## The 10 Thinking Tools (Apps)

These are called BY the Kernel, not in fixed order.

---

### Tool 1 — Problem Framing

**When:** Starting any new problem or dimension.

```
1. PROBLEM:      What exactly am I solving? (testable, not vague)
2. ACTORS/GOALS: Who is involved, what does each want?
3. BOUNDARY:     What's inside my control? What's outside?
                 Who owns the truth of each piece of data?
4. CONSTRAINTS:  Time, money, energy, rules, dependencies
5. SUCCESS:      How do I measure it? (concrete, measurable)
6. ASSUMPTIONS:  Where am I guessing? Write each one down.
                 Hidden assumption = future bug.
7. OUTPUT:       What should the final deliverable look like?
                 (Architecture doc? PRD? Technical spec? Task board?
                  API contract? Diagram? Code?)
                 This determines how wide and how deep the analysis goes.
```

First Principles Thinking is embedded here:
- Q3 prevents naive oversimplification ("user = identity + permission" is wrong;
  user/account/identity/auth/profile/session/consent are separate concepts)
- Q6 separates fact from belief

**Practical First Principles — ask:**
- "What is the source of truth for this data?"
- "What events change the state of this thing?"
- "Am I copying a pattern or solving MY problem?"

NOT: "What is a user?" (philosophy)
BUT: "Who owns the truth of user identity — our DB or the OAuth provider?" (engineering)

---

### Tool 2 — Decompose

**When:** A problem or dimension is too big to tackle whole.

Break into parts that **don't overlap** and **together cover everything.**
Can apply at any level — whole problem into dimensions, or one dimension
into sub-problems.

**Two types of decomposition (both needed for complex systems):**

```
TECHNICAL DECOMPOSITION (how it's built):
  ├── Backend
  ├── Database
  ├── API
  ├── Frontend
  ├── Mobile
  └── Infrastructure

DOMAIN DECOMPOSITION (what it's about — from Domain-Driven Design):
  ├── Identity & Auth (user accounts, login, sessions)
  ├── Content Management (posts, comments, media)
  ├── Subscription & Billing (plans, payments, invoices)
  └── Notification (email, push, in-app)
```

**Why both?** Technical decomposition tells you WHERE code lives.
Domain decomposition tells you WHERE business logic lives.
They cross-cut each other: "Subscription" has Backend code AND Frontend
code AND Database schema. Without domain decomposition, you miss
business boundaries. Without technical decomposition, you miss
implementation boundaries.

**Domain Decomposition principles (from Eric Evans, DDD 2003):**
- Each domain boundary (Bounded Context) has its own language and rules
- "User" in Identity means something different from "User" in Billing
- Don't force one model to serve all domains
- Identify which domain owns the truth of each piece of data

**Rules:**
- Each part has a clear membership criterion
- No item belongs in two parts
- Nothing important is missing
- If parts are technical but problem is business-facing → add domain decomposition
- If parts are domain but problem is implementation → add technical decomposition

**This tool does NOT discover behavior, rules, or risks.**
Those come from Tools 3-6.

**Validation:** "Is any item in two buckets? Is any bucket empty?
Is there a bucket I haven't thought of?
Do I have BOTH technical AND domain decomposition for complex systems?"

---

### Tool 3 — Behavior Modeling

**When:** Something changes over time and has distinct states.

**First ask: does this system have independent behavioral dimensions?**

```
NO independent dimensions → flat state machine is fine (2-4 states, linear)

YES independent dimensions → use orthogonal regions
  Example: Subscription has billing_state AND access_state AND user_intent
  Without orthogonal regions: 4×3×3 = 36 flat states (unmanageable)
  With orthogonal regions: 4+3+3 = 10 states in 3 tracks (clear)

States share common behavior? → use hierarchical nesting
  Example: "active" and "past_due" both respond to "cancel_requested"
  → make them substates of "subscribed" superstate
```

**For each transition, record:**

```
[source_state] → [target_state]
  Event:       what triggers it
  Guard:       what conditions must be true
  Side Effect: what happens alongside the transition
  Timeout:     if time-based, how long
```

**Validation:**
- "Is there an impossible state combination?" (e.g. deleted + authenticated)
- "Is there an event that no state handles?"
- "Is there a state with no exit transition?" (dead end)

Based on David Harel's Statecharts (1987): "A complex system cannot be
beneficially described in a flat, unstratified fashion."

---

### Tool 4 — Rules Modeling

**When:** Multiple conditions combine to produce an outcome.

**When to use Decision Table:** 2-5 combinable conditions.
**When NOT to use:** 6+ binary conditions (2⁶ = 64 rows → table explodes).
→ Split into smaller tables, or use rule engine / policy pattern in code.

**Build the table:**

```
| Condition A | Condition B | Condition C | → Outcome     |
|-------------|-------------|-------------|---------------|
| Yes         | Yes         | Yes         | → Action 1    |
| Yes         | Yes         | No          | → Action 2    |
| Yes         | No          | *           | → Action 3    |
| No          | *           | *           | → Default     |
```

**Every table must specify:**
- Default behavior (when no rule matches)
- Conflict resolution (when two rules match)

**Collapse technique:**
- Remove impossible combinations
- Merge rows with identical outcomes
- Use * for "don't care" conditions

**Validation:** "Is any combination missing? Are any two rules contradictory?"

---

### Tool 5 — Scenario Modeling

**When:** Verifying how real usage flows through the system.

**Recommended order:** First Behavior (Tool 3) → then Rules (Tool 4) →
then Scenarios (here). Each validates the previous.

**Three types:**

```
HAPPY PATH:      Everything goes as planned
ALTERNATE PATH:  Valid but non-standard route
EXCEPTION PATH:  Error, edge case, failure
```

**For each scenario:**

```
Scenario:       [name]
Trigger:        what starts it
Preconditions:  what must be true
Steps:          what happens, in order
Postconditions: system state after
User sees:      what the human experiences
System sees:    what's logged / stored / changed
```

**CRITICAL: Run scenarios PER RELEVANT DIMENSION.**
A Backend scenario is different from a Frontend scenario.
If the Kernel identified multiple platform dimensions,
run key scenarios for each one.

Example of a cross-dimension scenario most people miss:
"User's access token expires while they're writing a comment.
Frontend needs to silently refresh and retry. What does the user see?"
This scenario only emerges when you run scenarios from the Frontend dimension.

**Validation:** "Does every state from Tool 3 appear in at least one scenario?
Are there exception paths I haven't covered?"

---

### Tool 6 — Risk Pass

**When:** Finding what could go wrong before it does.

**Four lenses:**

```
INVERSION:       "How would I build the worst version of this?"
PRE-MORTEM:      "It's 6 months later and this failed. Why?"
THREAT MODELING: "Where would an attacker strike?"
ABUSE CASES:     "How would a bad actor exploit this?"
```

**Risk categories:**
Security · Data Integrity · UX Failure · Operational ·
Legal/Compliance · Abuse/Fraud · Performance/Scaling · Dependency/Vendor

**Output: Risk Register**

```
# │ Risk              │ Category  │ Severity │ Mitigation           │ Phase
──┼───────────────────┼───────────┼──────────┼──────────────────────┼──────
1 │ JWT secret leaked │ Security  │ Critical │ Secret rotation +    │ MVP
  │                   │           │          │ token blacklist      │
2 │ Webhook replayed  │ Security  │ High     │ Signature verify +   │ MVP
  │                   │           │          │ timestamp check      │
```

**This tool discovers risks. It does NOT redesign the system.**
If a risk reveals a new state, rule, or actor → flag it.
Kernel will schedule a revisit via Process Manager.

---

### Tool 7 — Second-Order Thinking

**When:** Making an important decision with lasting consequences.

Ask "And then what?" at least 2 layers deep:

```
Decision → 1st order → 2nd order → 3rd order
```

**Don't confuse with Tool 3 (Behavior):**
- "What happens if we delete an account?" → consequences (here)
- "From which states is deletion allowed?" → behavior (Tool 3)

---

### Tool 8 — Simplify Without Lying

**When:** After divergent thinking (Tools 2-7), before output.

**Remove:** Fake complexity, unrealistic scenarios, premature abstractions,
duplicated concepts, features nobody asked for.

**Keep:** Real risks, legal constraints, genuine edge cases,
domain distinctions that matter.

**Phase explicitly:**

```
MVP:  "If removed, system is broken or unsafe"
v1:   "Users complain but survive"
v2:   "Future speculation, not current demand"
```

**Mark removed items "Deferred" not "Deleted."**
Deferred = wisdom. Deleted = negligence.

**Correct Occam's Razor:** Not "always pick simplest."
But "when two options are equal in every other way, prefer simpler."
Simpler today may be technical debt tomorrow — evaluate honestly.

**Validation:** "Is there anything I deferred that could cause a
real problem in MVP? If unsure → keep it."

---

### Tool 9 — Convert to Action

**When:** Thinking is done. Time to make it executable.

```
Action:        what to do
Due:           when
Depends on:    what must happen first
Done when:     testable acceptance criteria
Linked risks:  from Tool 6
Linked states: from Tool 3
Phase:         MVP / v1 / v2
```

**Without this tool, brilliant analysis produces zero results.**

---

### Tool 10 — Record and Communicate

**When:** Output needs to be captured or shared.

**Structure (Pyramid Principle):**
1. Conclusion first (one sentence)
2. Main supporting branches (2-4)
3. Details and evidence

**Document type (Diátaxis as a lens, not a rigid template):**
Ask "What need does this serve?"
- Learning → Tutorial (step-by-step, guided)
- Doing a task → How-to (practical, problem-oriented)
- Looking up facts → Reference (dry, complete, structured like the code)
- Understanding why → Explanation (conceptual, discussion-oriented)

Don't mix types. Don't force all 4 for every feature.
Not every feature needs a tutorial.

**Architecture docs (only when documenting system architecture):**
C4 model: Context → Container → Component → Code.
If not writing architecture docs → skip.

---

## Tool Selection Guide

The Kernel uses this to decide which tools each dimension needs.
If a dimension spans multiple types, take the **union** of all applicable tools.

```
Dimension Type          │ Essential Tools         │ Notes
────────────────────────┼─────────────────────────┼──────────────────────
Core Logic              │ 1, 2, 3, 4, 5, 6, 7, 8 │ Full analysis
(backend, business)     │ 9                       │
                        │                         │
Data / Schema           │ 1, 2, 3, 4, 8, 9       │ Behavior = verify
(database, models)      │                         │ states map to fields
                        │                         │
Interface Contract      │ 1, 2, 4, 5, 8, 9       │ Scenarios matter
(API, protocols)        │                         │ for contract design
                        │                         │
User Experience         │ 1, 2, 5, 6, 7, 8, 9    │ Scenarios are king
(frontend, mobile)      │                         │ Run per platform!
                        │                         │
Security                │ 1, 3, 4, 6, 8, 9       │ Risk Pass is king
(auth, crypto, trust)   │                         │
                        │                         │
Infrastructure          │ 1, 2, 6, 8, 9          │ Risk = what breaks
(deploy, CI/CD, env)    │                         │ in production
                        │                         │
Standards / Style       │ 1, 2, 8, 9             │ Lightweight pass
(naming, patterns)      │                         │
                        │                         │
Content / Marketing     │ 1, 2, 5, 7, 8, 9, 10  │ Scenarios + Record
(SEO, copy, brand)      │                         │
```

**Golden Rule scope clarification:**
"Never start acting before you've separated problem, behavior, rules,
and risk" applies to **Deep** dimensions. Light dimensions may skip
behavior and risk if the Complexity Gate confirms low complexity.

---

## Depth Levels

### Deep — Full analysis

All selected tools run completely. Every state modeled.
Every scenario written. Risk pass thorough.

**Use for:** Core business logic, security, primary user flows.

### Medium — Focused analysis

Tools run on critical paths only. Key states modeled.
Main scenarios (happy + top 2 exceptions). Quick risk scan.

**Use for:** Database schema, API contract, secondary flows.

### Light — Sanity check

Problem Framing + Decompose + Simplify only.
No detailed modeling. Just ensure nothing critical is missed.

**Use for:** Code standards, peripheral features, v2 items.

---

## Phase Discipline

```
MVP — "If removed, system is broken or unsafe"
      All MVP dimensions must complete before v1 starts.

v1  — "Users complain but survive"
      Exception: pull v1 forward if it blocks an MVP dimension.

v2  — "Future speculation, not current demand"
      Only plan, don't build yet.
```

---

## Safety Mechanisms

### Max Iteration Limit

Maximum 3 full Zoom cycles. After that, deliver output with
caveats listing remaining uncertainties. Don't loop forever.

### Max MVP Dimensions

If more than 8 MVP dimensions identified, the problem is
probably too big. Break into 2+ separate problems first.

### Reframe Trigger

If during ANY Zoom In, you discover that:
- The original problem was defined wrong
- A critical actor was missing entirely
- The system boundary needs to change
- A fundamental constraint changed

→ STOP. Go back to Tool 1. Re-frame the problem. Restart.
This is expensive but less expensive than building the wrong thing.

---

## Complete Zoom Cycle Example

**Problem: "Build a user system for a blog"**

### Complexity Gate

```
Q1 (Nature): COMPLICATED — I know the type of answer (auth system
   with roles) but details require analysis.
Q2 (Dimensions): 5+ — Backend, Database, API, Frontend, Mobile,
   Security, SEO, Code Standards = 8 dimensions.
→ Full Zoom cycle with Dimension Map.
```

### Zoom Out #1

```
Dimensions + Priority + Depth + Phase:

├── Backend Logic     (MVP, Deep)    ← most dependencies, first
├── Database Schema   (MVP, Medium)  ← depends on Backend
├── API Contract      (MVP, Medium)  ← depends on Backend
├── Frontend UX       (MVP, Deep)    ← depends on API
├── Mobile UX         (v1, Medium)   ← depends on API
├── Security          (MVP, Deep)    ← bidirectional with Backend
├── SEO               (v1, Light)    ← depends on Frontend
└── Code Standards    (MVP, Light)   ← no dependencies

Dependency Matrix built. Assumption Registry initialized.
```

### System Sketch

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Auth     │────→│ Backend  │────→│ API      │
│ (JWT+    │     │ (content,│     │ (REST,   │
│  roles)  │     │  votes,  │     │  OpenAPI)│
└────┬─────┘     │  reviews)│     └────┬─────┘
     │           └────┬─────┘          │
     ↓                ↓           ┌────┴─────┐
┌──────────┐     ┌──────────┐    │ Frontend │
│ Database │     │ Security │    │ (Next.js │
│ (PG,     │     │ (tokens, │    │  SSR,SEO)│
│  states) │     │  limits) │    └──────────┘
└──────────┘     └──────────┘

Risk smells: Auth=commodity, Backend=commodity,
API=needs dual format (human+agent), Security=agent rate limits
```

### Stakeholder Checkpoint

```
"Here's my plan:
 - Problem has 8 dimensions, 6 MVP
 - Starting with Backend Logic (most dependencies)
 - Final deliverable: Architecture doc + task breakdown
 - Assuming standard blog, multi-author, production-grade
 - Proceed?"
→ (stakeholder confirms or redirects)
```

### Orient #1 (before first Zoom In)

```
MODEL UPDATE: First time — no prior understanding to update.
EVOLUTION CHECK:
  Backend Logic (auth + roles) → Good Practice (well-known patterns)
  BUT: AI Agent access control → Emerging (few standard solutions)
  → Split Backend into two: standard auth (Good Practice, Medium)
     + AI Agent access (Emerging, Deep)
MEMORY CHECK: (Memory not yet active)
BIAS CHECK: Am I defaulting to Backend first because I'm comfortable
  there? → No, Dependency Heuristic confirms it genuinely has most deps.

→ Start with Backend Logic (standard auth part first).
```

### Zoom In #1 — Backend Logic (Deep)

```
Tools selected: 1,2,3,4,5,6,7,8,9

Tool 1: Frame — actors, boundary, constraints, success metrics
Tool 2: Decompose — Registration, Auth, Authorization, Profile, Lifecycle
Tool 3: Behavior — Statechart with 3 orthogonal regions
        (account_state, session_state, role)
        Hierarchical: active contains {normal, password_reset_pending}
Tool 4: Rules — Authorization matrix, registration rules, login rules
Tool 5: Scenarios — 5 scenarios (happy + alternate + 3 exceptions)
Tool 6: Risk — JWT expiry, email enumeration, IDOR, brute force
Tool 7: Consequences — email as identifier, soft delete, grace period
Tool 8: Simplify — Social login → Deferred v2. MFA → Deferred v2.
Tool 9: Actions — 15+ tasks with acceptance criteria

Validation: impossible states identified ✓
            event coverage verified ✓
            all states appear in scenarios ✓
```

### Zoom Out #2

```
Process Manager reports:
  ✓ Backend Logic complete
  ○ Database Schema pending ← next (depends on Backend)
  ○ API Contract pending
  ○ Frontend UX pending
  ○ Mobile UX pending (v1, defer)
  ◐ Security partial (token storage needs Frontend input)
  ○ SEO pending (v1, defer)
  ○ Code Standards pending

Consistency check:
  Backend defined 5 roles → all downstream must know about them ✓
  Backend uses JWT → Frontend needs token lifecycle details → flagged

Reframe Trigger check: no fundamental changes → continue
```

### Orient #2 (before next Zoom In)

```
MODEL UPDATE: Backend taught me that account lifecycle is more
  complex than expected (3 orthogonal regions). This means Database
  Schema needs more careful state mapping than I initially thought.
  → Upgrade Database Schema from Medium to Deep? No — Medium is
     sufficient if I verify state mapping as part of Tool 3 in DB.
EVOLUTION CHECK: Database Schema → Commodity (standard Django models).
  → Use best practice patterns, don't overthink.
BIAS CHECK: Am I tempted to skip DB and jump to Frontend (more fun)?
  → Yes. Resist. DB depends on Backend and API depends on DB.

→ Next: Database Schema
```

### Zoom In #2 — Database Schema (Medium)

```
Tools: 1,2,3,4,8,9
Verify all Statechart states map to DB fields.
Define tables, constraints, indexes, cascade rules.
```

### Zoom Out #3

```
Cross-check: DB cascade on delete = SET NULL on posts.
Matches Backend Scenario 4 (GDPR deletion)? ✓
→ Next: API Contract
```

### ...cycle continues...

### Final Zoom Out

```
Process Manager final report:

All MVP dimensions: ✓ Complete
All v1 dimensions: ✓ Planned (not built)
Assumptions reviewed: 4 total, 2 validated, 2 accepted with risk
Cross-dimension consistency: all checks passed
Conflict Log: 0 unresolved
Deferred items: 7 items with rationale

→ Ready for implementation.
```

---

## Quick Reference Card

### The Zoom Cycle

```
CLASSIFY → ZOOM OUT → SKETCH → ORIENT → CHECKPOINT → ZOOM IN → ZOOM OUT → ORIENT → ZOOM IN → ... → DONE
(gate)     (see)      (map)    (update)  (confirm)    (solve)    (check)    (update)  (solve)         (verify)
                      ↑ first cycle only  ↑ first cycle only
```

### Kernel Questions

```
COMPLEXITY GATE:                    ZOOM OUT:
├── Nature? (Clear/Complicated/     ├── What dimensions exist?
│   Complex/Chaotic/Confusion)      ├── What's done, pending, blocked?
└── How many dimensions?            ├── Any cross-dimension conflicts?
                                    ├── Reframe needed?
SYSTEM SKETCH (first cycle):        ├── Max iterations reached?
├── What does the whole look like?  └── What's highest priority next?
├── How do dimensions connect?
├── Where are the risk smells?      ZOOM IN:
                                    ├── Scope of this dimension?
ORIENT:                             ├── Which tools needed?
├── Has my understanding changed?   ├── What depth?
├── Is this dimension novel or      ├── Execute tools
│   commodity? (Wardley)            └── Anything that changes
├── Have I seen this before?            other dimensions?
│   (Memory, when active)
├── Am I biased toward/against      STAKEHOLDER CHECK (first cycle):
│   something? (Bias Check)         ├── Here's my plan. Correct?
└── If Complex → run                ├── Right priorities?
    Experiment Protocol?            └── Missing anything?
```

### The 10 Tools

```
 1. Frame        — What am I solving? For whom? Limits? Assumptions?
 2. Decompose    — Break into independent parts, full coverage
 3. Behavior     — States, events, transitions (orthogonal + hierarchical)
 4. Rules        — Condition combinations → outcomes (2-5 conditions)
 5. Scenarios    — Happy, alternate, exception (per dimension!)
 6. Risk         — Inversion, pre-mortem, threats, abuse
 7. Consequences — And then what? 2+ layers deep
 8. Simplify     — Remove fake complexity. Phase: MVP/v1/v2
 9. Act          — Tasks with acceptance criteria
10. Record       — Conclusion first. Document type: tutorial/howto/ref/explanation
```

### Four Laws

```
GOLDEN RULE:
  Never start acting (Tool 9) before separating
  problem, behavior, rules, and risk (Tools 1-6).
  Applies to Deep dimensions. Light dimensions may skip
  behavior and risk after Complexity Gate confirms low complexity.

SEQUENCE RULE:
  First DIVERGE (Tools 2-7: see everything).
  Then CONVERGE (Tools 8-10: filter and build).
  If you converge too early, blind spots survive.

ZOOM RULE:
  Zoom Out before first Zoom In.
  Orient before every Zoom In.
  Zoom Out between every Zoom In.
  Never finish without a final Zoom Out.

EVOLUTION RULE:
  Don't reinvent what's commodity. Don't shortcut what's novel.
  Commodity = use best practice, save time for what matters.
  Novel = go deep, experiment, expect uncertainty.
```

### Universal ↔ Engineering Translation

```
Universal                        │ Engineering Tool            │ Source
─────────────────────────────────┼─────────────────────────────┼──────────────
"How does it change?"            │ Harel Statechart            │ Harel 1987
"What conditions → what result?" │ Decision Table              │ ISTQB
"Independent parts, full cover"  │ MECE Issue Tree             │ Minto/McKinsey
"Business boundaries inside"     │ Bounded Contexts            │ DDD / Eric Evans
"How would I make this fail?"    │ Inversion + Pre-Mortem      │ Munger/Kahneman
"And then what?"                 │ Second-Order Thinking        │ Howard Marks
"Remove fake complexity"         │ Simplify Without Lying       │ Occam (corrected)
"Conclusion first"               │ Pyramid + Diátaxis           │ Minto/Procida
"What type of problem?"          │ Cynefin Framework            │ Snowden 1999
"Update my understanding"        │ Orient (OODA Loop)           │ John Boyd
"Is this novel or commodity?"    │ Evolution Stage              │ Wardley Mapping
"I don't know until I test"      │ Experiment Protocol          │ Scientific Method
```

---

## Final Edition — All Fixes Applied

### From v2 (foundation):

```
Fix │ Issue                          │ Solution
────┼────────────────────────────────┼──────────────────────────────
1   │ Kernel/PM role overlap         │ PM = data provider, Kernel = decider
2   │ No Complexity Gate             │ Cynefin × dimensions matrix
3   │ No Priority Heuristic          │ Dependency > Uncertainty > Bottleneck
4   │ No Dependency Matrix           │ Template + usage rules
5   │ No Reframe Trigger             │ 4 conditions → restart if any true
6   │ Multi-type dimensions          │ Tool union for multi-type dims
7   │ No Max Iteration               │ 3 cycles max, then deliver with caveats
8   │ No Max MVP dimensions          │ 8+ → break into separate problems
9   │ Golden Rule scope unclear      │ Applies to Deep, not Light
```

### From v3 (new frameworks):

```
#  │ Addition                         │ Source
───┼──────────────────────────────────┼─────────────────────
10 │ Orient step in Zoom cycle        │ OODA Loop (John Boyd)
11 │ Evolution awareness              │ Wardley Mapping
12 │ Domain Decomposition             │ DDD (Eric Evans)
13 │ Experiment Protocol for Complex  │ Scientific Method
14 │ Bias Check in Orient             │ Cognitive Psychology
```

### Final Edition (from live testing):

```
#  │ Addition                         │ Why it was missing
───┼──────────────────────────────────┼──────────────────────────────
15 │ System Sketch (breadth-first)    │ Without it, 80% effort on 1 dim
16 │ Stakeholder Checkpoint           │ Without it, wrong priority path
17 │ Output Format (Q7 in Framing)   │ Without it, depth ≠ deliverable need
18 │ Mandatory Tool 10 rule          │ Without it, raw analysis not doc
```

---

## One Sentence

**Classify the problem, see the whole picture, sketch the system,
orient your understanding, confirm the plan, go deep on one part,
come back and check, repeat — using the right tools at the right
depth, with domain AND technical decomposition, and experiment
when the answer isn't knowable in advance.**

---

## Self-Learning Pipeline (Phase 15 — Implemented)

The Memory layer is now active. The pipeline is fully wired into hooks — no manual
invocation required. Every session automatically contributes to the learning DB.

```
PIPELINE FLOW (automated):

Write/Edit tool
  └─► PostToolUse: capture.py
        ├─ observations table  (file, tool, narrative, impact_score, concepts)
        └─ concept_graph table (co_edit edges between files edited in same session)

Session end (Stop hook: session-end.sh)
  ├─ session_summaries  (request from gate, completed from obs, learned from graph)
  ├─ agent_metrics      (domain, complexity, duration — auto-inferred)
  └─ concept_graph      (concept_link edges from concept co-occurrence in obs)
  └─ decay.py           (runs if last decay >7 days — prunes stale learned_patterns)

make task-done
  └─► record_outcome.py → task_outcomes
        └─ every 10 tasks: cos_learn_extract → learned_patterns + routing_weights
```

**Narrative generation** (`capture.py`): Each Write/Edit automatically generates a
rule-based narrative from the file path — free, instant, no API call:

- `backend/apps/commerce/models/order.py` → "Modified commerce order model (schema change)"
- `frontend/src/app/products/page.tsx` → "Modified frontend app component"

**Diagnostic tools:**

```bash
make thinking_os-health                                    # Full health report (DB, hooks, gates, pipeline)
python3 .claude/thinking_os/health_check.py --json        # JSON output for programmatic use
```

**Bootstrap tool** (one-time cold-start):

```bash
python3 .claude/thinking_os/bootstrap_outcomes.py          # populate from docs/tasks.md
python3 .claude/thinking_os/bootstrap_outcomes.py --dry-run # preview only
```

**10 SQLite tables** (`.claude/thinking_os/coding-os.db`):

| Table             | Populated by                  | When                          |
| ----------------- | ----------------------------- | ----------------------------- |
| observations      | capture.py (PostToolUse)      | Every Write/Edit              |
| concept_graph     | capture.py + session-end.sh   | Every Write/Edit + session end|
| session_summaries | session-end.sh                | Session end                   |
| agent_metrics     | session-end.sh                | Session end                   |
| task_outcomes     | make task-done                | Task completion               |
| learned_patterns  | cos_learn_extract            | Every 10 task_outcomes        |
| routing_weights   | cos_route_skill/model        | After learned_patterns updated|
| outcome_history   | decay.py                      | Periodic (>7 days)            |
| experiment_log    | manual / MCP tools            | Research experiments          |
| schema_version    | migrations                    | Schema upgrades               |

**MCP tools** (available in Orient Memory Check):

- `thinking_os_search` — similarity search across observations
- `cos_learn_suggest` — route task to best agent/model based on learned patterns
- `cos_learn_extract` — extract patterns from recent task_outcomes
- `cos_metric_record` — manual metric recording (auto-recorded at session end)
- `thinking_os_health` — live health status via MCP

---

## Future Roadmap

```
MULTI-AGENT SUPPORT:
  Shared Dimension Map across agents
  Merge protocol for parallel work on different dimensions
  Conflict resolution when two agents' outputs contradict

MEMORY ENRICHMENT (next):
  Claude API narrative enrichment via compress.py (batch job, not per-edit)
  Embedding search: sqlite-vec integration for semantic similarity
  Cross-session pattern linking: connect patterns across domains
```

---

## Intellectual Heritage

```
Framework / Source              │ What we took from it
────────────────────────────────┼──────────────────────────────────
Metacognition (Cambridge)       │ Layer 0 — thinking about thinking
Cynefin (Dave Snowden, 1999)    │ Complexity Gate — problem classification
OODA Loop (John Boyd, 1960s)    │ Orient step — mental model update
MECE (Barbara Minto, McKinsey)  │ Tool 2 — non-overlapping decomposition
Pyramid Principle (Minto)       │ Tool 10 — conclusion-first writing
Domain-Driven Design (Evans)    │ Tool 2 — domain decomposition
Harel Statecharts (Harel, 1987) │ Tool 3 — behavior with hierarchy/orthogonal
Decision Tables (ISTQB)         │ Tool 4 — combinatorial rules
Use-Case Modeling (IBM/UML)     │ Tool 5 — actor-goal scenarios
Inversion (Charlie Munger)      │ Tool 6 — reverse thinking
Pre-Mortem (Daniel Kahneman)    │ Tool 6 — failure imagination
Threat Modeling (Microsoft SDL) │ Tool 6 — security risk discovery
FMEA (ASQ)                      │ Tool 6 — failure mode analysis
Second-Order Thinking (Marks)   │ Tool 7 — consequence chains
Wardley Mapping (Wardley)       │ Orient + Priority — evolution awareness
Scientific Method               │ Experiment Protocol for Complex problems
Diátaxis (Procida)              │ Tool 10 — document type classification
C4 Model (Simon Brown)          │ Tool 10 — architecture documentation
```

---

*"The measure of intelligence is the ability to change."*
— Albert Einstein
