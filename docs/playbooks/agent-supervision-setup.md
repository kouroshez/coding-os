<!-- domain:ADAPTERS | layer:playbook | ssot:true | updated:2026-08-07 -->
# Playbook — Turning On Agent Supervision

Purpose: The operator recipe for routing each semantic role to its own adapter, model, and reasoning effort — including the single-adapter case, capacity cooldowns, and how to back the feature out.
Read when: Enabling supervision on a project, pinning a role to a cheaper or stronger model, or diagnosing why a supervised dispatch was refused.
Skip when: You are changing the supervision *implementation* — the contract lives in [agent-supervision.md](../engineering/agent-supervision.md) and this playbook only operates it.
Read next: [agent-supervision.md](../engineering/agent-supervision.md) · [dispatcher-contract.md](../engineering/dispatcher-contract.md) · [model-routing.md](../../src/core/rules/model-routing.md)

> Nav: [Docs Index](../00-index.md)

## 0. What you are turning on

Supervision decides **which runtime and which model executes each role** in a
formula chain, and it stops sending work to a runtime that just told you it is
out of capacity. It is off by default and costs nothing while off.

It is not an agent-to-agent chat system. The conversation you are in stays the
parent; supervision only places the bounded child work a role dispatch already
performed.

## 1. Decide whether you need it

| You want | Enable supervision? |
|---|---|
| One model for everything | No. The default path is unchanged and cheaper. |
| Cheap review, expensive architecture | **Yes** — per-role model policy. |
| Two runtimes installed, work split across them | **Yes** — per-role adapter policy. |
| Survive a provider rate limit without hand-holding | **Yes** — capacity cooldown. |
| Interactive multi-agent conversations | Not this feature. |

## 2. Enable and set a project default

```bash
cos supervision enable
cos supervision set --orchestrator-model claude-sonnet-5 --orchestrator-effort medium
```

The orchestrator target is the **project-wide default** for supervised work.
Every role inherits it until that role gets its own entry.

## 3. Pin the roles that deserve a different tier

```bash
cos supervision set --role reviewer   --role-model claude-haiku-4-5 --role-effort low
cos supervision set --role architect  --role-model claude-opus-4-8  --role-effort xhigh
cos supervision set --role researcher --role-model claude-fable-5
```

Role ids are the 11 semantic roles (`cos_role_info` lists them). A role entry
overrides the orchestrator **field by field** — setting only `--role-model`
keeps the orchestrator's effort.

Writes are validated against the adapter descriptors immediately. If a model or
effort is not declared by the target adapter, the command fails with the reason
instead of saving a policy that could never dispatch.

Clear one back to the default:

```bash
cos supervision set --role reviewer --clear-role
```

## 4. Choose when supervision engages

```bash
cos supervision set --mode adaptive --complexity-threshold COMPLICATED
```

- `explicit` (default) — the policy always applies. Deterministic; what you
  configured is what runs.
- `adaptive` — the policy applies only at or above the complexity gate, so
  routine work keeps running on the session default.
- `suggest` — **dry run**: resolves the route, returns it, executes nothing.

Use `suggest` first on a live project. It answers "what would this cost me?"
without spending a token.

The capacity breaker is never gated by mode — if you enabled supervision for
rate-limit protection alone, leave `explicit` and set no roles.

## 5. Choose what happens when the target is unavailable

```bash
cos supervision set --fallback-policy fail_closed      # default
```

| Policy | Behaviour |
|---|---|
| `fail_closed` | Report the unavailable reason. Never silently switch runtimes. |
| `same_adapter_default` | Keep the adapter, drop to its default model. |
| `next_eligible` | Try another configured adapter before giving up. |

`fail_closed` is the default on purpose: an unnoticed reroute means you are
paying a different bill and getting different behaviour than the policy you
reviewed. Fallback never happens after a run has already accepted mutable work.

