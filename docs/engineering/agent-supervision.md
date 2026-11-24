<!-- domain:ADAPTERS | layer:engineering | ssot:true | updated:2026-08-07 -->
# Agent Supervision

Purpose: Define the opt-in, adapter-neutral control plane that routes role work
across installed agent runtimes and models while preserving native runtime
capabilities, deterministic evidence, and safe recovery.
Read when: changing adapter manifests, formula dispatch, Hub chat orchestration,
runtime health, model routing, or supervised-run persistence.

> Nav: [docs/](../) · [engineering/](.) · related:
> [Dispatcher contract](dispatcher-contract.md) ·
> [Agent Hub](agent-hub-orchestration.md) ·
> [Adapter parity](adapter-parity.md)

## Product contract

Supervision is part of the optional `cognition` module and is additionally
guarded by `model_routing.enabled`. When either gate is off, existing dispatch,
chat, hooks, and storage behavior stays byte-for-byte equivalent at the
supervision boundary: no child process, health probe, state write, or token is
spent by this feature. Configuration surfaces may still show the disabled
state and the control that enables it.

When enabled, the conversation's current runtime remains the parent. The
supervisor may assign bounded child work to any configured, ready adapter and
model. Children return typed evidence to the parent; they do not replace the
conversation or freely message one another.

Three trigger modes decide **whether the configured policy applies to a given
request**:

| Mode | Policy applies | Effect |
|---|---|---|
| `explicit` (default) | always, while supervision is enabled | the configured route is the contract: validate, check capacity, dispatch |
| `adaptive` | only when the request's complexity is at or above `complexity_threshold` | cheap work skips the policy and runs on the session default |
| `suggest` | always | resolve the full route and return it **without executing** (`status="skipped"`, `output_json.proposed_route`) |

Complexity ranks `CLEAR < COMPLICATED < COMPLEX < CHAOTIC`. A request carrying
no complexity is below every gate, so an unclassified request is never
escalated by accident under `adaptive`.

The gate applies at both ends of the same rule: the cognition layer stops
injecting the role/orchestrator route, and the dispatcher falls back to the
plain session dispatch path. One predicate, two call sites — never two
definitions of "supervised".

`suggest` is a **dry run**, not an interactive approval prompt: it spends no
provider tokens and returns the route it would have taken. Approval is an
operator action — switch the mode to `explicit` or `adaptive`. An
in-conversation approval channel is deliberately deferred; a mode that silently
behaved like `explicit` would be worse than one that does not exist.

**The breaker follows the policy, not the routing preference.** Under
`explicit` — the default — every dispatch goes through the capacity check, so
an operator who enabled supervision purely for rate-limit protection and
configured no roles still gets it. The only paths that skip the breaker are
`enabled: false` and `adaptive` below its gate, both of which are explicit
operator choices to leave that request unsupervised.

A per-role entry outranks the orchestrator default, which outranks the
adapter's own default. A project with one adapter can still route roles among
that adapter's models and efforts — the single-adapter, multi-model case is a
first-class use, not a degraded one.

## Control surfaces and ownership

The policy is project state owned by the kernel, not by Hub. One shared service
loads, validates, deep-merges, locks, and atomically writes
`.coding-os/hub-settings.json::model_routing`; it preserves every unrelated and
unknown settings section. Hub, CLI, and MCP are peer adapters over that service:

- Hub: **Config → Settings → Agent Supervision**;
- CLI: `cos supervision show|enable|disable|set`;
- MCP: `cos_supervision_config` with `show`, `enable`, `disable`, or `set`.

The CLI and MCP surfaces work without installing or starting Hub. All three
surfaces must round-trip the same normalized policy, including nested
`orchestrator`, `roles`, and `cooldown` defaults. A partial or older settings
file is migration-safe: readers receive the current complete shape, while a
write keeps unrelated settings intact. A malformed file fails closed on write
instead of being replaced with defaults.

Headless examples:

```bash
cos supervision enable
cos supervision set --mode adaptive --complexity-threshold COMPLICATED \
  --fallback-policy next_eligible --max-parallel 3
cos supervision set --orchestrator-model claude-sonnet-5-5 --orchestrator-effort medium
cos supervision set --role reviewer --role-model claude-haiku-5-5 --role-effort low
cos supervision set --role architect --role-model claude-opus-5-5 --role-effort xhigh
cos supervision disable
```

Every write is validated against the adapter descriptors before it lands: a
role pinned to an unknown adapter, to a model that adapter does not declare, or
to an effort on an adapter without `effort_selection` is rejected at write time
with the reason. This is deliberate — a policy the dispatcher can never satisfy
is a silent outage discovered at the worst moment.

## What consults the policy, and when

A policy nothing reads per-prompt is indistinguishable from a policy that is
switched off. `nudge-model-routing.sh` states that supervision is enabled;
`resolve-supervise-route.sh` (UserPromptSubmit) is what makes it *apply*: for a
formal gate with a composed role chain it resolves the active role through the
same precedence the dispatcher uses, writes the result to the panel's
`.supervise-route`, and surfaces the resolved `adapter/model/effort` to the agent
and to the transparency banner.

Resolution is deterministic and read-only. The hook spends no provider tokens
and spawns no child: it answers "if this role dispatched right now, where would
it go", which is the fact an operator needs to see and the agent needs in order
to pass `adapter=`/`model=` when it does dispatch. Execution stays an explicit
act — `cos_dispatch_formula_run` costs a real sub-session, so auto-spawning one
per prompt would be a token incident wearing a feature's clothes.

The mode still decides what the resolution means:

