<!-- domain:DOCS | layer:reference | ssot:ref | updated:2026-04-19 -->
# Zero-to-Production Problem Decomposition Formulas

> This document contains 11 structured, spec-level formulas covering the full lifecycle of any software project:
> from research through analysis, architecture, documentation, implementation, testing, debugging, security, deployment, monitoring, and refactoring.
> Objective: **leave zero ambiguity, zero gaps, zero unexamined assumptions.**
>
> **Audience:** These formulas apply to both solo developers and teams. Steps that assume a team (e.g., mandatory code review, notifying support staff) can be replaced with self-review and checklists by a solo developer.

### Structural Guide

> Each formula uses one of three organizational patterns based on its nature:
>
> - **Step:** When tasks have sequential dependencies and must execute in order (e.g., analysis, coding, debugging)
> - **Layer:** When checks are independent and parallelizable — order does not matter (e.g., security audit)
> - **Section:** When two fundamentally different but complementary activities are grouped (e.g., testing and code review)
>
> All cross-references use **formula names**, never numbers — so reordering formulas will not break references.

---

## Formula 1: Research & Discovery

> **Objective:** Before starting any work, produce an explicit map of what you know, what you assume, and what you must learn — to eliminate wasted effort and uninformed decisions.

### Step 1 — Current Knowledge Map

- What do you concretely know about this problem domain? (List honestly)
- What do you assume to be true but have not verified? (Unvalidated assumptions)
- What are your explicit blind spots — things you know you do not know?
- For each unknown: Is it a blocker for starting, or can it be learned just-in-time?

### Step 2 — Existing Solutions Audit

- Has anyone solved this problem before? (Open-source projects, competing products, research papers)
- What can be learned from existing solutions? (Mistakes, architecture choices, trade-offs)
- Is there a justified reason not to use an existing solution directly? (If not, use it)
- What libraries, frameworks, or tools exist for this problem space?

### Step 3 — Technical Options Inventory

- What technologies are candidates for solving this problem?
- For each candidate, evaluate: maturity, community support, documentation quality, learning curve
- Does the team (or you) have operational experience with this technology? If not, what is the concrete time cost to acquire it?
- Does this technology scale to the target usage level?
- ⚠️ **This step produces an options inventory only — the final binding decision is made in the Architecture & System Design formula.**

### Step 4 — Exploratory Prototype (Spike)

- Before committing to a final decision, build a small, throwaway prototype
- The prototype's sole purpose: validate or invalidate technical assumptions — not build product
- Set a strict time-box (e.g., 2–4 hours) — if the time-box expires without a clear answer, the assumption is likely wrong
- Document the outcome explicitly: what worked, what failed, what was unexpected

---

## Formula 2: Problem Decomposition & Analysis

> **Objective:** Decompose any idea or problem from zero to the point where every sub-part is actionable, testable, and free of ambiguity.

### Step 1 — Problem Definition

- State the exact problem in one explicit, unambiguous sentence
- Who experiences this problem? (Target user / persona)
- What is the concrete cost of not solving it? (Prove the value)
- What is the explicit boundary of this problem? (What is in scope and what is deliberately excluded — state both)
- **Top-level success metrics:** How will you know the system actually solved the problem? (e.g., 80% of tasks completed on time, 30-day user retention above 40%). Without macro-level metrics, all feature tests can pass while the product fails to deliver user value
- 📦 **Required deliverable from this step:** One clear, ruthless problem statement + an explicit Scope / Out-of-Scope list + a list of measurable success metrics. If any of these are missing, this step is not complete.

### Step 2 — Actor Identification

- What roles interact with the system? (End user, admin, external service, cron job, etc.)
- What is each actor's explicit goal within the system?
- What constraints does each actor operate under? (Access level, technical literacy, language, device, etc.)

### Step 3 — Goal Tree (Capability-Based Decomposition)

- State the top-level goal
- Decompose into 3–7 sub-goals
- ⚠️ **Decompose by business capabilities, never by UI screens.** E.g., "Pet Management", "Caregiver Management", "Care Schedule", "Reminders" — not "Home Screen", "Profile Page". Screens change; business logic does not.
- Recursively decompose each sub-goal until you reach a leaf task that **one person can fully implement in 1–2 days**
- For each leaf node, state explicitly: input, output, and success condition

### Step 4 — Scenario Specification

- For each leaf node, produce a structured scenario:
  - **Trigger:** What initiates this scenario?
  - **Precondition:** What must be true before execution begins?
  - **Happy Path:** The nominal flow when everything works correctly
  - **Sad Paths:** Failure flows — network down, invalid input, external service unavailable, etc.
  - **Recovery Path:** When a failure occurs, how does the system restore itself to a healthy state? (e.g., local queue + sync after reconnection)
  - **Boundary Conditions:** Zero values, maximum values, duplicates, empty inputs, malformed formats
  - **Concurrency Conditions:** Two actors performing the same operation simultaneously
  - **Postcondition:** After successful completion, what is the explicit new state of the system?

### Step 5 — Decision Table

- For every component with conditional logic, produce an explicit decision table:
  - Column 1: Input conditions
  - Column 2: System state
  - Column 3: Expected output / behavior
- Each row in this table becomes a future test case

### Step 6 — Conceptual Data Model

- What entities exist in the system?
- What are each entity's attributes?
- What are the relationships between entities? (One-to-one, one-to-many, many-to-many)
- What happens when an entity is deleted? (Cascade, Restrict, Nullify)
- ⚠️ **The data model at this stage is conceptual (entities and relationships). Physical database design (tables, indexes, migrations) is handled in the Architecture & System Design formula.**

### Step 7 — State Machine

- For every entity that **changes state over time**, produce an explicit state machine
- List all possible states (e.g., for a Task: Draft → Scheduled → Due → Overdue → Completed / Skipped / Cancelled)
- For each state transition, specify:
  - What condition must be satisfied?
  - Which actor is authorized to trigger it?
  - What side effects does it produce? (e.g., send notification, update timeline, recalculate schedule)
  - What event does it emit?
- ⚠️ **If an entity has more than two states and no state machine has been defined for it, the analysis is still incomplete.** Without a state machine, time-dependent behavior degrades into unstructured if/else chains.

### Step 8 — Event Map

- List all events the system produces (e.g., `pet_created`, `task_completed`, `reminder_sent`, `reminder_failed`, `caregiver_invited`)
- What action triggers each event?
- What consumers does each event have?:
  - **Business logic:** (e.g., when `task_completed` fires, schedule the next occurrence)
  - **Analytics:** (e.g., what percentage of tasks are completed on time)
  - **Notifications:** (e.g., notify the owner that medication was administered)
- Do events require persistent storage? (Audit log)

### Step 9 — Permission Matrix

