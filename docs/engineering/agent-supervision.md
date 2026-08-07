<!-- domain:ADAPTERS | layer:engineering | ssot:true | updated:2026-08-06 -->
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
chat, hooks, storage, and UI behavior stays byte-for-byte equivalent at the
supervision boundary: no child process, health probe, state write, or token is
spent by this feature.

When enabled, the conversation's current runtime remains the parent. The
supervisor may assign bounded child work to any configured, ready adapter and
model. Children return typed evidence to the parent; they do not replace the
conversation or freely message one another.

Three trigger modes are supported:

- `explicit`: supervise only when the caller requests it.
- `suggest`: propose a route and wait for approval.
- `adaptive`: supervise requests that meet the configured complexity gate.

Manual role policies always outrank adaptive selection. A project with one
adapter can still route roles among that adapter's models and efforts.

## Raptor shape

The feature adds one cohesive registry and one health state machine. It reuses:

- adapter manifests for discovery and capability declarations;
- the existing dispatcher port for execution;
- formula dispatch rows for run evidence and native identity;
- project settings for opt-in policy;
- cognition traces and Hub event streams for observability.

It does not add a second board, workflow engine, transcript store, provider
gateway, or provider SDK import in `src/core/**`.

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

Resolution order is deterministic:

1. explicit request override;
2. project role policy;
3. active preset hint;
4. role default;
5. adaptive eligible-set ranking;
6. adapter default.

Adapter selection happens before model and effort validation. A selected model
must belong to the selected adapter descriptor. Every parallel request resolves
its own dispatcher; a fan-out never shares one implicit session dispatcher.

`fallback_policy` values:

- `fail_closed`: return the unavailable reason without switching runtimes;
- `same_adapter_default`: keep the adapter and use its default model;
- `next_eligible`: select another policy-eligible adapter before execution.

Fallback is never allowed after an uncertain write or after a native run has
accepted mutable work.

## Runtime health and capacity

Health is keyed by `(project, adapter)` and is generic across present and future
adapters. The state machine is:

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
  callers continue to use fallback or fail closed.
- A successful probe resets failure count and returns the adapter to healthy.
- Another capacity failure extends the cooldown.
- Authentication and configuration failures remain unavailable until readiness
  changes; they are not treated as timed capacity limits.
- Process restart preserves cooldown state. Wall-clock timestamps make recovery
  deterministic across sessions.
- Operators may clear a cooldown explicitly, but enabling supervision never
  clears health state implicitly.

The first release detects capacity from adapter-normalized errors. It does not
poll provider billing endpoints or claim to know subscription quota before a
runtime reports it.

## Dispatch identity and evidence

Each supervised child records:

```text
run_id
parent_run_id
adapter_id
native_thread_id
role
model
effort
capability_snapshot
health_decision
status
error_category
retry_after_s
partial
```

The parent receives an `EvidenceBundle` or an explicit failure. Raw child
transcripts remain adapter-owned and are linked by native identity rather than
copied into parent context.

## Hub behavior

When supervision is disabled, no supervision controls appear. When enabled,
Hub shows:

- trigger mode and complexity threshold;
- orchestrator and per-role adapter/model/effort policies;
- only configured adapter descriptors;
- readiness and cooldown reason with recovery time;
- fallback, concurrency, and cooldown settings;
- adapter/model badges for every supervised child.

An installed but unavailable adapter remains visible and disabled so the user
can diagnose it. A one-adapter project hides redundant adapter choice while
retaining model and effort policy.

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

- [ ] Replace research-oriented documentation and remove obsolete public wording.
- [ ] Add manifest runtime entrypoints and capability validation.
- [ ] Consolidate descriptor loading for config, dispatch, and transcript paths.
- [ ] Prove a fixture adapter is discovered without a core literal.

### Policy and Hub

- [ ] Extend settings with default-off supervision policy and migration-safe defaults.
- [ ] Add role adapter/model/effort controls sourced from descriptors.
- [ ] Hide the feature surface when disabled.
- [ ] Show readiness, cooldown reason, and recovery time.

### Dispatch and health

- [ ] Resolve a dispatcher per request and support mixed-adapter fan-out.
- [ ] Preserve single-adapter multi-model routing.
- [ ] Normalize capacity failures in adapter-owned code.
- [ ] Persist cooldown and half-open probe leases.
- [ ] Apply fail-closed and explicit fallback policies deterministically.
- [ ] Prevent automatic replay after an uncertain write.

### Verification and release

- [ ] Unit-test policy precedence and future-adapter discovery.
- [ ] Test capacity cooldown, persistence, half-open concurrency, and recovery.
- [ ] Test disabled zero-overhead behavior.
- [ ] Run adapter, cognition, Hub API, UI, docs, and release verification matrices.
- [ ] Smoke installed Claude and Codex entrypoints with capability limits reported.
- [ ] Adversarially review Raptor part count, failure modes, privacy, and compatibility.
- [ ] Publish matching GitHub and PyPI versions from the verified commit.

## Release boundary

The shipped slice is supervised formula dispatch plus its Hub policy and health
visibility. General writable interactive chat migration uses the same registry
but is not allowed to expand this release unless the verified dispatcher slice
requires it. This keeps the first implementation opt-in, testable, and small
enough to revert without changing existing chat behavior.
