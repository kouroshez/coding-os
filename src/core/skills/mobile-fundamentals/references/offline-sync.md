# Offline Sync — Queue, Retry, Conflict Resolution

The pattern that makes a mobile app feel reliable when the network is anything less than great.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  React component                                                    │
│   useUseCase('markLessonComplete').execute(input)                   │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Use case (application layer)                                       │
│   1. Update LocalCache  ─────►  Re-render via useQuery cache hook   │
│   2. Enqueue Mutation   ─────►  SyncQueue.enqueue(...)              │
│   3. Return immediately (no await on network)                        │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Sync queue (durable, MMKV / SQLite)                                │
│   FIFO of pending mutations with idempotency keys                    │
│   Background worker drains when network is up                        │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Server (eventually consistent)                                     │
│   Receives mutation with Idempotency-Key header                     │
│   Returns canonical state                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## The Sync Queue — Schema

Use SQLite or MMKV. SQLite preferred for >1000 entries or query needs.

```sql
-- mobile/app database (SQLite via op-sqlite or react-native-quick-sqlite)
CREATE TABLE sync_queue (
  id                  TEXT PRIMARY KEY,
  type                TEXT NOT NULL,          -- 'lesson.complete', 'message.send', ...
  payload             TEXT NOT NULL,          -- JSON-serialized command
  idempotency_key     TEXT NOT NULL UNIQUE,
  created_at          TEXT NOT NULL,          -- ISO8601
  next_attempt_at     TEXT NOT NULL,          -- ISO8601, advanced on backoff
  attempts            INTEGER NOT NULL DEFAULT 0,
  last_error          TEXT,
  state               TEXT NOT NULL DEFAULT 'pending'  -- 'pending' | 'failed' | 'sent'
);
CREATE INDEX idx_sync_queue_pending ON sync_queue(next_attempt_at) WHERE state = 'pending';
```