- For each actor and each action, state explicitly: allowed, conditional, or forbidden
- State special conditions explicitly:
  - If a subscription expires, what becomes read-only?
  - Temporary access (e.g., a temporary sitter) — until what date is it active?
  - Can an owner delete a pet while active tasks exist?
- ⚠️ **This matrix defines "who is allowed to do what" (an analytical decision). The technical enforcement (Token, RBAC, Middleware) is handled in the Security Audit formula.**

### Step 10 — Dependency Map

- Which components depend on each other?
- What is the required build order?
- Where can work proceed in parallel?
- Where must one component block on another?

### Step 11 — Unknowns Audit

- What do you still not know?
- For each unknown: Is it a blocker, or can progress continue with an explicit assumption?
- If proceeding with an assumption, state the assumption explicitly and flag it for later validation
- For each risk, define a concrete fallback plan

### Step 12 — Recursive Decomposition Checklist

- For every sub-component or node that is still too large, ask these 12 questions:
  1. What exact problem does this component solve?
  2. Who is the primary actor?
  3. What triggers it?
  4. What are the preconditions?
  5. What are the explicit inputs?
  6. What is the successful output or result?
  7. What state change does it produce?
  8. What are the governing rules?
  9. What are the edge cases?
  10. What happens on failure?
  11. How do you know it worked correctly? (Observable metric)
  12. What is the concrete test case?
- **If any of these 12 questions remains unanswered, the component must be decomposed further**
- **Stop condition:** A component is a leaf node when it has a clear owner, clear input and output, is implementable by one person, is testable, and its rules and edge cases are fully specified. If you are still saying "this needs to be handled better," it is not a leaf yet.

---

## Formula 3: Architecture & System Design

> **Objective:** Make final, binding technical structure decisions before writing code — based on options identified in the Research & Discovery formula and analysis completed in the Problem Decomposition formula. These decisions are extremely expensive to change later.
>
> 🔄 **Backtrack trigger:** If during architecture design you encounter a question that the Problem Decomposition formula does not answer (e.g., unknown actor, undefined capability, unforeseen state) → stop, return to the Problem Decomposition formula, and fill the gap there. Do not guess.

### Step 1 — Non-Functional Requirements Definition

- How many concurrent users must be supported? (10? 10,000? 1 million?)
- What is the acceptable maximum response time? (100ms? 2 seconds?)
- Must the system be available 24/7? What downtime is acceptable?
- What is the projected data volume at 1 year? At 5 years?
- Is multi-language or multi-timezone support required?

### Step 2 — Final Architecture Pattern & Technology Selection

- Based on the options inventoried in the Research & Discovery formula, make the binding decision:
- Monolith or microservices? (For initial builds, monolith is almost always the correct choice)
- If multiple services: Monorepo or polyrepo? Monorepo simplifies cross-service changes and shared tooling; polyrepo enforces service independence and separate deployment cycles. State the choice and justify it explicitly.
- Internal structure pattern: Hexagonal (Ports & Adapters), Clean Architecture, Onion, Layered, or Vertical Slices? For each, the core question is: **how is domain logic separated from infrastructure?** Choose the pattern that matches the team's experience and the project's complexity. Over-engineering the structure is as harmful as under-engineering it.
- Communication pattern: REST, GraphQL, gRPC, Event-Driven?
- Layer structure: How many layers? What responsibility per layer? (Controller → Service → Repository → DB)
- Final language and framework — with explicit justification
- For every choice, explicitly state **why** it was selected and **what was sacrificed** (trade-off)

### Step 3 — Physical Database Design

- Based on the conceptual data model from the Problem Decomposition formula, produce the physical design:
- SQL or NoSQL? Justify explicitly
- Core tables / collections with fields, types, and constraints
- Indexes: Which queries are heavy and require indexing?
- Migration strategy: What happens when the database schema changes?
- Backup and recovery: How often? Where stored? Has recovery been tested?

### Step 4 — API Design

- Explicit list of endpoints with precise input and output schemas
- Naming convention
- Error contract: What is the error response format? What status codes are used?
- API versioning: When the API changes, what happens to the previous version?
- Rate limiting and pagination strategy
- **Schema evolution strategy:** When a service adds, removes, or modifies a field in its request/response, how do consumers handle backward and forward compatibility? Define explicitly: Are new fields optional? Is there a deprecation period for removed fields? Do services use strict or lenient parsing? Without this, any schema change becomes a coordination nightmare across services.

### Step 5 — Infrastructure Decisions

- Where will it be hosted? (Cloud, VPS, Serverless)
- Environment structure: Development, Staging, Production
- Containerization: Is Docker used? Docker Compose for development? Where is the image registry?
- **Local development orchestration (for multi-service systems):** Can a developer run the entire system locally with a single command? (e.g., `docker-compose up` that starts all services, databases, and message queues together). Define explicitly: which services run in containers vs. natively, how service discovery works locally, and how to seed test data across services. If local setup takes more than 15 minutes or requires tribal knowledge, it is a productivity bottleneck that will compound over time.
- Supporting services: Cache (Redis)? Queue (RabbitMQ)? Search (Elasticsearch)?
- Where are files and media stored? (Object Storage, CDN)
- For each supporting service: Is it genuinely needed or is it premature optimization?

### Step 6 — Architecture Decision Records (ADR)

- Document every significant decision:
  - **Title:** What decision was made
  - **Context:** Why this decision was necessary
  - **Options:** What alternatives were evaluated
  - **Decision:** Which option was selected and why
  - **Consequences:** What trade-offs were accepted

---

## Formula 4: Technical Documentation

> **Objective:** Produce documentation that enables any developer to operate without asking additional questions.
> This formula is not executed only at project start — **documentation must be updated with every significant change.**
>
> 🔄 **Backtrack trigger:** If while writing documentation you cannot clearly explain a use case or the API contract does not seem logical → return to the Problem Decomposition or Architecture formula and correct the design. If you cannot document it, it is probably not yet properly designed.

### Step 1 — Documentation Inventory

- **README:** Project overview, installation instructions, folder structure
- **API docs:** Endpoint list, input/output schemas, examples (from Architecture & System Design formula)
- **Architecture docs (ADR):** Architecture decisions and their justifications (from Architecture & System Design formula)
- **Setup guide:** Prerequisites, environment variables, execution steps
- **Changelog:** Changes per version
- **Contributing guide:** Git workflow, code standards, PR submission process
- For each doc type, specify: Is it needed now or later? Who is the audience?

### Step 2 — Audience & Purpose per Document

- Who will read this document? (Developer, product manager, end user)
- After reading, what should the reader be able to concretely do?
- What is the reader's technical proficiency level?

### Step 3 — Mandatory Document Structure

