<!-- domain:REACTNATIVE | layer:policy | ssot:true | updated:2026-04-29 -->
# Offline-First Patterns

> P: Sync-queue + conflict-resolution patterns every mutating action in the mobile app must follow.
> R: Adding a user-mutating action (log medication, save profile, post message).
> S: Read-only screens that never POST / PATCH / DELETE.
> N: [mobile-rules.md](mobile-rules.md), [../playbooks/mobile-app.md](../playbooks/mobile-app.md)

## 1. Optimistic UI

Every mutation:

1. Updates Zustand state immediately.
2. Pushes the action to `src/mobile/sync/queue.ts`.
3. Drains the queue with `src/mobile/sync/drainer.ts` when connectivity returns.

Never block the UI on a pending sync.

## 2. Action shape

Every queued action is a typed object with `kind`, `payload`, `clientId`, `clientTimestamp`:

```ts
type LogMedicationAction = {
  kind: 'log_medication';
  clientId: string;          // UUID generated client-side
  clientTimestamp: string;   // ISO-8601 in user's local TZ
  payload: { petId: string; medicationId: string; dose: number };
};
```

`clientId` is the idempotency key — the server must dedupe on it.

## 3. Drainer guarantees

- Drainer runs on every `NetInfo` connectivity change AND on app foreground.
- Actions are FIFO per pet / resource group; cross-resource ordering is best-effort.
- A single failure is retried with exponential backoff (`100ms → 1s → 10s → user-visible error`).
- On 4xx the action is moved to `src/mobile/sync/dlq.ts` and the user sees a `<ConflictModal />`.

## 4. Conflict resolution

Three strategies, decide per action type:

| Strategy | When | Implementation |
|---|---|---|
| Last-write-wins | Profile fields, simple state | server overwrites local on 409 |
| Merge | Lists (medication log) | client + server unions on `clientId` |
| User-prompt | Conflicting edits, deletes | `<ConflictModal />` with both versions |

Never silently drop user data.

## 5. Storage

Queue persists via `src/mobile/lib/storage.ts` so app restarts don't lose pending actions. The drainer reads at startup before mounting any UI.

## 6. Tests

- Unit-test `enqueue()` and `apply()` separately with a fake drainer.
- Integration: simulate offline → mutate 3x → reconnect → assert all 3 reach the server.
- E2E (Maestro): airplane mode → action → connectivity → action visible on the server.
