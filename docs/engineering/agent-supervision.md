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
cos supervision set --orchestrator-model claude-sonnet-5 --orchestrator-effort medium
cos supervision set --role reviewer --role-model claude-haiku-4-5 --role-effort low
cos supervision set --role architect --role-model claude-opus-4-8 --role-effort xhigh
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
  capabilities:
    - dispatch
    - model_selection
    - effort_selection
    - structured_output
models: []
efforts: []
```

The adapter owns SDK imports and converts native errors into the normalized
dispatch result. Core discovers directory ids rather than enumerating provider
names. Missing runtime fields mean unsupported capability, not a degraded
success.

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
row, so the read path MUST preserve that dimension: `/api/cognition/cost` returns
a `by_adapter` rollup alongside the formula×day rows, and the Hub renders the
split. A single blended total is not an acceptable answer to "what did each
runtime cost" — the entire reason to route work across providers is to compare
them, and an aggregate that erases the provider hides both the saving and the
overrun. Rows whose `adapter` is NULL are pre-attribution history and report as
`unattributed` rather than being silently folded into one of the real adapters.

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