| Mode | `.supervise-route` | Agent directive |
|---|---|---|
| `explicit` | resolved route | dispatch on this route when you dispatch |
| `adaptive` | resolved route only at/above `complexity_threshold` | below the gate: session default, no route written |
| `suggest` | resolved route, marked `proposed` | report the route; do not dispatch on it |

Freshness and ownership follow the gate contract: the hook reads the panel's
`.thinking_os-gate` and `.roles`, is debounced once per (session, role), and
fails open. A stale or absent route is reported as absent — never as the
last session's answer.

## Raptor shape

The feature adds one cohesive registry and one health state machine. It reuses:

- adapter manifests for discovery and capability declarations;
- the existing dispatcher port for execution;
- formula dispatch rows for run evidence and native identity;
- project settings for opt-in policy;
- cognition traces and Hub event streams for observability.

It does not add a second board, workflow engine, transcript store, provider
gateway, or provider SDK import in `src/core/**`.

## Design precedents

A survey of production multi-agent orchestrators and agent-interop protocols
preceded this design. The findings are recorded as portable patterns; the
systems they came from are not named here, because a rule that only holds while
you remember its source is a rule that rots.

**Scope the runtime, not the conversation.** The mature systems bind an agent
to a *workspace* and record the chosen runtime on the run itself, immutably.
Changing settings never retargets a conversation that is already in flight.
Coding OS follows this: a Hub project supplies the workspace scope, and a run's
adapter plus capability snapshot are frozen at creation.

**Carry two identities.** Every implementation that bridged an external agent
hit the same defect: the orchestrator's session id and the runtime's native
thread id are different id-spaces, and code that conflates them breaks on
resume. Supervised runs persist `run_id` *and* `native_thread_id`, and Hub
links transcripts by native identity rather than copying them.

**Negotiate capability; never simulate it.** The protocols that aged well
advertise features and let the client degrade honestly; the integrations that
aged badly faked resume or fork and failed at the edge. Hence
`runtime_entrypoints.capabilities`: a missing capability is an explicit
`invalid` failure, never a quiet success on a downgraded path.

**Keep orchestration deterministic and above the agent.** Sequential,
concurrent, hand-off, and group patterns are *policy*, not provider features.
The systems that put them in plain, checkpointed control flow stayed debuggable;
the ones that relied on agents freely messaging each other could not be
budgeted, cancelled, or reproduced. Supervision is therefore a typed state
machine, and free agent-to-agent chat is not a control plane.

**Prefer the runtime's own surface.** Where a runtime already exposes
parent-controlled child agents with per-child model, effort, and sandbox, going
through a lowest-common-denominator protocol discards exactly the capabilities
worth having. Adapters drive native surfaces; a portability protocol belongs at
the edge, as an optional compatibility adapter, not as the internal contract.

**Return evidence, not transcripts.** Children hand their parent a typed slice.
Unbounded transcript relay is what turns a fan-out into a context-window
incident.

### Rejected alternatives

| Alternative | Why not |
|---|---|
| Adopt a general multi-agent framework as the kernel | Duplicates the board, roles, formula chains, persistence, and tracing this repo already owns, and still does not solve native runtime identity. |
| Use an interop protocol as the internal contract | Real implementations have capability gaps (resume/fork), while the kernel needs native steer, hooks, and evidence semantics. |
| Route through a model-provider gateway | Switching *providers* is not switching *agent runtimes* — it discards tools, sandboxes, sessions, subscriptions, and hooks. |
| Let agents message each other freely | Cannot be checkpointed, budgeted, cancelled, or reproduced. |
| Hardcode adapter routing in core | Breaks adapter autonomy (P8) and makes every future adapter a kernel change. |

## Adapter descriptor

Every adapter may advertise these provider-neutral fields without changing the
existing Hub-chat `runtime` flag:

```yaml
runtime_entrypoints:
  dispatch: "sdk_dispatcher.py"
  transcript: "chat_provider.py"
  account: "account_probe.py"
  capabilities:
    - dispatch
    - model_selection
    - effort_selection
    - structured_output
    - account
models: []
efforts: []
```

The adapter owns SDK imports and converts native errors into the normalized
dispatch result. Core discovers directory ids rather than enumerating provider
names. Missing runtime fields mean unsupported capability, not a degraded
success.

### Published prices belong to the adapter that needs them

A model entry may carry a `pricing` block. Only an adapter whose runtime does
not report a cost figure declares one: the Claude SDK returns `total_cost_usd`
itself, so the claude descriptor has no table, while the Codex CLI reports
tokens and no money, so without a table every codex dispatch lands as a
priceless row and the per-adapter rollup reads as if codex were free.

```yaml
models:
  - id: gpt-5.6-sol
    pricing:
      unit: usd_per_mtok
      source: https://platform.openai.com/docs/pricing
      retrieved: "2026-08-21"
      long_context_input_tokens: 272000
      rates:
        short: { input: 5.00, cached_input: 0.50, cache_write: 6.25, output: 30.00 }
        long: { input: 10.00, cached_input: 1.00, cache_write: 12.50, output: 45.00 }
```

`source` and `retrieved` are required, because a price table is the one kind of
constant that goes wrong silently — the numbers stay plausible while the vendor
changes them, and a reader with no provenance cannot tell a current figure from
a two-year-old one.

The tier is metered on **input** tokens, cached and written ones included: above
`long_context_input_tokens` the whole call bills at the `long` rates. A long
answer to a short prompt is not a long-context request. Cached reads and cache
writes each bill at their own rate, so an adapter that omits them understates
every cached run. Core does the arithmetic
(`dispatcher_helpers.price_tokens`); the adapter maps its runtime's own usage
field names onto the rate buckets.