- **Executive summary:** In 3 lines, state what this document covers and why it matters
- **Prerequisites:** What knowledge, tools, or access are required beforehand
- **Glossary:** Define every domain-specific term — do not assume the reader knows it
- **Body:** Explanation + concrete working example for every section
- **Limitations and exceptions:** What it does not do and why
- **FAQ:** Questions likely to arise during use

### Step 4 — Writing Rules

- Each sentence conveys exactly one concept
- Never use ambiguous pronouns (instead of "set it," write "set the `timeout` value")
- Provide a concrete, executable example for every claim
- Specify input and output formats explicitly (type, range, default value)
- Every step must be actionable — not descriptive

### Step 5 — Minimal Edit Rule

- ⚠️ **When editing an existing document, modify only the specific section that needs change — never rewrite the entire document**
- Every edit must be targeted and traceable: what changed, why, and confirmation that the rest of the document is untouched
- Before editing, read the current document in full — then modify only the targeted section
- Never rewrite sections that have been approved or have no issues — even if you think you can "improve" them
- If multiple sections need changes, edit each one separately — not all at once
- 🤖 **AI agent directive:** When using tools like `str_replace`, execute each change as a separate tool call. Never delete and recreate a file.

### Step 6 — Document Review

- Can someone with no prior context complete their task using only this document?
- Is every term defined?
- Is every example executable with its expected output stated?
- Are limitations explicitly stated?

---

## Formula 5: Implementation

> **Objective:** Transform analysis into clean, maintainable, unambiguous code.

### Step 1 — Pre-Implementation Verification

- What exact behavior must be implemented? (Reference scenarios from the Problem Decomposition formula)
- What are the explicit inputs? (Type, range, required vs. optional)
- What is the explicit output? (Type, structure, error states)
- What dependencies exist on other components?
- 🔄 **Backtrack trigger:** If any of the above questions lacks a clear answer → **do not write code.** Return to the Problem Decomposition formula (scenarios, decision table, state machine) or the Architecture formula (API contract) and record the answer there. Writing code against ambiguous assumptions guarantees technical debt.

### Step 2 — Pre-Code Design

- Naming: Every function, class, and variable name must be self-descriptive of its purpose
- Single responsibility: Each function performs exactly one task
- Error contract: How are errors handled? (Exception, Result Type, Error Code)
- Logging contract: What information is logged and at what level?

### Step 3 — Version Control & Git Workflow

- Branching strategy: Git Flow, Trunk-based, or GitHub Flow?
- Commit message convention: Explicit format (e.g., Conventional Commits: `feat:`, `fix:`, `refactor:`)
- Pull request size: Small and focused (preferably under 400 changed lines)
- Does every PR have a clear description? (What changed, why, how it was tested)
- Is `.gitignore` correct? Are sensitive files (env, secret, build artifacts) excluded from the repository?

### Step 4 — During Implementation

- Write tests first, then code (TDD) — or at minimum, write tests concurrently
- Every conditional block (if/else/switch) must cover all cases — the else/default branch is never empty
- Every external input (API, user input, file) must be validated
- Convert every implicit assumption into an explicit assertion or validation
- Comments explain **why**, never **what** — the code itself must communicate what it does
- **AI/LLM integration (when working with language models or AI services):**
  - Treat prompt templates as versioned code artifacts — store them in version control, not inline strings
  - Prompt engineering is iterative: write prompt → test with representative examples → evaluate output quality → refine → version. This cycle is separate from feature implementation and must be explicitly planned
  - Validate LLM responses structurally (correct schema) AND semantically (reasonable content). Never trust raw LLM output — always parse, validate, and constrain before using
  - Implement cost controls: token budget per request, caching for repeated queries, model size selection per query complexity
  - Handle high latency explicitly: LLM calls take 1–10 seconds. Implement streaming responses, loading states, timeouts, and fallback behavior when the service is slow or unavailable
- ⚠️ **Minimal edit rule:** When editing existing code, modify only the specific section that needs change. Never rewrite an entire file — tested, working sections must remain untouched. Every change must be the smallest possible diff.
- 🤖 **AI agent directive:** Use targeted edit tools (e.g., `str_replace`) instead of full file rewrites. Apply each change separately. Read the current file before editing. Verify the rest of the file is undamaged after editing.

### Step 5 — Post-Implementation Verification

- Are all happy and sad paths covered?
- Have boundary inputs been tested? (null, empty, max, negative, duplicate)
- Do errors produce clear, actionable messages?
- Is performance acceptable? (N+1 queries, memory leaks, infinite loops)

---

## Formula 6: Testing, Code Review & Performance

> **Objective:** Verify that code is correct, maintainable, performant, and meets standards.
> This formula executes **before every merge and every release** — not just once after implementation.

### Section A — Testing

> (Three test layers are independent; their order is simply fine-to-coarse granularity)

#### Layer 1: Unit Tests

- Does every public function have at least one test?
- Is the happy path tested?
- Are failure paths tested? (Invalid input, unavailable dependency)
- Are boundary values tested? (Zero, empty, maximum, negative)
- Has every row of the decision table (from the Problem Decomposition formula) become a test case?
- Every test must follow the **Given/When/Then** structure. Example: Given a pet exists and a caregiver has medication permission / When the caregiver logs medication at the scheduled time / Then a care log is stored, the task transitions to completed, and the owner receives a notification. **If you cannot write Given/When/Then, the expected behavior is still ambiguous.**

#### Layer 2: Integration Tests

- Do inter-module connections function correctly?
- Is database interaction correct? (Read, write, delete, update)
- Do external service integrations function correctly?
- How does the system behave when an external service is unavailable?
- **Contract tests (for multi-service systems):** Do the API contracts between services remain consistent? Use contract testing tools (e.g., Pact) to verify that the provider's actual response matches the consumer's expected schema — at build time, without running both services. Integration tests catch runtime failures; contract tests catch schema drift before deployment. If you have 2+ services that communicate, contract tests are not optional.

#### Layer 3: End-to-End Tests

- Do primary user scenarios work from start to finish?
- Does it function across different browsers / devices?
- Has it been tested with realistic (or production-like) data?

#### Layer 4: AI/LLM Output Testing (when using language models or AI services)

- **Structural validation:** Does the LLM response match the expected schema? (correct fields, correct types, within allowed value ranges)
- **Semantic validation:** Is the content reasonable and safe? Build a golden test set — a curated set of inputs with human-evaluated expected outputs — and run it against every prompt change
- **Hallucination detection:** Does the response contain fabricated facts or entities that do not exist in the input? Implement explicit checks for claims that cannot be grounded in the provided context
- **Safety and boundary testing:** Does the model refuse or flag inputs that are outside its scope? (e.g., "my cat is depressed" should recommend a vet, not provide therapy)
- **Non-determinism handling:** LLM outputs vary between calls. Tests must evaluate output quality ranges, not exact string matches. Use scoring rubrics (1–5 quality scale) rather than pass/fail for semantic tests
- **Cost regression testing:** Does a prompt change significantly increase token usage? Track tokens-per-request as a metric alongside correctness

