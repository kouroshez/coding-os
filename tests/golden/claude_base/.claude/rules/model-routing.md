# Agent Supervision (settings-gated)

> **Rule:** When `model_routing.enabled` is on in `$COS_STATE_DIR/hub-settings.json`, formula dispatch follows the configured trigger mode and role policy. When it is off, this rule is inert.

CLI and desktop sessions receive the same project policy through the once-per-session `nudge-model-routing` hook. Hub edits that policy without changing the current conversation's parent runtime.

## The contract

1. **Toggle off (default)** — nothing fires; dispatch behaviour is unchanged.
2. **Explicit** (default mode) — the configured policy always applies; what is configured is what runs.
3. **Suggest** — resolve the route and return `status="skipped"` with `proposed_route`, executing nothing. A dry run, not an approval prompt.
4. **Adaptive** — apply the policy only at or above the configured complexity threshold; pass the gate level to the run tools, or the request stays unclassified and below every gate.
5. **Dispatch** — explicit request fields override per-role policy, which overrides the project orchestrator default, then preset and role defaults. Every parallel role resolves its own adapter. The capacity breaker is never gated by trigger mode.
6. **Capacity** — a normalized usage-limit failure pauses only that adapter. The dispatcher uses an eligible fallback only when the failed run is known not to have started; timeout or unknown outcomes are never replayed.
7. **Recovery** — after cooldown, one half-open probe is allowed. Success restores normal routing; another capacity failure extends cooldown.

## Settings source (SSOT)

`hub-settings.json::model_routing` is written by Hub and read fresh per dispatch. Adapter capabilities, models, and efforts come from adapter descriptors; the kernel does not enumerate providers.

## See also

- [Agent supervision](../../docs/engineering/agent-supervision.md)
- [Dispatcher contract](../../docs/engineering/dispatcher-contract.md)
- [src/core/hooks/nudge-model-routing.sh](../hooks/nudge-model-routing.sh) — the per-session directive injector
