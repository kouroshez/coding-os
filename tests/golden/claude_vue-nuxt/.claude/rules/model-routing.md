# Agent Supervision (settings-gated)

> **Rule:** When `model_routing.enabled` is on in `$COS_STATE_DIR/hub-settings.json`, formula dispatch follows the configured trigger mode and role policy. When it is off, this rule is inert.

CLI and desktop sessions receive the same project policy through the once-per-session `nudge-model-routing` hook. Hub edits that policy without changing the current conversation's parent runtime.

## The contract

1. **Toggle off (default)** — nothing fires; dispatch behaviour is unchanged.
2. **Explicit** — dispatch only when the operator or active procedure requests a child run.
3. **Suggest** — propose the adapter/model/role route and wait for operator approval.
4. **Adaptive** — after classification, supervise work at or above the configured complexity threshold.
5. **Dispatch** — explicit request fields override per-role policy, then preset and role defaults. Every parallel role resolves its own adapter.
6. **Capacity** — a normalized usage-limit failure pauses only that adapter. The dispatcher uses an eligible fallback only when the failed run is known not to have started; timeout or unknown outcomes are never replayed.
7. **Recovery** — after cooldown, one half-open probe is allowed. Success restores normal routing; another capacity failure extends cooldown.

## Settings source (SSOT)

`hub-settings.json::model_routing` is written by Hub and read fresh per dispatch. Adapter capabilities, models, and efforts come from adapter descriptors; the kernel does not enumerate providers.

## See also

- [Agent supervision](../../docs/engineering/agent-supervision.md)
- [Dispatcher contract](../../docs/engineering/dispatcher-contract.md)
- [src/core/hooks/nudge-model-routing.sh](../hooks/nudge-model-routing.sh) — the per-session directive injector