> 🔄 **Backtrack trigger:** If during test writing you discover an edge case not present in the decision table or scenarios from the Problem Decomposition formula → first return and update the decision table / scenario / state machine, then write the test. A test without roots in analysis is a dangling test.

### Section B — Code Review

#### Readability Checklist

- Are names clear and free of ambiguous abbreviations?
- Are functions short and single-responsibility?
- Is the code flow followable without complex mental execution?
- Do comments explain "why," never "what"?

#### Correctness Checklist

- Are all conditional paths covered?
- Is error handling complete? (No unhandled exceptions?)
- Are race conditions eliminated?
- Are memory leaks eliminated?
- Are all user inputs validated?

#### Maintainability Checklist

- Is there no duplicated code? (DRY)
- Are dependencies injected, not hardcoded?
- Are configuration values separated from code? (Config / Env)
- Is logging sufficient and useful?

### Section C — Performance Review

#### Backend

- Have heavy queries been identified and optimized? (EXPLAIN ANALYZE)
- Is the N+1 query problem eliminated?
- Is the caching strategy explicit? (What is cached, retention duration, invalidation trigger)
- Is pagination implemented for large lists?
- Have heavy operations been moved to background jobs?

#### Frontend (if applicable)

- Is bundle size acceptable? (Code splitting, tree shaking)
- Are images optimized? (Appropriate format, lazy loading, srcset)
- Has render performance been verified? (Unnecessary re-renders)
- Are Core Web Vitals (LCP, FID, CLS) within acceptable ranges?

---

## Formula 7: Debugging

> **Objective:** Identify the exact root cause of a problem — never patch symptoms.

### Step 1 — Reproduce the Problem

- What is the exact current behavior? (Observed)
- What is the exact expected behavior? (Specified)
- What is the precise delta between the two?
- Can you reproduce the problem with explicit, repeatable steps?
- If not reproducible on demand, under what conditions does it occur? (High load, specific time, specific user, specific data)

### Step 2 — Isolate the Fault Location

- What is the last point where the system behaved correctly?
- What is the first point where the output is incorrect?
- What layers exist between these two points? (UI → API → Service → DB)
- By progressively removing layers, in which layer does the problem disappear?
- **Multi-service isolation (for microservice / multi-service systems):** When a request traverses multiple services (e.g., Mobile → API Gateway → Service A → Service B → DB), use the trace ID to follow the request across service boundaries. Check each service's logs independently. Test each service in isolation with the same input to determine which service produced the incorrect output. If you cannot reproduce the bug by calling a single service directly, the problem is likely in the integration layer (serialization, network, timeout, contract mismatch).

### Step 3 — Evidence Collection via Tooling

- **Logs:** What errors or warnings were recorded? Follow the Trace ID
- **Debugger:** Use breakpoints and step-through to inspect variable values
- **Network Tab / API Client:** Inspect HTTP request and response (Header, Body, Status Code)
- **Database:** Query the data directly — is what you expect actually stored?
- **Profiler:** If the issue is performance-related, run a profiler and identify the bottleneck
- **Git Blame / Git Bisect:** Identify the most recent change that touched the affected code

### Step 4 — Hypothesis Formation & Testing

- Based on collected evidence, formulate 3 explicit hypotheses for the root cause
- Rank each hypothesis by likelihood
- For each hypothesis, design a simple experiment that confirms or refutes it
- Change only one variable per experiment
- Record the result of every experiment

### Step 5 — Fix & Verify

- Identify the root cause — not just the symptom
- Write the fix — **modify only the component that is broken, nothing else**
- ⚠️ **Minimal edit rule:** The fix must be the smallest possible change that resolves the problem. Never "refactor while I'm here" — refactoring is separate from fixing.
- Verify that the original problem is resolved
- Verify that the fix has not introduced new problems (regression)
- Document: what the problem was, why it occurred, how it was resolved, how recurrence can be prevented
- 🤖 **AI agent directive:** When applying a bug fix, edit only the lines related to the bug. The rest of the file must remain byte-identical. Always read the file before editing and verify integrity after editing.
- 🔄 **Backtrack trigger:** If the root cause reveals a problem deeper than a simple bug (e.g., incomplete state machine, flawed architecture, or an entirely unanalyzed scenario) → apply a temporary fix, but log the root issue and reference it back to the appropriate formula (Problem Decomposition / Architecture / Technical Debt). A bug with an architectural root cause cannot be resolved with a code-only fix.

---

## Formula 8: Security Audit

> **Objective:** Identify and remediate vulnerabilities before they become production incidents.
> Security layers are independent and parallelizable — each layer can be audited separately.

### Layer 1 — Authentication & Authorization

- Does every endpoint verify that the user is authenticated?
- Does every endpoint verify that the user is authorized for the requested operation?
- Reference the Permission Matrix from the Problem Decomposition formula (Step 9) — verify that every access rule defined there is technically enforced here
- Do tokens / sessions have expiration times?
- After a password change, are previous sessions invalidated?
- Is brute-force login throttled? (Rate limiting)
- Is the password recovery flow secure? (Single-use token, short expiration)

### Layer 2 — Input Validation

- Are all inputs validated? (Form fields, URL parameters, headers, cookies, file uploads)
- Is SQL injection prevented? (Parameterized queries)
- Is XSS prevented? (Output encoding)
- Is CSRF prevented? (Token-based protection)
- Are file uploads validated? (Type, size, content — not just extension)
- Is path traversal impossible? (../../../etc/passwd)

### Layer 3 — Data Protection

- Are passwords hashed? (bcrypt / argon2 — not MD5 / SHA1)
- Is sensitive data excluded from logs? (Passwords, card numbers, tokens)
- Are communications encrypted? (HTTPS / TLS)
- Are API keys and secrets outside the codebase? (Stored in environment variables)
- Are backups encrypted?
- Is sensitive data retained only as long as necessary?

### Layer 4 — Infrastructure & Configuration

- Are unnecessary ports and services closed?
- Have default settings been changed? (Default passwords, debug mode)
- Are dependencies up to date with no known vulnerabilities?
- Are system errors hidden from users? (No stack traces, no DB errors in responses)
- Are security headers configured? (CORS, CSP, HSTS, X-Frame-Options)

### Layer 5 — Security Readiness

- Are security-relevant logs (failed logins, privilege changes, suspicious activity) captured separately?
- Does an Incident Response Plan exist and has it been practiced?
- Is there a concrete procedure for data breach notification?
- Are vulnerabilities scanned periodically? (Dependency audit, penetration testing)
- ⚠️ **General system monitoring (metrics, alerts, dashboards) is covered in the Monitoring & Observability formula.**