> **If you run two or more adapters and want one to cover for the other when it
> hits its provider limit, you must set `next_eligible`.** Under the default
> `fail_closed`, a limited adapter returns the wait time and the healthy adapter
> is left alone — correct, but not automatic failover.

When every eligible adapter is cooling at once, the error names all of them and
reports the *soonest* recovery, so the retry you schedule matches the first
adapter that will actually be able to answer.

## 6. Multiple runtimes

Only when more than one adapter is installed **and** declares `dispatch`:

```bash
cos supervision set --role implementer --role-adapter codex
```

An adapter with an empty `models:` catalog forwards whatever model string you
give it — Coding OS does not invent ids for a runtime that has not published a
list, so the Hub shows a free-text field and the string is yours to get right.

## 7. Living with capacity limits

When an adapter reports a rate/usage limit, it enters `cooling_down` for the
provider's `retry-after` (clamped by your configured maximum) or an exponential
backoff. Work is not sent to it during that window. At expiry exactly one
caller gets a half-open probe; success restores it, another limit extends it.

Inspect and override:

```bash
cos supervision show --format json          # policy + eligible adapters
```

Hub → **Config → Adapters** shows the state, the reason, and the remaining
recovery time, and offers an explicit clear. Clearing is an operator override
of a safety breaker — it is written to `extensions-audit.log`.

Auth and configuration failures deliberately do **not** open the breaker: they
are not timed limits and waiting does not fix them.

## 8. Verify it is doing what you think

```bash
cos supervision show
cos cognition trace <session_id>      # per-child adapter/model/effort + health decision
```

Every supervised child records its adapter, model, effort, health decision, and
normalized error category on the dispatch row.

## 9. Backing out

```bash
cos supervision disable
```

The policy is preserved, and the disabled path is the pre-feature path: no
health probe, no state write, no injected tokens. Health rows survive a
disable — enabling never implicitly clears a cooldown.

## 10. Adding a new runtime to the fleet

A new adapter joins supervision with no kernel change — it is discovered from
`src/adapters/<id>/adapter.yaml`. To participate *safely* it must translate its
runtime's failures into the normalized shape, because the breaker can only act
on what the adapter reports:

| Native failure | Must become |
|---|---|
| rate/usage limit, quota, 429 | `capacity`, `retryable=True`, `outcome="known_failed"` |
| a limit that names a delay | the same, plus `retry_after_s` |
| timeout | `timeout`, `outcome="unknown"` — never replayed |
| not logged in / 401 / 403 | `auth` — not a timed limit, waiting will not fix it |
| anything unanticipated | `provider`, `outcome="unknown"` |

`tests/test_adapter_capacity_errors.py` runs this over **every** adapter
declaring `dispatch`, so a new runtime cannot ship without it. An adapter that
returns no category is not protected by the breaker at all — it would retry a
limit that cannot succeed until the provider blocks it harder.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `no eligible dispatch adapter for '<id>'` | Target not in `.coding-os.yaml::agents`, or it does not declare `dispatch`. | Add the adapter, or set `--fallback-policy next_eligible`. |
| `adapter '<id>' does not support effort selection` | Effort set on an adapter without `effort_selection`. | Clear the effort for that role. |
| `model '<id>' is not declared by adapter '<id>'` | Model not in that adapter's catalog. | Use a declared id, or switch the role's adapter. |
| `<id> is cooling down` | Capacity breaker is open. | Wait for `retry_after_s`, or clear it in Hub if the limit is known-resolved. |
| `all eligible adapters are at capacity` | Every configured runtime is cooling. | Retry after the reported soonest recovery. |
| `capacity recovery probe already running` | Another caller holds the half-open lease for the duration of its probe. | Retry after that probe finishes. |
| A limited adapter keeps being retried | Its `_failure_fields` does not classify that wording as `capacity` — check the warning in the log. | Extend that adapter's token list and add the wording to the parity suite. |
| Policy saved but nothing routes | `mode=adaptive` and the request is below `complexity_threshold`, or `mode=suggest` (dry run). | Lower the threshold, or switch to `explicit`. |