```typescript
// mobile/src/infrastructure/sync/SyncQueueSqlite.ts
import { open, type DB } from '@op-engineering/op-sqlite';

import type { SyncQueue, QueuedMutation } from '@application/ports/syncQueue';

export class SyncQueueSqlite implements SyncQueue {
  constructor(private db: DB) {}

  async enqueue(m: Omit<QueuedMutation, 'id' | 'state' | 'attempts' | 'last_error' | 'next_attempt_at'>): Promise<void> {
    await this.db.execute(`
      INSERT INTO sync_queue (id, type, payload, idempotency_key, created_at, next_attempt_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `, [
      crypto.randomUUID(),
      m.type,
      JSON.stringify(m.payload),
      m.idempotency_key,
      m.created_at,
      m.created_at,
    ]);
  }

  async dequeueBatch(now: string, limit: number): Promise<QueuedMutation[]> {
    const rows = await this.db.executeAsync(`
      SELECT * FROM sync_queue
      WHERE state = 'pending' AND next_attempt_at <= ?
      ORDER BY created_at ASC
      LIMIT ?
    `, [now, limit]);
    return rows.rows._array.map(parseRow);
  }

  async markSent(id: string): Promise<void> {
    await this.db.execute('UPDATE sync_queue SET state = "sent" WHERE id = ?', [id]);
  }

  async markFailed(id: string, error: string, retryDelayMs: number | null): Promise<void> {
    if (retryDelayMs === null) {
      await this.db.execute('UPDATE sync_queue SET state = "failed", last_error = ? WHERE id = ?', [error, id]);
    } else {
      const next = new Date(Date.now() + retryDelayMs).toISOString();
      await this.db.execute(`
        UPDATE sync_queue
        SET attempts = attempts + 1, last_error = ?, next_attempt_at = ?
        WHERE id = ?
      `, [error, next, id]);
    }
  }
}
```

## The Worker

```typescript
// mobile/src/infrastructure/sync/SyncWorker.ts
import NetInfo from '@react-native-community/netinfo';
import { AppState } from 'react-native';

import type { SyncQueue } from '@application/ports/syncQueue';
import type { ApiClient } from '../http/apiClient';

const BACKOFF_MS = [
  0, 1_000, 5_000, 15_000, 60_000, 5 * 60_000, 30 * 60_000,
  60 * 60_000, 4 * 3600_000, 24 * 3600_000,
];
const MAX_ATTEMPTS = BACKOFF_MS.length;

const HANDLERS: Record<string, (api: ApiClient, payload: unknown, key: string) => Promise<void>> = {
  'lesson.complete': async (api, payload, idempotencyKey) => {
    await api.post('/lessons/complete', payload, {
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  },
  'message.send': async (api, payload, idempotencyKey) => {
    await api.post('/messages', payload, {
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  },
  // ... add per mutation type
};

export class SyncWorker {
  private running = false;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(private queue: SyncQueue, private api: ApiClient) {}

  start() {
    this.scheduleNext(0);
    NetInfo.addEventListener((state) => {
      if (state.isConnected) this.scheduleNext(0);
    });
    AppState.addEventListener('change', (s) => {
      if (s === 'active') this.scheduleNext(0);
    });
  }

  private scheduleNext(delayMs: number) {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => this.tick(), delayMs);
  }

  private async tick() {
    if (this.running) return;
    this.running = true;
    try {
      const now = new Date().toISOString();
      const batch = await this.queue.dequeueBatch(now, 10);
      if (batch.length === 0) {
        this.scheduleNext(60_000);
        return;
      }
      for (const m of batch) {
        await this.process(m);
      }
      this.scheduleNext(1000);  // immediately try next batch
    } catch (e) {
      this.scheduleNext(30_000);
    } finally {
      this.running = false;
    }
  }

  private async process(m: QueuedMutation) {
    const handler = HANDLERS[m.type];
    if (!handler) {
      await this.queue.markFailed(m.id, `unknown type ${m.type}`, null);
      return;
    }
    try {
      await handler(this.api, m.payload, m.idempotency_key);
      await this.queue.markSent(m.id);
    } catch (err: any) {
      const retryable = isRetryable(err);
      if (!retryable || m.attempts >= MAX_ATTEMPTS - 1) {
        await this.queue.markFailed(m.id, String(err?.message || err), null);
        // TODO: surface to UI as "couldn't sync — review"
      } else {
        const delay = BACKOFF_MS[Math.min(m.attempts + 1, BACKOFF_MS.length - 1)];
        const jittered = delay + Math.floor(Math.random() * delay * 0.2);
        await this.queue.markFailed(m.id, String(err?.message || err), jittered);
      }
    }
  }
}

function isRetryable(err: any): boolean {
  if (!err?.response) return true;            // network/timeout
  const status = err.response.status;
  if (status >= 500) return true;
  if (status === 429) return true;
  if (status === 408) return true;
  return false;                                // 4xx terminal
}
```

## Key Properties

- **Idempotency-Key on every mutation** — server dedup (see api-design skill).
- **Exponential backoff with jitter** — avoids thundering herd on reconnect.
- **Max attempts** — terminal failure surfaces to UI; do not retry forever.
- **Drains on AppState=active and network=connected** — react to events, don't poll aggressively.
- **No global flush on logout** — abandoning the queue can lose user work; either await drain or warn the user.

## Conflict Resolution

When the server's state and your queued mutation disagree, three strategies. Pick per mutation type, never per-app.

### 1. Last-Write-Wins (LWW)

Simplest. Server takes the latest mutation's value. Used for: cosmetic changes (display name, theme), single-user data with no merge concerns.

```
client mutation: name = "Alice"   timestamp 12:00
server state:    name = "Bob"     last_modified 12:01
→ server keeps "Bob" (newer)
```

LWW requires the server to track `updated_at`. Client sends with `If-Unmodified-Since` (or no precondition; server simply takes whichever request has a higher mutation timestamp).

### 2. Server-Wins (Reject + Surface)

Server compares the client's expected version with current; if mismatch, returns 409 with current state. Client surfaces to user: "your changes conflict — resolve".

Used for: shared resources, payment edits, anything where silent overwrites cause data loss.

```
PATCH /lessons/lsn_123
If-Match: "v3"
{ "title": "Old name" }

→ 412 Precondition Failed
  { "code": "version_conflict", "current": { "version": "v5", "title": "Newer name" } }

Client: shows the conflict UI; user picks "keep mine" / "keep theirs" / merge manually.
```

### 3. CRDT / Merge

For collaborative editing (chat reactions, shared lists). Library: Yjs, Automerge.

Heavy machinery; only use if you genuinely need real-time collab. For "single-user offline app", LWW + 412 conflicts is enough.

## Cache Invalidation on Sync

After a mutation succeeds:

```typescript
import { useQueryClient } from '@tanstack/react-query';

// In the worker after markSent:
queryClient.invalidateQueries({ queryKey: ['lesson', payload.lessonId] });
```

Or use TanStack Query's `useMutation` directly when the call is online:

```typescript
const mutation = useMutation({
  mutationFn: (input) => markLessonComplete.execute(input),
  onMutate: async (input) => {
    // Optimistic: update local state.
    await queryClient.cancelQueries({ queryKey: ['lesson', input.lessonId] });
    const prev = queryClient.getQueryData(['lesson', input.lessonId]);
    queryClient.setQueryData(['lesson', input.lessonId], (old: Lesson) => ({
      ...old, state: 'completed',
    }));
    return { prev };
  },
  onError: (_err, input, context) => {
    if (context?.prev) {
      queryClient.setQueryData(['lesson', input.lessonId], context.prev);
    }
  },
  onSettled: (_data, _err, input) => {
    queryClient.invalidateQueries({ queryKey: ['lesson', input.lessonId] });
  },
});
```

## Showing Pending State

Users want to know "did my action go through?". Show:

- **Inline indicator** on items with pending mutations (small spinner or "syncing" badge).
- **Global indicator** in the navbar showing offline state + pending count.
- **Failure surface** for terminal failures: "couldn't sync — try again" with retry button.

```typescript
// useSyncStatus hook subscribes to queue state changes.
const { pending, failed } = useSyncStatus();

return (
  <View style={styles.statusBar}>
    {!isConnected && <Text>Offline</Text>}
    {pending > 0 && <Text>Syncing {pending}…</Text>}
    {failed > 0 && (
      <Pressable onPress={() => navigation.navigate('SyncErrors')}>
        <Text>{failed} couldn't sync</Text>
      </Pressable>
    )}
  </View>
);
```

## Common Sync Mistakes

1. **No idempotency key** — retries become duplicates.
2. **Naive retry without backoff** — DDoSes own server on reconnect.
3. **Retrying 4xx** — wastes bandwidth on terminal failures; surface them.
4. **No max-attempts** — failed mutations stuck in queue forever.
5. **Sync queue not durable** — app kill = lost mutations.
6. **No cache invalidation after success** — UI shows stale optimistic state.
7. **Optimistic update without rollback path** — error → UI shows wrong state forever.
8. **Drain on logout without warning** — user thought they saved, work is gone.
9. **No conflict UI** — silent overwrites cost users their work.
10. **Sync queue in main thread** — blocks UI while serializing payloads. Use a worker / async batches.

## Source Material

- "Designing Data-Intensive Applications" (Kleppmann) — chapter on conflict resolution.
- TanStack Query docs — Optimistic updates, networkMode.
- Yjs / Automerge docs — for CRDT use cases.
- "Local-first software" — Ink & Switch (read for the philosophy, then back to your queue).