A model named in a request but absent from the catalog is priced at **nothing**,
not at a neighbour's rates. An empty cell is honest; a confident wrong number
is not.

## Account state — what a plan has left

A dollar figure answers "what did that cost". On a subscription it does not
answer the question the operator actually has, which is *how much of the plan is
left* — the money was already spent at the start of the billing period, and the
budget being consumed is a quota.

Both runtimes already write their rate-limit state to disk, so no credential and
no network call is involved:

| Adapter | Source | Freshness |
|---|---|---|
| `claude` | `~/.claude.json` → `cachedUsageUtilization` | written by Claude Code, typically when `/usage` runs |
| `codex` | newest `~/.codex/sessions/**/*.jsonl` → `token_count.rate_limits` | written on every Codex turn, so supervised dispatches keep it current |

`account_probe.py` in each adapter reads its own file; `thinking_os/account_status.py`
normalizes, sorts and ages the result. The Hub quota panel that rendered it was
removed in TASK-1079; three rules still make any reader of it trustworthy:

1. **Every window the provider reports is shown, not just the headline pair.**
   On a real account the two headline windows read 0% and 49% while the binding
   limit was a per-model weekly cap at 78% — the one about to bite was the one a
   two-window view would have hidden.
2. **A reading always carries its age.** Both sources are caches; the Claude one
   was observed 9.7 hours stale in normal use. A percentage with no timestamp
   invites the reader to assume it is live, so the age renders whether or not it
   is old, and past 15 minutes it is marked stale.
3. **Absence is reported as absence.** A provider with no state file yields
   `status: unavailable` and a reason. Never `0%`, which reads as "plenty left".

### A reported cost is not always money

`auth_mode` accompanies both the quota and the cost payloads, and comes from the
adapter's own login state rather than a Hub setting: the setting is a
declaration made once that drifts silently, while the probe reads what the
runtime will actually bill. The setting remains the fallback when no probe can
answer. It is reported per adapter, because one project can meter an API key on
one provider and run a flat subscription on another — a single global flag
labels one of the two wrongly.

Under `subscription` the figure is the API-equivalent price of the tokens, and
the Hub labels it *notional (subscription — not billed)*. The stored number is
never altered by that framing: an operator on `api_key` reads the same row and
needs it to be real.

## Routing policy

Project settings extend the existing `model_routing` section:

```yaml
model_routing:
  enabled: false
  mode: explicit
  complexity_threshold: COMPLICATED
  fallback_policy: fail_closed
  max_parallel: 3
  cooldown:
    default_seconds: 300
    maximum_seconds: 3600
  orchestrator:
    adapter: ""
    model: ""
    effort: ""
  roles: {}
```

`orchestrator` is the **project-wide default target** for supervised work: any
role without its own entry inherits its adapter, model, and effort. A per-role
entry overrides it field by field, so pinning one cheap reviewer does not force
you to re-state the default for every other role. The orchestrator model and
effort are also what the Hub chat composer falls back to when a turn does not
name its own.

Resolution order is deterministic:

1. explicit request override;
2. project role policy;
3. project orchestrator policy;
4. active preset hint;
5. role default;
6. empirical routing history;
7. adapter default.

Adapter selection happens before model and effort validation. A selected model
must belong to the selected adapter descriptor. Every parallel request resolves
its own dispatcher; a fan-out never shares one implicit session dispatcher.

### Model catalogs

`models:` in an adapter descriptor is the catalog offered to operators — it
drives the Hub pickers and write-time validation. An adapter may declare
`model_selection` with an **empty** catalog: that means "this runtime forwards
any model string, but Coding OS does not maintain its list". Core does not
invent model ids for a runtime that has not published one. The consequence is
explicit rather than silent:

- validation accepts any non-empty model string for that adapter;
- the Hub renders a free-text field instead of an empty, unusable select;
- the operator owns the correctness of the string they typed.

A populated catalog is strictly better and is the expected end state.

`fallback_policy` values:

- `fail_closed`: return the unavailable reason without switching runtimes;
- `same_adapter_default`: keep the adapter and use its default model;
- `next_eligible`: select another policy-eligible adapter before execution.

Fallback is never allowed after an uncertain write or after a native run has
accepted mutable work.

## Runtime health and capacity

### What a limit actually applies to

Providers do not meter "an adapter". They meter an **account** and, within it,
**each model pool separately** — Anthropic states both plainly: limits "are set
at the organization level", and "rate limits are applied separately for each
model; therefore you can use different models up to their respective limits
simultaneously" ([rate limits](https://docs.claude.com/en/api/rate-limits)).
Pools are not one-per-model: Opus 4.x share a pool, Opus 5 has its own, Sonnet 5
is separate from Sonnet 4.x.

Cooling a whole adapter therefore removes capacity that provably still exists —
and it defeats the feature's main use, since routing a reviewer to a cheap model
and an architect to an expensive one is exactly a bet on independent pools.

So health is keyed by **model pool**, declared by the adapter because it cannot
be derived from a model id:

```yaml
models:
  - id: claude-opus-4-8
    bucket: opus-4x        # shares a pool with the other Opus 4.x models
  - id: claude-haiku-4-5
    bucket: haiku-4-5      # independent pool
```

The health key is `<adapter>:<bucket>`, or plain `<adapter>` when the adapter
declares no pools — which keeps a pool-less adapter behaving exactly as before.
Hub summarises an adapter across its pools: the most restrictive state, the
**soonest** recovery, and which pools are limited. Clearing an adapter's health
clears every pool it meters against.

