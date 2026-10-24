# Idempotency + Pagination — Implementation Patterns

The two patterns most APIs get wrong. Both are simple in theory; both fail in subtle ways at scale.

## Idempotency

### Why It's Mandatory

Networks drop responses. Mobile clients on bad LTE retry. Load balancers fail over mid-request. Without an idempotency contract, a single user tap can become two charges.

The fix is a small protocol the client and server both follow:

1. Client generates a random key per logical operation.
2. Client sends the key on every retry of that operation.
3. Server stores `(key, response)` after the first successful execution.
4. On any retry with the same key, server returns the stored response without re-executing the side effect.

### The Contract

```http
POST /payments
Idempotency-Key: 8e0f7b1d-2a44-4c7f-9b2e-1c5d6e7f8a9b
Content-Type: application/json

{ "amount": 4200, "currency": "USD", "source": "card_xyz" }
```

Server responses:

| Scenario | Status | Header |
|---|---|---|
| First call, success | 201 | normal |
| First call, error | 4xx/5xx | normal |
| Retry, original was success | 201 | `X-Idempotent-Replay: true` |
| Retry, original was 5xx | re-execute | (stored 5xx is NOT a final result) |
| Retry, different body, same key | 409 | `code: idempotency_key_collision` |

**Key rules**:

- Only store FINAL outcomes (2xx, 4xx). 5xx and timeouts → safe to re-execute on retry.
- Compare body hash on retry — if body differs, refuse with 409 (don't silently return old response for new request).
- TTL the stored entry. 24 hours is industry default. Long enough for legitimate retries, short enough to bound storage.
- Return the SAME response on replay — same status, same headers (esp `Location`), same body.

### Storage Schema (PostgreSQL)

```sql
CREATE TABLE idempotency_keys (
    key                 TEXT        PRIMARY KEY,
    user_id             TEXT        NOT NULL,            -- scope to caller
    request_method      TEXT        NOT NULL,
    request_path        TEXT        NOT NULL,
    request_body_hash   TEXT        NOT NULL,            -- SHA-256 of canonicalized body
    response_status     INT         NOT NULL,
    response_headers    JSONB       NOT NULL,
    response_body       BYTEA       NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,                     -- NULL while in-flight
    locked_until        TIMESTAMPTZ                      -- in-flight lock
);

CREATE INDEX idx_idempotency_keys_user_path
    ON idempotency_keys (user_id, request_path);
CREATE INDEX idx_idempotency_keys_created
    ON idempotency_keys (created_at);

-- Sweep job (cron, every hour) — drop entries older than 24h.
DELETE FROM idempotency_keys WHERE created_at < NOW() - INTERVAL '24 hours';
```

### In-Flight Collision

If two requests with the same key arrive simultaneously (genuinely; client retries the request before the first response):

1. First request acquires the row lock (`INSERT … ON CONFLICT DO NOTHING`).
2. Second request sees the row exists with `completed_at IS NULL`.
3. Second request waits up to N seconds for `completed_at` to be set.
4. If filled in time → return that response.
5. If timeout → return 409 `idempotency_key_in_flight` (client retries shortly).

```go
// Pseudocode for the lock dance:
func (s *Store) Begin(ctx context.Context, key, userID, method, path, bodyHash string) (existing *Stored, acquired bool, err error) {
    // Try to insert a placeholder.
    res, err := s.db.Exec(ctx, `
        INSERT INTO idempotency_keys (key, user_id, request_method, request_path,
                                      request_body_hash, response_status, response_headers,
                                      response_body, locked_until)
        VALUES ($1, $2, $3, $4, $5, 0, '{}', '\x00', NOW() + INTERVAL '30 seconds')
        ON CONFLICT (key) DO NOTHING
    `, key, userID, method, path, bodyHash)
    if err != nil { return nil, false, err }
    if res.RowsAffected() == 1 {
        return nil, true, nil  // We acquired the lock; caller proceeds to execute.
    }

    // Someone else owns the key. Read what they have.
    row := s.db.QueryRow(ctx, `
        SELECT request_body_hash, completed_at, response_status,
               response_headers, response_body
        FROM idempotency_keys WHERE key = $1
    `, key)
    var stored Stored
    var hash string
    var completedAt sql.NullTime
    if err := row.Scan(&hash, &completedAt, &stored.Status,
                       &stored.Headers, &stored.Body); err != nil {
        return nil, false, err
    }
    if hash != bodyHash {
        return nil, false, ErrKeyCollision
    }
    if !completedAt.Valid {
        return nil, false, ErrInFlight
    }
    return &stored, false, nil
}
```

### Scoping Keys

Idempotency keys are scoped to `(user_id, method, path)` — NOT global. Prevents:

- A malicious caller from "claiming" a key another user is about to send.
- The same key being legitimately reused for `POST /orders` and `POST /payments` by different consumers.

## Pagination — Cursor Pattern (Default)

### The Contract

Request:

```http
GET /orders?limit=20&cursor=eyJpZCI6Im9yZF9hYmMiLCJjcmVhdGVkX2F0IjoiMjAyNi0wNC0yNlQxNDozMDowMFoifQ
```

Response:

```json
{
  "data": [
    { "id": "ord_b1", "created_at": "2026-04-26T14:25:00Z", ... },
    { "id": "ord_b2", "created_at": "2026-04-26T14:24:00Z", ... },
    ...
  ],
  "page": {
    "next_cursor": "eyJpZCI6Im9yZF9iMjAiLCJjcmVhdGVkX2F0IjoiMjAyNi0wNC0yNlQxNDoxMDowMFoifQ",
    "has_more": true
  }
}
```

Rules:

- `limit`: integer, default 20, max 100. Reject larger values.
- `cursor`: opaque base64 of internal state. Do NOT promise a parseable shape; it's a black box for clients.
- `next_cursor: null` when no more results.
- `has_more: false` is authoritative; clients should stop iterating.

### Cursor Encoding

The cursor encodes the SORT KEY of the last row returned. For "newest first":

```python
import base64
import json
from datetime import datetime

def encode_cursor(last_id: str, last_created_at: datetime) -> str:
    payload = json.dumps({
        "id": last_id,
        "created_at": last_created_at.isoformat() + "Z",
    }, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()

def decode_cursor(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, json.JSONDecodeError):
        raise ValueError("invalid cursor")
    if "id" not in data or "created_at" not in data:
        raise ValueError("invalid cursor")
    return data
```

### The SQL — Tuple Comparison Pattern

For "ORDER BY created_at DESC, id DESC" (stable sort even when timestamps tie):

```sql
SELECT id, created_at, total, status
FROM orders
WHERE user_id = $1
  AND ($2::TIMESTAMPTZ IS NULL OR (created_at, id) < ($2::TIMESTAMPTZ, $3::TEXT))
ORDER BY created_at DESC, id DESC
LIMIT $4 + 1;       -- fetch one extra to detect has_more
```

Wrapper code:

```python
async def list_orders(
    user_id: str,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[Order], str | None]:
    cursor_data = decode_cursor(cursor)
    after_created = cursor_data["created_at"] if cursor_data else None
    after_id = cursor_data["id"] if cursor_data else None

    rows = await db.fetch(
        """
        SELECT id, created_at, total, status
        FROM orders
        WHERE user_id = $1
          AND ($2::TIMESTAMPTZ IS NULL OR (created_at, id) < ($2, $3))
        ORDER BY created_at DESC, id DESC
        LIMIT $4
        """,
        user_id, after_created, after_id, limit + 1,
    )

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1]["id"], page[-1]["created_at"])
        if has_more and page else None
    )
    return [Order.from_row(r) for r in page], next_cursor
```

### Why Cursor Beats Offset

Offset (`?page=3&size=20`) suffers from:

1. **Race conditions**: items inserted between page 2 and 3 → duplicates or skips.
2. **Performance**: `OFFSET 50000` makes the DB skip 50000 rows every request.
3. **Page-jump unreliability**: page numbers shift as data changes.

Cursor is stable: each cursor encodes a precise position. Even if 1000 new rows arrive, your cursor still picks up exactly where you stopped.

### When Offset Is OK

Small (<10k row), fixed datasets where users genuinely want "go to page 7". Admin dashboards, audit log views with date filters that bound the set. Document the limit clearly.

```http
GET /admin/audit-events?page=7&size=50
```

### Backward Pagination

If you need both directions (rare in mobile lists, common in chat):

```json
{
  "data": [...],
  "page": {
    "next_cursor": "eyJ...",
    "prev_cursor": "eyJ...",
    "has_more": true
  }
}
```

Implement with the same tuple-comparison trick but reversed sort, then re-reverse the result list before returning.

### Counts? No.

Resist the urge to return `total: 12345` on paginated endpoints. `SELECT COUNT(*)` against a large table is expensive and gets stale immediately. If you genuinely need a count, expose it as a separate endpoint with explicit caching (`/orders/count`, cached 60s).

If users want a sense of "how much is left", show "Loading more…" or "1–20 of many" instead of a precise count.

### Pagination Anti-Patterns

1. **No max limit** — `?limit=10000` ships 10k rows, OOMs the server.
2. **Cursor that's actually an offset** — defeats the purpose; race conditions return.
3. **Returning the last page as `cursor: null` and an empty `data`** — if there's nothing more, just say so on the prior page.
4. **Cursor that includes user-modifiable fields** — clients tamper, break sort, get duplicate or missing rows.
5. **Different pagination per endpoint** — pick cursor and use everywhere.
6. **GraphQL `first/after` confusion** — if using Relay-style, follow the spec exactly.

## Combined: Both at Once

A single mutating list operation (rare, but exists — bulk import) needs both:

```http
POST /imports/orders
Idempotency-Key: 8e0f7b1d-2a44-4c7f-9b2e-1c5d6e7f8a9b
Content-Type: application/json

{
  "items": [...500 orders...],
  "cursor_after_failure": null
}
```

Server:

1. Idempotency check at the top.
2. Process items in chunks; if a chunk fails, return `cursor_after_failure: <token>` so client can resume from that point.
3. On idempotent retry, return the original outcome including any `cursor_after_failure`.

Most APIs don't need this complexity. But when you do, do it right.

## References

- Stripe API — Idempotent requests: <https://stripe.com/docs/api/idempotent_requests>
- Stripe API — Pagination: <https://stripe.com/docs/api/pagination>
- IETF draft — The Idempotency-Key HTTP Header Field: <https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/>
- Slack Engineering — "Evolving API Pagination at Slack" (still current): <https://slack.engineering/evolving-api-pagination-at-slack/>
