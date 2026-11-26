# Server Sessions vs JWTs — Decision + Implementation

The choice that shapes every other auth decision. Read once; refer to the table when you're tempted to switch mid-design.

## The Honest Comparison

| Concern | Server sessions (opaque token) | JWT (signed claims) |
|---|---|---|
| **Storage** | DB row per session | None server-side (or blocklist) |
| **Read cost / request** | DB lookup or Redis hit | Verify signature (~µs) |
| **Revocation** | Instant (`UPDATE sessions SET revoked_at = NOW()`) | Hard — short TTL or blocklist |
| **Token size** | ~32 bytes opaque | 200-1000 bytes |
| **Logout from all devices** | `DELETE WHERE user_id = X` | Per-user `iat_min` revocation epoch |
| **Multi-service trust** | Need shared session store / call-back endpoint | Self-contained — verify signature |
| **Audit / observability** | Easy — sessions table is the source of truth | Harder — need usage tracking |
| **Mobile-friendly** | Yes — opaque token in Keychain | Yes — opaque token in Keychain |
| **Browser-friendly** | Cookies + CSRF defense | Cookies (CSRF), header (XSS), localStorage (XSS+disk) |
| **Attack surface on theft** | One DB lookup → revoked | Valid until expiry; revocation hard |
| **Cross-domain SSO** | Hard (cookies are origin-scoped) | Easier (just verify the token) |
| **Operational complexity** | Low (one DB) | Medium (key rotation, JWKS, blocklist) |

## Decision Tree

```
Single trust domain (one product, one team's services)?
├─ Yes → Server sessions
│   └─ Need to call other internal services with user identity?
│       └─ Yes → Mint short-lived JWT at the API gateway / business backend.
│                The CLIENT never sees a JWT.
│
└─ No (multiple distinct trust domains, third-party callers)
    └─ JWT — short-lived, signed, with key rotation
        └─ Need revocation? → Blocklist or `iat_min` per-user epoch.
```

## Server Session Implementation

### Schema

```sql
CREATE TABLE sessions (
    id              TEXT        PRIMARY KEY,           -- public token (e.g. "ses_8h2k...")
    token_hash      TEXT        NOT NULL,              -- SHA-256 of id (defense-in-depth: DB dump = no usable tokens)
    user_id         TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id       TEXT        NOT NULL,              -- shared with refresh tokens for theft detection
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,                       -- NULL while active
    user_agent      TEXT,
    ip              INET,
    scopes          TEXT[]      NOT NULL DEFAULT '{}'  -- granted scopes
);

CREATE INDEX idx_sessions_user_active ON sessions(user_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_sessions_token_hash ON sessions(token_hash);

-- Sweep job (hourly): delete sessions revoked > 30 days ago.
```

The token format: `ses_<32 random chars from URL-safe alphabet>`. The DB stores `SHA-256(token)` and only validates by hash — even a full DB dump doesn't yield usable tokens.

### Verify Middleware (Go + Fiber)

```go
func RequireSession(store SessionStore) fiber.Handler {
    return func(c fiber.Ctx) error {
        token := bearerToken(c.Get("Authorization"))
        if token == "" {
            return apperr.Unauthenticated(c, "missing_token", "")
        }

        hash := sha256Hex(token)
        sess, err := store.LookupActive(c.Context(), hash)
        if err != nil {
            return apperr.Unauthenticated(c, "invalid_token", "")
        }

        // Update last_seen async (don't block the request).
        go store.TouchAsync(sess.ID)

        c.Locals("user_id", sess.UserID)
        c.Locals("scopes", sess.Scopes)
        return c.Next()
    }
}
```

Cache hot sessions in Redis with a short TTL (60s) to absorb the read load. Cache invalidation = delete by ID on revoke.

### Verify Middleware (Python + FastAPI)

```python
from fastapi import Depends, HTTPException, Header

async def require_session(
    authorization: str = Header(...),
    store: SessionStore = Depends(get_session_store),
) -> Actor:
    token = bearer_token(authorization)
    if not token:
        raise HTTPException(401, detail="missing_token")
    sess = await store.lookup_active(sha256_hex(token))
    if not sess:
        raise HTTPException(401, detail="invalid_token")
    asyncio.create_task(store.touch(sess.id))
    return Actor(user_id=sess.user_id, scopes=sess.scopes)
```

## JWT Implementation (Internal Service-to-Service)