Scope stops at the project, not the account: two projects sharing one
organization each discover the same limit separately. Account-wide health needs
a credential identity the kernel must not read (P8), so it is deferred until a
real multi-project account limit is observed rather than guessed at.

The state machine is:

```text
healthy -> cooling_down -> half_open -> healthy
                         -> cooling_down
```

Normalized failure metadata:

```text
category       capacity | auth | unavailable | timeout | provider | invalid
retryable      true | false
retry_after_s  optional positive integer
outcome        known_failed | unknown
```

Rules:

- Only a retryable `capacity` failure opens the circuit automatically.
- `retry_after_s` wins when supplied; otherwise exponential cooldown starts at
  the configured default and is capped by the configured maximum.
- Work is not sent to a cooling adapter. This avoids retry storms and paid
  probes that cannot succeed.
- At expiry, exactly one caller obtains the half-open probe lease. Concurrent
  callers continue to use fallback or fail closed. The lease is held for the
  probe request's own timeout, not a fixed window — a lease shorter than the run
  it guards admits a second caller mid-probe, which is the retry storm the
  breaker exists to prevent.
- A probe that fails for a non-capacity reason releases its lease immediately.
  That failure says nothing about capacity, so it must not stall recovery for
  the rest of the lease.
- When every eligible adapter is cooling, the caller is told the **soonest**
  recovery across the fleet and which adapters are waiting — not whichever
  adapter the resolution loop happened to check last.
- A successful probe resets failure count and returns the adapter to healthy.
- Another capacity failure extends the cooldown.
- Authentication and configuration failures remain unavailable until readiness
  changes; they are not treated as timed capacity limits.
- **Provider-side overload (529) and internal errors (5xx) are not your quota.**
  They classify as `provider` + `retryable`, never `capacity`, so a brief
  provider blip cannot cool an adapter for the configured window — while still
  telling the caller the request is worth retrying.
- A probe that is settled back to healthy keeps its `failure_count`, so an
  unrelated error cannot reset an escalating backoff.
- An adapter that raises instead of returning a result still releases its probe
  lease; otherwise a crash would strand recovery for the whole lease window.
- Process restart preserves cooldown state. Wall-clock timestamps make recovery
  deterministic across sessions.
- Operators may clear a cooldown explicitly, but enabling supervision never
  clears health state implicitly.

The first release detects capacity from adapter-normalized errors. It does not
poll provider billing endpoints or claim to know subscription quota before a
runtime reports it.

### Normalization is an adapter obligation, not a convention

The kernel cannot guess a category it was never given: an adapter that returns
`error_category=None` for a provider limit never opens its breaker and will
retry-storm a limit that cannot succeed. Because every future runtime inherits
this path, the requirement is enforced rather than documented — a parity suite
runs over **every** adapter declaring `dispatch` and requires that it:

- classifies at least one common provider limit wording as retryable `capacity`
  with `outcome="known_failed"`;
- extracts a provider-supplied retry delay when the message carries one;
- leaves a timeout `unknown` so it can never be replayed;
- reports auth failure as `auth`, never as a timed limit;
- returns some category for an unanticipated failure rather than a success shape.

A dispatch that still returns an unclassified failure is logged at warning level
naming the adapter, so a third-party runtime that skipped the contract is
visible in the log rather than silently unprotected.

Health state lives in the project's own database, so the cooldown one project
learns is not shared with a sibling project using the same account. Adding
account-scoped health is deliberately deferred until a real multi-project
account limit is observed.

## Dispatch identity and evidence