---

## Formula 9: Deployment & DevOps

> **Objective:** Move code from development to production in a repeatable, secure, and rollback-capable manner.

### Step 1 — CI/CD Pipeline

- Is every push to the repository automatically tested?
- What are the pipeline stages? (Lint → Test → Build → Deploy)
- What happens when a stage fails? (Block? Notify?)
- Is deployment automatic or does it require manual approval?

### Step 2 — Containerization & Environment Management

- Is the Dockerfile optimized? (Multi-stage build, minimal image size, layer caching)
- Does a Docker Compose configuration exist for local development?
- Is the image registry defined and access-controlled?
- How many environments exist? (Development, Staging, Production — minimum)
- How closely does Staging mirror Production? (The closer, the better)
- How are environment variables managed?
- Is each environment's database isolated? Where does test data originate?

### Step 3 — Deployment Strategy

- What is the deployment method? (Rolling, Blue-Green, Canary)
- Is automated rollback possible? How?
- Can you revert to the previous version in under 5 minutes?
- Are database migrations reversible?

### Step 4 — External Dependency Management

- If an external service (payment gateway, email provider, CDN) is down, what does the system do?
- Are timeout and retry policies configured for external calls?
- Is a circuit breaker implemented?
- Do fallbacks exist for critical services?

### Step 5 — Pre-Release Checklist

- Have all tests passed?
- Has the database migration been tested?
- Have new environment variables been added to Production?
- Has documentation been updated? (API docs, changelog, README)
- Is the rollback plan defined?
- Has the support team been notified of the changes?
- **AI/LLM deployment checks (when using language models):** Have prompt templates been versioned and tagged with this release? Has the golden test set been re-run against updated prompts? Is the token cost impact of prompt changes measured? Can you rollback to the previous prompt version independently of code rollback?

---

## Formula 10: Monitoring & Observability

> **Objective:** Detect problems before users do — the system must tell you when it is degrading.
> This formula covers **general system monitoring**. Security-specific monitoring is in the Security Audit formula.

### Step 1 — Golden Signals

- **Traffic:** What is the request rate per second / minute? What is the normal pattern?
- **Errors:** What is the error rate? (Percentage of 5xx responses, percentage of failed requests)
- **Latency:** What is the response time at P50, P95, P99?
- **Saturation:** What percentage of CPU, memory, disk, and connection pool is consumed?
- For each metric, define explicitly: what is the normal value? What value signals danger?

### Step 2 — Structured Logging & Distributed Tracing

- Do logs follow a consistent format? (JSON with fixed fields: timestamp, level, service, message, trace_id)
- Does every request carry a trace ID that is preserved across all layers?
- Are log levels well-defined? (DEBUG for development, INFO for normal events, WARN for suspicious activity, ERROR for failures)
- Where are logs stored and for how long?
- Is sensitive information masked in logs?
- **Distributed tracing (for multi-service systems):** Is an observability framework (e.g., OpenTelemetry) configured to propagate trace context across service boundaries? Can you visualize a single user request as it flows through all services (e.g., Mobile → API → Service A → Service B → DB) in one trace view? Without distributed tracing, debugging cross-service issues requires manually correlating logs across multiple systems — which is slow, error-prone, and often impossible under production pressure.

### Step 3 — Alerting System

- Is an alert threshold defined for every critical metric?
- Who receives alerts and through what channel? (SMS, Slack, Email, PagerDuty)
- Are alerts prioritized? (Critical = wake someone up at 3am, Warning = review in the morning)
- Are current alerts genuinely actionable or have they created alert fatigue?
- Does a runbook exist for every alert? (When this alert fires, what exactly should be done?)

### Step 4 — Dashboards & Observability

- Does a dashboard exist that shows overall system health in one view?
- Can you quickly identify where the problem is? (Drill-down from general to specific)
- Does a health check endpoint exist for monitoring tools?
- Are uptime and SLA being tracked?

### Step 5 — Proactive Prevention

- Has load testing been performed? What is the system's breaking point?
- Has chaos testing been performed? (e.g., What happens if a server dies?)
- Are data growth and traffic trends being monitored? (Before the disk fills up or the database slows down)
- Are dependencies periodically audited? (New vulnerabilities)

---

## Formula 11: Refactoring & Technical Debt Management

> **Objective:** Keep code and architecture clean over time — prevent gradual project decay.

### Step 1 — Technical Debt Identification

- Which parts of the codebase make you think "this needs to be fixed"? (Log them)
- Which components produce the most bugs? (Hotspots = decay points)
- Which components does nobody dare to touch? (Fear = debt signal)
- Which components break other areas every time they are modified? (Excessive coupling)
- Which technologies have become obsolete and are no longer supported?

### Step 2 — Prioritization

- Score each technical debt item on three dimensions:
  - **Pain:** How much does it slow down development? (1–5)
  - **Risk:** If left unfixed, how likely is a serious failure? (1–5)
  - **Fix cost:** How much time and effort does the fix require? (1–5)
- Fix items with high pain and high risk but low fix cost first

### Step 3 — Refactoring Strategy

- Never execute a large refactor all at once — always incremental
- Scout rule: Every time you touch a file, leave it slightly cleaner than you found it
- Before refactoring, ensure adequate test coverage exists (if not, write tests first)
- Never mix refactoring and behavior changes in the same commit
- After every refactoring step, all tests must pass
- ⚠️ **Minimal edit rule:** Each refactoring step must be a small, independent change. If 10 locations need modification, execute 10 separate edits — not one full rewrite. After each edit, verify nothing is broken.
- 🤖 **AI agent directive:** Never delete and recreate a file under the guise of refactoring. Use targeted edit tools (e.g., `str_replace`). Apply and test each change separately. If changes are numerous, decompose them into smaller steps.

### Step 4 — Preventing New Debt

- Are coding standards documented and enforced?
- Is code review mandatory?
- Are automated linters and formatters active?
- When technical debt is deliberately introduced (e.g., for speed), is it explicitly documented?
- Is dedicated time allocated for technical debt reduction in every sprint / cycle?

---

## Golden Rule Across All Formulas

> **No implicit assumptions.**
>
> Everything that seems "obvious" or "self-evident" — state it explicitly.
> Everything that you will "handle later" — document it now.
> Everything that "probably won't be a problem" — test it.

### Anti-Ambiguity Criteria

Every requirement, feature, or decision must satisfy these 7 criteria — if any is missing, it is still ambiguous:

1. **Observable:** Can its behavior be seen?
2. **Measurable:** Can a number be assigned to it?
3. **Testable:** Can a Given/When/Then be written for it?
4. **Scoped:** Is its boundary defined and finite?
5. **Owned:** Is its responsible party identified?
6. **Reversible or Justified:** Can it be undone, or is there a strong justification for its irreversibility?
7. **Connected to User Value:** Does it directly solve a user's pain?

