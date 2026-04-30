<!-- domain:REACTNATIVE | layer:playbook | ssot:true | updated:2026-04-29 -->
# Mobile App Playbook

> P: Routes mobile-specific tasks to anatomy.md, the right rules file, and verification commands.
> R: Picking up any task whose primary work happens in `mobile/`.
> S: Working on web / backend / ai-service code.
> N: [../engineering/mobile-rules.md](../engineering/mobile-rules.md), [../engineering/offline-first.md](../engineering/offline-first.md), [../engineering/accessibility-checklist.md](../engineering/accessibility-checklist.md)

## When to use

Any task that touches `mobile/**/*.{ts,tsx}` — new screens, components, hooks, sync actions, native bridges, or perf work.

## Read selection guide (3-7 files max)

For typical tasks, read in this order:

1. The active task file — `docs/tasks/TASK-NNN-*.md`.
2. [`anatomy.md`](../../skills/react-native-mobile/references/anatomy.md) — file map + entity recipe for the action you're about to take.
3. The matching rule file (`mobile-rules.md` for general, `offline-first.md` for sync, `accessibility-checklist.md` for a11y).
4. The existing parent screen/component/hook the change relates to.
5. `shared/contracts/<resource>.ts` if you're adding an API call.
6. `mobile/store/<slice>.ts` if you're touching shared state.
7. `mobile/sync/queue.ts` if you're queueing a mutation.

Stop reading when no further file would change the implementation decision.

## Steps

1. Classify: which entity recipe in [`anatomy.md`](../../skills/react-native-mobile/references/anatomy.md) matches?
2. Map dependencies: which files do you read, edit, or create?
3. Implement smallest correct change.
4. Add or extend colocated tests (Given/When/Then).
5. Manual smoke: run on iOS simulator AND Android emulator before opening PR.

## Verification

| Changed | Command |
|---|---|
| `mobile/**/*.{ts,tsx}` | `cd mobile && npm run lint && npm test -- --findRelatedTests <file>` |
| `mobile/sync/**` | `cd mobile && npm test -- mobile/sync` |
| `mobile/native/**` | manual native build (iOS + Android) |
| `mobile/e2e/**` | `cd mobile && npx maestro test e2e/<flow>.yaml` |

## Failure modes

- White screen on Android only → Reanimated worklet calling JS-thread API.
- Optimistic state out of sync after reconnect → `mobile/sync/drainer.ts` not idempotent.
- VoiceOver skips an element → `accessibilityRole` missing.
- iOS-only crash on launch → native bridge ADR not implemented for the target version.