Identity uses the [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
rather than names invented here, so a new runtime learns what to emit from a
public spec and any OTel-aware tool can read the envelope. Each supervised child
returns, in its result metadata:

| Attribute | Meaning |
|---|---|
| `gen_ai.provider.name` | the adapter that ran the work |
| `gen_ai.agent.id` | the semantic role |
| `gen_ai.request.model` | the model actually used |
| `capacity_scope` | the model pool its health is metered against |
| `health_state` · `health_probe` | breaker state at dispatch, and whether this was the recovery probe |
| `error_category` · `retry_after_s` | normalized failure and provider-supplied wait |

The parent receives an `EvidenceBundle` or an explicit failure. Raw child
transcripts remain adapter-owned and are linked by native identity rather than
copied into parent context.

### Spend is reported per adapter, never as one number

`formula_dispatches` carries `adapter`, `model`, `effort` and `cost_usd` on every
row, so any read path MUST preserve that dimension and report a `by_adapter`
rollup alongside the formula×day rows (the Hub cost panel that did so was
removed in TASK-1079). A single blended total is not an acceptable answer to "what did each
runtime cost" — the entire reason to route work across providers is to compare
them, and an aggregate that erases the provider hides both the saving and the
overrun. Rows whose `adapter` is NULL are pre-attribution history and report as
`unattributed` rather than being silently folded into one of the real adapters.

**A reported cost is not always money.** Under a subscription login the SDK
still emits `total_cost_usd` — the API-equivalent price of the tokens, not a
charge. Presenting it as spend tells a subscription operator they paid for work
that came out of quota. The rollup therefore reports the project's `claude_auth`
mode alongside the figures, so a consumer labels `subscription` numbers notional
and `api_key` numbers real. The stored value stays identical either way; only
the framing changes, because the same number means two different things and the
reader cannot tell which from the number alone.

**A failed dispatch is recorded too.** Persistence covers every *terminal*
outcome — `ok`, `timeout` and `error` alike — because a run that exhausted its
turn budget or hit a provider error still consumed wall-clock and tokens. Writing
only successes makes failed spend invisible and, worse, makes a chronically
broken route look like an idle one: both report zero. The only case that is
deliberately not written is a schema-validation failure, where the row would
carry an `output_hash` over untrusted output.

### When dispatch fires by itself

Dispatch is agent-initiated by default, and for six days that meant it never
fired: the policy validated, the banner named a route, and nothing ran. The
automatic trigger closes that, but deliberately narrowly.

**Only the two review roles are dispatched at `testing`.** `reviewer` runs every
round; `security_auditor` runs when the task's own diff touches security-sensitive
code (below). Every other role is a target the agent dispatches on purpose, so
pinning `implementer` to another provider does not make every move to `testing`
spawn an implementer. Dispatching every role pinned away from the session's
adapter would start nine Claude roles for one move from a Codex session under the
default pins, `architect` and `debugger` on Opus among them.

A review runs in a child even on the session's own adapter: a fresh context that
did not write the code is the part of a review worth paying for (~$0.40 and ~45s
on Sonnet, measured). A second provider adds an independent blind spot on top,
which is why `reviewer` and `security_auditor` are the roles worth pinning across
providers: both exist to disagree with the author, and a reviewer from the
author's own family mostly agrees with itself.

The trigger fires on the `in_progress → testing` transition — the first moment
there is finished work to review, and once per task rather than per prompt. It
runs **detached**: a codex dispatch measured 123s, and a PostToolUse hook holding
the tool call open that long would be worse than no trigger at all. Results land
in `formula_dispatches` and in `$COS_PANEL_DIR/.dispatch-results`, which the next
prompt surfaces so the operator sees which adapter and model ran without querying
the database.

The trigger reads both ways a task reaches `testing`: the `cos_task_move` tool
and a `cos task-move … --to testing` command.

**Every testing round is reviewed; supervision only decides who reviews.** With
supervision on, each review role runs where its pin says: another provider, or the
session's own adapter with the pinned model and effort. With supervision off, or a
role left unpinned, it runs on the session's own adapter at the role's default
model. Whether the operator turned routing on must never change whether, or how
thoroughly, the work was checked.

**A review is weighted like the task.** The level token the agent recorded in
the panel's Cynefin gate decides, and the justification text after it is ignored.
A CLEAR or COMPLICATED task is reviewed at the role's default model (Sonnet for
`reviewer`, $0.25 to $0.55 and about a minute a review), while a COMPLEX or CHAOTIC task, or any diff the security
auditor is due for, is weighty. A weighty review that nothing pins runs on the
session's own model (`$COS_AGENT_MODEL`), the one the operator chose for the work,
at effort `high`, but only when the session adapter's catalog lists it and its
strength is known to be no weaker than Sonnet; a model of unknown strength, such as
another provider's, never stands in. Otherwise it uses the role's `complex` tier.
This applies only with routing off: when the policy applies, its pins and its
orchestrator default decide, and a pin that names only a model is still a pin.
The session's effort cannot be read from a hook, so `high` replaces the adapter's
automatic `xhigh` for top-tier models, which made one review take 6.5 minutes.

Every weighty review, pinned or not, also gets the room a stronger model needs:
the role's `full` intensity, twice its turn budget and 420 seconds; at the
routine budget (11 turns, 120 s) an Opus review runs out of both. Measured on this
repo, a weighty Opus review costs $1.60 to $3.10 and takes 3.5 to 6.5 minutes.
A weighty review on
the session model shares the author's blind spots; pinning a second provider under
supervision is how to buy an independent one.

### A review on the session's own runtime runs as its native subagent

A detached SDK child is invisible in the operator's chat: it shows up only as a
pulse line after it finished. When a review role lands on the session's own
adapter and that adapter declares a native review agent
(`adapter.yaml::native_review_agents`, role → agent name), the review runs as
that runtime's own subagent instead, so it appears under the session in the
desktop app and the IDE plugin like any other subagent. Claude declares
`cos-reviewer` and `cos-security-auditor` (the hook matchers and the definition
file names repeat these names; a parity test keeps them in step); their definitions ship from
`src/adapters/claude/agents/` into the project's `agents_dir` (`.claude/agents/`)
through `cos init` and `cos update`. They carry no `model` field, so they inherit
the session's model, and only `Read`, `Grep` and `Glob`.

| Step | Who | What happens |
|---|---|---|
| task enters `testing` | `auto-dispatch-crossprovider` (PostToolUse) | starts the detached run for any cross-provider target, then writes each native role's `running` row with the exact call in `native`, appends the request (task, round, role, agent, call, audit digest, scope files) to `$COS_PANEL_DIR/.native-reviews.jsonl`, and returns `additionalContext` under the `BOARD_EVENTS` header telling the agent to make that call with the prompt `Review TASK-N round R` |
| agent calls `Agent` | `native-review-subagent` (PreToolUse `Agent`, `SendMessage`) | refuses a review agent's call unless its prompt names an open request of this session and its model is the planned one, and refuses a `name` (which would make the reviewer addressable); marks the request it approved. It also refuses a `SendMessage` to any subagent that ran a review still open, a reopened one included. The author cannot steer, soften or downgrade its own review this way |
| subagent starts | `native-review-subagent` (SubagentStart) | claims the oldest approval no start has used yet, picking and claiming in one locked step, so two reviews approved before either subagent starts go to one start each; a claim uses up every approval of its request (a restart re-approves and re-claims; the newest start owns the review), writes the full package (role instructions + review package) to `$COS_PANEL_DIR/review-packages/`, and injects it as the subagent's context; anything past the 10,000-character hook cap (usually the diff) stays in the file, which the context names |
| subagent hands back | `native-review-subagent` (PreToolUse `SubagentHandback`) | the report is `tool_input.message`. A message with the role's output JSON, carrying a boolean `passed`, is parsed with the same parser and out-of-scope check as a detached review and written as the `done` row; anything else is denied, and Claude Code asks the subagent to deliver again |
| subagent stops | `native-review-subagent` (SubagentStop) | only when no hand-back was recorded: parses `last_assistant_message`; with no JSON there either, the request reopens with its `native` call, once, and a second failure is the `error` row |