⚠️ **If any of these has no answer → it is not a requirement. It is an illusion.**

---

## Navigation Protocol

> **Objective:** These formulas are written linearly but execution is non-linear. During execution of any formula, you may need to zoom in (dive deeper), zoom out (pull back to the big picture), backtrack (return to a previous formula), or discover something new. This protocol specifies **when** and **how** to perform these maneuvers.

### 1 — Zoom In Triggers

- During any step, if a sub-component is too large or complex to address within the current step → **stop and analyze that sub-component separately**
- Signals: Phrases like "this part is complex, I'll handle it later" or "this should be handled somehow" — both indicate an unperformed zoom-in
- **Action:** Execute the 12-question recursive checklist (Step 12 of the Problem Decomposition formula) on the sub-component

### 2 — Zoom Out Triggers

- If more than 2–3 days have been spent on sub-components without checking alignment with the top-level goal → **stop and ask: am I still aligned with the macro objective?**
- If you are building a feature and cannot state in one sentence which user pain it solves → zoom out is required
- If the system scope is growing beyond what was originally defined → execute the Traceability Check
- **Action:** Return to Problem Decomposition Step 1 (Problem Definition) and re-read the system boundary. Is it still valid?

### 3 — Backtrack Triggers

- During execution of any formula, if you encounter a **question that the previous formula does not answer** → do not guess. Return to that formula and record the answer there
- Concrete backtrack signals:
  - During **architecture**: You discover a missing actor or capability in the analysis → return to the Problem Decomposition formula
  - During **implementation**: You encounter a question that neither analysis nor architecture answers → return to the relevant formula
  - During **testing**: You discover an edge case that changes the decision table → first update the decision table, then write the test
  - During **debugging**: You discover the root cause is architectural → document it and reference it to the Architecture and Technical Debt formulas
- ⚠️ **Never guess the answer and continue.** Guessing = hidden technical debt.

### 4 — Discovery Protocol

- During execution of any formula, you may discover something new: a new actor, a new state, a new dependency, a new constraint, a new risk
- When something new is discovered, execute these three steps:
  1. **Record it:** Write it down immediately — even if you cannot investigate it right now
  2. **Assess impact:** Does this discovery affect previous formulas? (e.g., Does the data model change? Is a new state machine needed? Does the system boundary shift?)
  3. **Decide:** Should you backtrack now and correct (if impact is large), or record it for later (if impact is small and does not block progress)?
- ⚠️ **Never ignore a new discovery.** Ignoring = hidden gap.

### 5 — Anti-Paralysis Guard

- If you have backtracked 3+ consecutive times without making forward progress → **you are likely over-analyzing**
- If more than half your time is spent re-analyzing rather than implementing → zoom out and ask: Am I confusing analytical obsession with systematic analysis?
- **Operational rule:** If you can proceed with 80% confidence, proceed. State your assumption explicitly and validate it later. Vague perfectionism = paralysis. Operational completeness = systematic approach + testability.

---

## Traceability Check

> **Objective:** Verify that everything connects top-to-bottom — nothing is redundant, nothing is missing.

- For each feature, ask: Which **user pain** does it solve? (If no answer → likely redundant)
- For each identified pain, ask: Which **feature** solves it? (If no answer → it is a gap)
- For each endpoint, ask: Which **use case** does it serve?
- For each event, ask: Which **business action** produces it?
- For each test, ask: Which **rule** or **edge case** does it validate?
- For each metric, ask: Which **objective** does it measure?
- ⚠️ **If something exists at the top with no implementation below → gap. If something exists at the bottom with no connection above → likely redundant and should be removed.**

---

## Formula Usage Map

### Intensity Levels

> Not every project needs every formula at full depth. Select the intensity level that matches your context:

**Light (Hackathon / Prototype / Student Portfolio — hours to days):**
- Execute Formula 2 Steps 1–5 only (Problem → Actors → Goals → Scenarios → Decision Table)
- Skip Formulas 8, 10, 11 entirely
- Formula 5: Write self-documenting code (clear names, small functions); comments by exception only (Rule 12 — WHY, never what), skip the separate doc artifacts at this intensity
- Formula 9: Deploy to simplest possible platform (Vercel, Railway, etc.)

**Standard (Most projects — weeks to months):**
- Execute all 11 formulas as documented
- This is the default mode described throughout this document

**Full (Critical systems — finance, healthcare, infrastructure):**
- Execute all 11 formulas with maximum depth
- Add formal threat modeling to Formula 8
- Add disaster recovery drills to Formula 10
- Add compliance and regulatory checks as a cross-cutting concern
- Every decision requires explicit ADR documentation

---

### Core Paths

```
New project (once):
  Formula 1 (Research) → Formula 2 (Analysis) → Formula 3 (Architecture) → Formula 4 (Documentation)

Development loop (repeat per feature / task):
  Formula 5 (Implementation) → Formula 6 (Testing, Review & Performance) → Formula 4 (Documentation update)

Before every merge:
  Formula 6 (Testing & Review)

Before every release:
  Formula 8 (Security) → Formula 9 (Deployment)

When a bug is found:
  Formula 7 (Debugging) → Formula 6 (Regression testing) → Formula 4 (Bug documentation)

Post-release (continuous):
  Formula 10 (Monitoring & Observability)

Periodic (every sprint / cycle):
  Formula 11 (Refactoring & Technical Debt)
  Formula 8 (Periodic security review)
  Formula 3 (Periodic architecture review)
  Traceability Check — verify all connections top-to-bottom

Always active (during execution of any formula):
  Navigation Protocol — Zoom In/Out, Backtrack, Discovery
  Anti-Ambiguity Criteria — final filter for every decision and requirement

Recursive:
  Any component that is too large → restart from Formula 1 for that component
```

---

### Existing Project Takeover Path

> When joining or inheriting an existing codebase — not starting from scratch:

```
1. Understand (reverse-engineer the current state):
   Formula 2 Steps 1–12 in reverse — derive the implicit problem definition,
   actor map, data model, state machines, and permission matrix from existing code

2. Stabilize (add safety nets before changing anything):
   Formula 6 — write tests for existing critical paths (characterization tests)
   Formula 4 — document what you discovered

3. Then enter the standard development loop:
   Formula 5 → Formula 6 → Formula 4

4. Gradually improve:
   Formula 11 — identify and prioritize technical debt
   Formula 3 — evaluate whether architecture changes are needed
```

---

### Situational Paths

**Incident Response (production is on fire — different from debugging):**
```
1. Mitigate immediately — restore service (rollback, feature flag, scale up)
2. Communicate — notify stakeholders with current status
3. Then debug — Formula 7 (Debugging) to find root cause
4. Fix and verify — Formula 6 (Regression testing)
5. Post-mortem — document what happened, why, how to prevent recurrence
6. Systemic fix — update Formula 10 (Monitoring) to catch this earlier next time
```