When the Go backend calls the Python AI adapter, it mints a short-lived JWT:

```go
import "github.com/golang-jwt/jwt/v5"

type ServiceClaims struct {
    Scope []string `json:"scope"`
    jwt.RegisteredClaims
}

func MintServiceToken(privKey ed25519.PrivateKey, kid, userID string, scopes []string) (string, error) {
    now := time.Now()
    claims := ServiceClaims{
        Scope: scopes,
        RegisteredClaims: jwt.RegisteredClaims{
            Subject:   userID,
            Issuer:    "business-api",
            Audience:  jwt.ClaimStrings{"ai-adapter"},
            IssuedAt:  jwt.NewNumericDate(now),
            ExpiresAt: jwt.NewNumericDate(now.Add(5 * time.Minute)),
            NotBefore: jwt.NewNumericDate(now.Add(-30 * time.Second)),  // clock skew
            ID:        uuid.NewString(),                                 // jti for replay tracking
        },
    }
    tok := jwt.NewWithClaims(jwt.SigningMethodEdDSA, claims)
    tok.Header["kid"] = kid
    return tok.SignedString(privKey)
}
```

Verify (Python side):

```python
import jwt
import httpx
from cachetools import TTLCache

JWKS_CACHE: TTLCache = TTLCache(maxsize=4, ttl=600)

async def get_jwks(issuer: str) -> dict:
    if issuer in JWKS_CACHE:
        return JWKS_CACHE[issuer]
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.get(f"{issuer}/.well-known/jwks.json")
        resp.raise_for_status()
    jwks = resp.json()
    JWKS_CACHE[issuer] = jwks
    return jwks


async def verify_service_token(token: str) -> dict:
    unverified = jwt.get_unverified_header(token)
    kid = unverified.get("kid")
    if not kid:
        raise jwt.InvalidTokenError("missing kid")

    jwks = await get_jwks("https://business-api.app.com")
    key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    if not key:
        raise jwt.InvalidTokenError("unknown kid")

    public_key = jwt.algorithms.OKPAlgorithm.from_jwk(key)
    payload = jwt.decode(
        token,
        public_key,
        algorithms=["EdDSA"],
        audience="ai-adapter",
        issuer="https://business-api.app.com",
        leeway=30,                               # clock skew tolerance
        options={"require": ["sub", "iat", "exp", "aud", "iss"]},
    )
    return payload  # {"sub": "usr_…", "scope": [...], ...}
```

### Algorithm Selection — 2026

- **EdDSA (Ed25519)** — first choice. Small keys, fast, no parameter footguns.
- **RS256** — broadly compatible; pick if EdDSA support is missing in any consumer library.
- **ES256** — fine alternative; popular in WebAuthn ecosystem.
- **HS256** — only for symmetric scenarios where the verifier is the issuer. NEVER share the secret across trust boundaries.
- **`alg: none`** — every library MUST reject. If yours doesn't, switch libraries.

### Key Rotation

```
business-api/
  /.well-known/jwks.json   →  { keys: [ {kid:"2026-04", ...}, {kid:"2026-03", ...} ] }
```

- Mint with current `kid`.
- Publish current + previous in JWKS for the lifetime of the longest-lived token.
- Rotate quarterly (or after any suspected key compromise).
- Verifiers cache JWKS for 10 min, refresh on `kid` miss.

## Hybrid Pattern (This Project)

```
Client (RN) ──[opaque session]──► Go API
                                     │
                                     │ Mint JWT { sub: user_id, scope, exp:5m, kid }
                                     ▼
                                FastAPI AI adapter (verifies via JWKS)
```

Best of both:

- Client always uses opaque sessions (revocable, simple to wipe).
- Service-to-service uses short JWTs (stateless, scoped, no extra DB hop on the AI adapter).
- AI adapter never sees the long-lived session token, so a compromise of the AI service doesn't expose user sessions.

## What NOT to Do

1. **Long-lived JWT as the only client credential** — leaks last forever.
2. **Session ID in URL query string** — leaks via referrers, logs, browser history.
3. **JWT in localStorage** for browser apps — XSS reads it.
4. **Stateless JWT for the user-facing API** without a path to revocation.
5. **Storing JWT secret in env vars accessible to client-side build** — pretty obvious mistake but seen in practice.
6. **Using HS256 across services owned by different teams** — shared secret = no trust boundary.
7. **Validating only signature, not `aud`/`iss`/`exp`** — token from one context valid in another.