Only the subagent whose start claimed the request can record it: hand-back and
stop match on `agent_id`, so another subagent of the same type can neither
record over a running review nor drop its verdict. The verdict reaches the
ledger without passing through the main agent, and with the prompt and model
fixed by the guard the agent cannot shape the review through its call. The
package (task text, diff, findings) is the author's writing; the agent
definitions and the package header tell the reviewer it is material to review,
never instructions. What this does not cover: the ledger, the requests file and
the package file are plain files under `.coding-os/` that the author's session
could write, as the detached path's ledger always was; the guard closes the
channel an honest agent would use, not a session set on forging its own record.

A `done` row needs a verdict: the gate reads a `done` row with no boolean
`passed` and no findings as a review that could not run, on both paths, so an
unfinished report never reads as a pass.

The model follows the task's weight: `sonnet` for a routine review, a pinned
Claude model as its tier alias, and for a weighty unpinned review no model
(inherit the session's) when the session's model qualifies as above; otherwise
the role's `complex` tier (`opus`), never a model weaker than Sonnet.

A native row that was never started does not go stale: it is in the agent's
power to start it, so `DOD_REVIEW_PENDING` keeps repeating the call instead of
letting the wait turn into a skipped review. A session that cannot make the call
(the guard refuses it, the session runs another runtime, or the planning session
ended) opens a round of its own by moving the task back to `in_progress` and to
`testing`; the refusal says so. A started review that dies without a result
still goes stale at 20 minutes and ends as the ⚠️ line, as a dead detached review
does. A finished or superseded request is dropped from the requests file at the
next plan, with its package file. Both the plan and the detached run write a
native role's `running` row and request, so a plan cut short by the hook's
timeout still leaves the review asked for. Every write to the requests file holds
the panel's lock (`.native-reviews.lock`) and a request is added once per id:
measured in the live run, a prune that read the file before the detached run
appended the auditor's request rewrote it without that line; the
hook's budget is 30 s against the 0.3 s measured.

A project whose `agents_dir` lacks the definition (not yet updated), or holds a
definition that differs from the one the adapter ships, keeps the detached
dispatch: the definition sets the reviewer's tools and instructions, so an edited
copy is not trusted to review. A definition linked while a session runs, as
`cos update` does, reaches that session from its next turn, not within the turn
that linked it (measured: "not found" in that turn, listed at the next prompt);
the pending line repeats the call, so the next turn starts it. Cross-provider
targets, and every target in a session whose adapter declares no native agent
(Codex), keep the detached dispatch; the same PostToolUse output then carries a
start line naming role, adapter and model
(`🛰️ TASK-N review started — reviewer@codex (gpt-5.6-sol)`), and the result
arrives through `.dispatch-results` as before. The foreground plan measured
0.28–0.37 s on a 60,000-character diff, against the hook's 10 s budget.

Debounce is keyed on `(task_id, role, round)`, where the round is how many times
the task has entered `testing` (counted from `task_status_history`). A repeated
hook for the same move never re-spawns a review; a task that went back to
`in_progress` and returned is a new round and gets a fresh one, because a review
whose findings were fixed has to look at the fix before it can release the task.

### When the security auditor runs

The reviewer reads security too, but a specialist pass catches what a generalist
skims, and it costs a second run, so it is spent where it can matter: when the
task's linked commits touch a path that is security-sensitive in any stack
(`board_os/review_security.py` owns the list).

| Sensitive because | Paths |
|---|---|
| it runs commands on the user's machine or in CI | shell scripts, Python under a `hooks/` directory, git hooks (`.husky/`, `.githooks/`, `.pre-commit-config.yaml`), `Makefile`, CI config (`.github/workflows/`, `.gitlab-ci.yml`, `.circleci/`, `Jenkinsfile`), Dockerfiles and compose files |
| it decides who may do what | a path naming auth, login, token, secret, credential, password, permission, crypto, csrf, cors, jwt, oauth, rbac, sanitize, tls, ssl, cert or security |
| it pulls in outside code | dependency manifests: `package.json`, `pyproject.toml`, `setup.py`, `requirements*.txt`, `Pipfile`, `go.mod`, `Cargo.toml`, `Gemfile`, `composer.json`, `pom.xml`, `build.gradle` |
| it holds secrets or agent permissions | `.env` files, `.claude/` and `.codex/` settings, `.mcp.json` |

Docs, tests, Markdown and lock files never count: a lock file's diff is hashes an
auditor cannot judge, and its manifest change is what triggers the audit. A task
with no linked commits gets no auditor: with no diff to read it hunts the whole
repository, and one such audit of a docs-only card cost $1.35.

A later round re-runs the auditor only when the sensitive part of the diff changed
since its last pass, or that pass had a blocking finding to re-check. Its ledger
row keeps a digest of that part (the task's commits limited to the sensitive
paths), so a rework that touched only other files costs a single review. Every
due role's `running` row is written before the first review starts, so the gate
cannot pass in the gap between two reviews.

### The review gate

A review nobody waits for buys false confidence: the agent used to close a task
seconds after `testing`, and the finding arrived two minutes later, on a task
that could no longer go back. The board's Definition of Done therefore reads the
review of the task's **current** round before it allows `complete`, on every path
that completes a task (CLI, `cos_task_move`, Hub).

Each dispatch writes two rows to `$COS_STATE_DIR/review-ledger.jsonl`
(`board_os/review_gate.py` owns the format): `running` when it starts, then its
result with `passed` and up to three findings. `.dispatch-results` stays the
pulse's one-shot notice; the ledger is what the gate trusts.

| Current round's review | Gate | Line the agent echoes |
|---|---|---|
| a role still `running`, started under 20 min ago | `DOD_REVIEW_PENDING` blocks; a row whose native subagent was never started names the `Agent(...)` call to make | `⏳ TASK-N waiting for review — security_auditor@codex` |
| a blocking finding (`critical`/`high`/`medium`, no severity, or `passed: false`) in round 1–2 | `DOD_REVIEW_FINDINGS` blocks | `🔍 TASK-N review found 5 issues, 3 blocking — high: …` |
| a blocking finding still open in round 3 | `DOD_REVIEW_ESCALATE` blocks | `🛑 TASK-N still has 2 blocking issues after 3 review rounds — needs your decision` |
| only `low`/`info` findings | `DOD_REVIEW_NOTES` warns | `📝 TASK-N review passed with 2 minor notes — low: …` |
| at least one role passed, none pending or failing | pass | — |
| a role errored or went stale, or nothing was recorded | `DOD_REVIEW_SKIPPED` warns | `⚠️ TASK-N closing without review — reviewer@claude could not run`, or `closing without a full review` when another role passed |

**One complete review, one rework.** The reviewer reports every finding in a
single pass (its prompt says so), the ledger keeps up to 20, and the refusal lists
them all, numbered, so the author fixes the whole batch in one rework — minor notes
included. A list cut to the first few findings is what turns review into a
one-finding-per-round loop. The next round's reviewer receives the previous
round's findings as `previous_review_findings` and checks those first, then what
the fix broke, instead of hunting afresh. Severity decides whether a finding sends
the task back: notes alone never do. A third round that still has a blocking
finding stops the loop — the agent moves the task to `blocked` with the open
findings as the reason and the operator decides.

A missing review warns rather than blocks on purpose: the trigger cannot fire for
a move made in the Hub or under a runtime without hooks, and a gate that waits for
a review that will never come strands the task. The ⚠️ line makes the gap visible
instead.

The block message carries the line under a `BOARD_EVENTS` header, so the agent
writes it into its reply exactly as it writes a board move
([transparency-banner.md](../../src/core/rules/transparency-banner.md)). The
remedy for findings is the rework loop: `testing → in_progress` (🔁), fix, back
to `testing`, which opens the next round. A dispatch that dies without a result
stops blocking at the stale cap, and a false positive is overridden like any DoD
block: `COS_VERIFY_OVERRIDE=1 COS_OVERRIDE_REASON='…'`, which is audited.

### The review package

A reviewer cannot run `git`, so it reviews exactly what it is handed. It used to
be handed only the task id and had to guess the scope from the task file. Each
review now carries, in its input:

| Key | What it holds |
|---|---|
| `task_title`, `task_outcome`, `acceptance_criteria` | read from the task file |
| `review_scope` | the task's own commits, their files and their diff (capped at 60k characters, truncation stated) |
| `verification_evidence` | the suites the author ran in the last two hours |
| `previous_review_findings` | round 2 onward: what the last round found |

A task's commits are known because `link-commit-to-task.sh` (PostToolUse on Bash)
writes each commit made while the task is the session's current task into its
Work Log as `commit <sha> — <subject>`. It reads the sha from git's
`[branch sha]` line, and when a quiet or piped commit prints none, it takes the
recent commit whose subject appears in the command — never simply the newest:
on trunk, `main` also carries other sessions' commits from the same minutes. A
task with no linked commits (work from before the link worked, or a commit
outside a hooked session) falls back to the old behaviour: the reviewer finds
the scope from the task file.

The reviewer maps every acceptance criterion to the test that covers it; a
criterion with no covering test is a `medium` finding. Order of checks: the
author runs the matching suites, the review reads the result alongside the diff,
and any rework changes the code, which the verify gate treats as untested until
the suites run again — so the task always closes on tests and a review of the
same final code.

### What a dispatched child is told

A child is spawned cold: it inherits no parent conversation. It receives its role
prompt, the upstream formulas' output (`input_slice`), the task prompt, and
`shared_context` — the active task's id, outcome and recent work log.

`shared_context` exists because the alternative is worse than ignorance. A role
that does not know which task it is serving still answers confidently, and a
confident answer built on no context is indistinguishable, to the parent, from a
grounded one. That is a hallucination the envelope cannot detect. Adapters that
can reach shared state through MCP may also query it live; adapters running
sandboxed — Codex dispatch runs `--sandbox read-only` with `mcp_servers={}` and
hooks disabled, deliberately, for reproducibility — have `shared_context` as their
only channel, so it is carried in the prompt rather than left to tool access.

### Who writes the route, and why it is the kernel

`adapter` and `effort` are **resolved by core and stamped by core** onto the
`formula_dispatches` row, from the `DispatchRequest` it already built and the
`DispatchResult` the adapter returned. An adapter-supplied `_meta` value still
wins when present, because only the runtime knows whether it honoured the
requested model; but the resolved route is never left NULL merely because the
adapter did not echo it back.

This is deliberate and it is the P8-correct split. The kernel is the component
that *chose* the adapter — asking every present and future runtime to report a
fact core already holds makes each new adapter a chance to silently break the
evidence trail, which is exactly what happened: the columns existed, the
persistence layer read them out of `_meta`, no adapter ever stamped them, and so
every row carried a NULL route while looking structurally complete. The same
applies to `error_category` and `retry_after_s`, which the normalized
`DispatchResult` already carries.

A row whose `status` is terminal therefore always names the adapter that ran it.
A NULL `adapter` now means "this row predates the columns", not "we lost track".

**Not yet built:** the standard also expresses a child's native session as
`gen_ai.conversation.id`, and parent/child as span parenting rather than a
bespoke column. Neither is emitted today, so a fan-out has no tree and Hub
cannot open a child's native transcript.

### Nested event loops are the normal case, not the exception

Every MCP-initiated dispatch already runs inside a live asyncio loop, because
the FastMCP server owns one. A dispatch entrypoint therefore **must not** call
`asyncio.run` and then hope to recover from the resulting `RuntimeError` by
matching its message: the wording is a CPython implementation detail, and a
guard written against the wrong wording turns the single most important path in
this feature into a hard failure that no test notices, because unit tests call
the tool from a thread with no running loop.

Entrypoints ask `asyncio.get_running_loop()` whether a loop is already running
and route to a dedicated thread with its own loop when one is. The check is a
property of the environment, not of an error string.

## Hub behavior

When supervision is disabled, Hub shows the disabled status and enable toggle,
but hides routing controls. When enabled, Hub shows:

- trigger mode and complexity threshold;
- orchestrator and per-role adapter/model/effort policies;
- only configured adapter descriptors;
- readiness and cooldown reason with recovery time;
- fallback, concurrency, and cooldown settings;
- adapter/model badges for every supervised child.

An installed but unavailable adapter remains visible and disabled so the user
can diagnose it. A one-adapter project hides redundant adapter choice while
retaining model and effort policy.

A saved policy always renders its saved value, even when the named adapter is
no longer installed or its runtime went unavailable: the stale target is shown
and labelled as unavailable rather than collapsing to a blank control. An empty
control reads as "nothing is configured", which is the opposite of the truth
and hides the reason dispatch is failing.

## Safety invariants

- One mutable scope has one writer; read-only children may run concurrently.
- Adapter and capability snapshot do not change after a child starts.
- Cancellation is idempotent and propagates from parent to active children.
- An unknown write outcome is never retried or rerouted automatically.
- Budget applies to the complete fan-out, not each child independently.
- Permission requests remain visible and the adapter may be stricter than core.
- Secrets and native provider payloads are never persisted in health details.
- Logs contain product-native adapter ids and normalized categories only.

## Delivery checklist

### Contract and discovery

- [x] Replace research-oriented documentation and remove obsolete public wording.
- [x] Add manifest runtime entrypoints and capability validation.
- [x] Consolidate descriptor loading for config, dispatch, and transcript paths.
- [x] Prove a fixture adapter is discovered without a core literal.

### Policy and Hub

- [x] Extend settings with default-off supervision policy and migration-safe defaults.
- [x] Add role adapter/model/effort controls sourced from descriptors.
- [x] Hide routing controls when disabled while retaining the enable control.
- [x] Show readiness, cooldown reason, and recovery time.
- [x] Expose the same policy through Hub, CLI, and MCP without a Hub dependency.
- [x] Deep-normalize older/partial settings payloads before Hub rendering.

### Dispatch and health

- [x] Resolve a dispatcher per request and support mixed-adapter fan-out.
- [x] Preserve single-adapter multi-model routing.
- [x] Normalize capacity failures in adapter-owned code.
- [x] Persist cooldown and half-open probe leases.
- [x] Apply fail-closed and explicit fallback policies deterministically.
- [x] Prevent automatic replay after an uncertain write.

### Verification and release

- [x] Unit-test policy precedence and future-adapter discovery.
- [x] Test capacity cooldown, persistence, half-open concurrency, and recovery.
- [x] Test disabled zero-overhead behavior.
- [x] Run adapter, cognition, Hub API, UI, docs, and release verification matrices.
- [x] Smoke installed Claude and Codex entrypoints with capability limits reported.
- [x] Adversarially review Raptor part count, failure modes, privacy, and compatibility.
- [ ] Publish matching GitHub and PyPI versions from the verified commit.

### Review follow-ups

- [x] Enforce `mode` and `complexity_threshold` at dispatch instead of describing them.
- [x] Give `orchestrator.adapter/model/effort` a real consumer as the default role target.
- [x] Validate role and orchestrator targets at write time, not only at dispatch.
- [x] Define empty-catalog semantics and stop rendering an unusable empty select.
- [x] Cache adapter dispatch readiness instead of executing entrypoints per request.
- [x] Keep the capacity check off the async event loop.
- [x] Render a saved-but-unavailable target instead of a blank control.
- [x] Restore the design rationale as portable, source-free patterns.
- [x] Document the feature in the README and the operator playbook.

## Release boundary

The shipped slice is supervised formula dispatch plus its Hub policy and health
visibility. General writable interactive chat migration uses the same registry
but is not allowed to expand this release unless the verified dispatcher slice
requires it. This keeps the first implementation opt-in, testable, and small
enough to revert without changing existing chat behavior.