**New Team Member Onboarding:**
```
1. Read existing documentation — Formula 4 outputs
2. Understand architecture — Formula 3 ADRs
3. Start with small, well-scoped tasks — Formula 5 (Implementation) on leaf nodes
4. Graduate to Formula 6 (Code Review) as reviewer
5. Eventually participate in Formula 2 (Analysis) and Formula 3 (Architecture)
```

**Scope Change (client or stakeholder changes requirements mid-project):**
```
1. Return to Formula 2 Step 1 — re-evaluate problem definition and scope boundary
2. Run Traceability Check — what is affected by this change?
3. Update Formula 2 (affected scenarios, decision tables, state machines)
4. Update Formula 3 (if architecture is affected)
5. Update Formula 4 (documentation)
6. Re-enter development loop with updated specs
```

**External Service Integration (adding Stripe, Twilio, etc.):**
```
1. Mini Formula 1 — research the service's API, SDKs, limitations, pricing
2. Mini Formula 2 — define scenarios specific to this integration (happy path, failure, retry)
3. Update Formula 3 — API contract, error handling, circuit breaker strategy
4. Formula 5 → Formula 6 — implement and test
5. Update Formula 8 — security implications of the new dependency
```

**Design Review (before team starts implementation):**
```
1. After Formula 3 (Architecture) and Formula 4 (Documentation)
2. Before Formula 5 (Implementation)
3. Review: Does the design satisfy all scenarios from Formula 2?
4. Review: Are trade-offs explicitly documented in ADRs?
5. Approval gate — implementation begins only after design is approved
```

---

### Role-Based Entry Points

> Not everyone executes every formula. Here is which formulas each role primarily owns:

| Role | Primary Formulas | Secondary / Review |
|------|-----------------|-------------------|
| **Junior Developer** | F5, F6 (tests) | F4 (update docs), F7 (debug own code) |
| **Senior Backend Dev** | F3, F5, F6, F7 | F2 (contribute to analysis), F8 |
| **Frontend Developer** | F5, F6 | F4, F7 |
| **Mobile Developer** | F5, F6, F9 (app store) | F7, F8 |
| **Tech Lead / Architect** | F1, F2, F3, F4 | F6 (review), F8, Design Review |
| **DevOps Engineer** | F9, F10 | F3 (infra decisions), F8 (infra security) |
| **QA Engineer** | F2 (scenarios), F6 (all testing) | F7 (reproduce bugs), F4 (test docs) |
| **Freelancer** | All (solo) | Scope Change path frequently |
| **Startup CTO** | F1, F2, F3, F8, F9, F10 | All (oversight) |
| **OSS Maintainer** | F6 (PR review), F9 (releases), F11 | F4 (contributing guide) |
| **Student** | F1 (Light), F2 (Light), F5, F6 | F4 (README only) |
| **Legacy Maintainer** | F7, F11, F6 | Takeover Path, F2 (reverse) |

---

### Team Parallelization Guide

> When multiple team members work simultaneously:

- **Formula 2 (Analysis)** can be split by capability — each person analyzes one capability area
- **Formula 5 (Implementation)** can be parallelized after Formula 2 Step 10 (Dependency Map) defines independent components
- **Formula 6 (Review)** — the author and reviewer must be different people
- **Formula 4 (Documentation)** and **Formula 5 (Implementation)** can run in parallel if API contracts are defined first
- ⚠️ **Formula 3 (Architecture) should NOT be parallelized** — architectural decisions require a single coherent vision. One person decides, team reviews.

---

### Domain-Specific Extensions

> Some domains have lifecycle patterns that differ significantly from standard web/backend development. The core formulas still apply, but additional domain-specific steps are needed:

- **AI/ML:** ✅ Core AI/LLM integration is now covered in the base formulas (F5 Step 4, F6 Layer 4, F9 Step 5). Remaining extensions for advanced use: fine-tuning lifecycle (dataset curation, training, evaluation), ML model training pipelines, data drift detection, A/B testing frameworks for model variants
- **Mobile:** Add App Store Submission, Code Signing, Beta Testing (TestFlight), Offline-First Architecture, Backward Compatibility with older app versions
- **Game Development:** Add Game Design Document, Asset Pipeline, Playtesting, Platform Certification
- **Embedded / IoT:** Add Hardware Interface, Firmware Update Strategy, Power Management, Safety Certification

⚠️ **Mobile, Game, and Embedded extensions are out of scope for this document but are flagged here so you know when the base formulas are insufficient for your domain.**

---

## Persona Simulations & Scenario Testing

> This section validates the formulas against concrete personas and real-world scenarios.

### Scoring Rubric

> Every persona is scored on 5 criteria (0–2 each, total = 10):

| Criteria | 0 | 1 | 2 |
|----------|---|---|---|
| **Path Coverage** | No path exists for this persona | Path exists but incomplete or requires guessing | Complete, explicit path |
| **Formula Coverage** | Critical steps are absent | Most steps exist but some role-specific ones are missing | All steps needed for this role are covered |
| **Scenario Realism** | Primary scenario cannot be executed | Primary scenario works but common secondary scenarios do not | Primary and common secondary scenarios are all executable |
| **Failure Handling** | No failure guidance | General failures covered but role-specific failures are not | General and role-specific failures are both covered |
| **Self-Sufficiency** | Must rely mostly on external knowledge | Document helps but some areas require external research | Document alone is sufficient for this role |

---

### Project-Specific Personas: Pet Care App (React Native + Go Hexagonal + FastAPI LLM)

---

#### Persona A — React Native Mobile Developer (Pet Care App)

**Context:** Builds the mobile UI for pet profiles, medication reminders, caregiver sharing, and push notifications. Works with offline-capable medication logging.

**Scenario:** Implementing the medication reminder screen with offline support — user logs medication while underground (no network), app queues locally and syncs when connection returns.

**Formula path:** F1 (research RN offline storage) → F2 (scenarios for offline medication logging, including conflict resolution) → F5 (implement RN components) → F6 (test on both iOS and Android) → F9 (App Store / Play Store submission).

**Where formulas work well:** F2 scenario specification directly applies to the offline sync flow. State Machine maps to medication task states. Permission Matrix captures caregiver access levels.

**Remaining gaps (domain-specific — require Mobile extension):**
- F9 is server-focused — App Store submission, code signing, TestFlight are absent
- Offline-first sync patterns (conflict resolution, queue-and-retry) are not in any formula
- Push notification setup (FCM / APNs) is not in any formula

**Score: 6/10** — Path=1, Formula=1, Scenario=2, Failure=1, Self=1

---

#### Persona B — Go Backend Developer (Hexagonal Architecture with Go Fiber)

**Context:** Builds the domain logic in hexagonal / ports-and-adapters architecture. Go Fiber handles HTTP layer. PostgreSQL adapter for persistence.

**Scenario:** Building the caregiver permission system — Owner invites Caregiver, Caregiver accepts, gets scoped access to specific pets and actions.

**Formula path:** F2 (Permission Matrix + State Machine for invitation) → F3 (hexagonal port interfaces, Go Fiber middleware) → F5 (domain layer + adapters) → F6 (table-driven tests for permission combinations).

**Where formulas work well:** Permission Matrix asks the right questions. State Machine captures invitation lifecycle. Decision Table covers complex permission combinations. F3 Step 2 covers architecture pattern selection (Hexagonal, Clean, Onion).

**Remaining gaps (minor, language-specific):**
- Go-specific testing patterns (table-driven tests, race detector) — F6 is language-agnostic by design
- Mobile-specific API patterns (pagination for slow connections) not in F3

**Score: 9/10** — Path=2, Formula=2, Scenario=2, Failure=2, Self=1

---

#### Persona C — FastAPI LLM Microservice Developer

**Context:** Builds AI-powered features using FastAPI (Python). Receives pet symptom descriptions, returns structured analysis with urgency levels via external LLM.

**Scenario:** Building the "Symptom Checker" — user describes symptoms, LLM analyzes and returns structured response with urgency level, possible causes, and recommended actions.

**Formula path:** F1 (research LLM options) → F2 (scenarios including hallucination, token limit) → F3 (FastAPI service design, prompt architecture) → F5 (implement with AI/LLM integration guidance) → F6 (Layer 4 AI/LLM output testing) → F8 (prompt injection prevention) → F9 (prompt versioning in pre-release checklist).

**Where formulas work well:** F5 Step 4 AI/LLM section covers prompt lifecycle, cost controls, latency, and response validation. F6 Layer 4 covers hallucination detection, semantic validation, golden test sets, non-determinism, and cost regression. F9 includes prompt versioning.

**Remaining gaps (minor):**
- A/B testing for prompt variants not explicitly covered
- Fine-tuning lifecycle is beyond scope

**Score: 9/10** — Path=2, Formula=2, Scenario=2, Failure=2, Self=1

---

#### Persona D — Cross-Service Integration Developer (Go ↔ FastAPI)

**Context:** Responsible for integration between Go Fiber backend and FastAPI LLM microservice.

**Scenario:** Implementing integration with handling for slow responses, errors, and unexpected formats.

**Formula path:** F2 (cross-service scenarios) → F3 (API contract, schema evolution, circuit breaker) → F5 (HTTP client, response parsing) → F6 (contract testing Layer 2, integration testing) → F7 (multi-service fault isolation Step 2) → F10 (distributed tracing Step 2).

**Where formulas work well:** All critical integration concerns are covered. Schema evolution handles compatibility. Contract testing catches schema drift. Multi-service isolation pinpoints fault origin. Distributed tracing provides end-to-end visibility.

**Score: 10/10** — Path=2, Formula=2, Scenario=2, Failure=2, Self=2

---

#### Persona E — Solo Full-Stack Pet Care Developer (All Hats)

**Context:** Single developer building entire stack: React Native + Go Fiber + FastAPI LLM.

**Scenario:** Building MVP end-to-end — pet registration, medication scheduling, and basic symptom checker.

**Formula path:** F1 (research all stacks) → F2 (full analysis) → F3 (architecture + monorepo + local orchestration) → F4 (API contracts) → F5 (implement) → F6 (test + contract tests) → F9 (deploy all services + mobile app).

**Where formulas work well:** Full chain applies. Monorepo decision structures the repo. Local orchestration ensures single-command startup. Dependency Map determines build order. Navigation Protocol handles context-switching.

**Remaining gaps (minor):**
- Context switching cognitive load between three languages/frameworks not addressed

**Score: 9/10** — Path=2, Formula=2, Scenario=2, Failure=2, Self=1

---

#### Persona F — QA Engineer for Multi-Stack Pet Care App

**Context:** Responsible for quality across the entire pet care app: mobile, Go API, FastAPI LLM, and integrations.

**Scenario:** Testing medication reminder flow end-to-end, including offline and concurrency scenarios.

**Formula path:** F2 (scenarios and decision tables as test source) → F6 (unit + contract + E2E + Layer 4 AI/LLM testing) → F7 (multi-service fault isolation).

**Where formulas work well:** Given/When/Then maps to test cases. Decision Table provides coverage. Multi-service isolation determines fault origin. Layer 4 covers LLM quality testing.

**Remaining gaps (domain-specific — require Mobile extension):**
- Mobile device testing: device farms, screenshot comparison, OS version matrix
- Cross-service test data management

**Score: 8/10** — Path=2, Formula=2, Scenario=1, Failure=2, Self=1

---

### General Personas

---

#### Persona G — Solo Indie SaaS Builder

**Context:** Building a SaaS product from scratch, solo, handling everything.

**Formula path:** Full chain: F1→F2→F3→F4 → loop F5→F6→F4 → F8→F9 → F10.

**Where formulas work well:** Complete lifecycle covered. Intensity levels scope effort. Architecture patterns and local orchestration help.

**Remaining gaps:**
- No architecture re-evaluation path for post-launch pivots
- No product validation or user feedback loop — formulas are purely technical

**Score: 8/10** — Path=2, Formula=2, Scenario=1, Failure=2, Self=1

---

#### Persona I — Tech Lead / Software Architect

**Context:** System design, architecture decisions, design review, mentoring.

**Formula path:** Project start (F1→F2→F3→F4) + Design Review situational path.

**Where formulas work well:** F3 covers architecture patterns, schema evolution, local orchestration. Design Review provides quality gate. Periodic architecture review in periodic section. ADR captures decision rationale.

**Remaining gaps (minor):**
- No framework for evaluating architecture evolution vs. replacement — F11 covers code-level debt, not architecture-level

**Score: 9/10** — Path=2, Formula=2, Scenario=2, Failure=2, Self=1

---

#### Persona J — DevOps Engineer

**Context:** CI/CD, infrastructure, monitoring, scaling.

**Formula path:** F9 (Deployment) + F10 (Monitoring) + F3 (infrastructure decisions).

**Where formulas work well:** F9 and F10 provide solid checklists. Incident Response covers production fires. Distributed tracing and local orchestration covered.

**Remaining gaps (domain-specific):**
- Infrastructure as Code (Terraform, Pulumi) not mentioned
- Cost optimization for cloud infrastructure absent
- Disaster recovery planning needs more depth

**Score: 7/10** — Path=2, Formula=1, Scenario=1, Failure=2, Self=1
