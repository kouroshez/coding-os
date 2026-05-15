# JWT for Service-to-Service — Implementation Reference

The hexagonal Go backend mints short-lived JWTs to authenticate calls to the FastAPI AI adapter. This file is the canonical implementation pattern.

## Token Shape

```json
{
  "alg": "EdDSA",
  "typ": "JWT",
  "kid": "2026-04"
}.{
  "iss": "https://business-api.app.com",
  "aud": "ai-adapter",
  "sub": "usr_8h2k4n9d3p7q",
  "iat": 1745678901,
  "exp": 1745679201,
  "nbf": 1745678871,
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "scope": ["ai:chat", "ai:recommend"],
  "tenant_id": "tnt_abc123"
}
```

| Claim | Required | Purpose |
|---|---|---|
| `iss` | yes | Issuer URL (must match `/.well-known/jwks.json` host). |
| `aud` | yes | Intended audience — verifier rejects if not its own ID. |
| `sub` | yes | Subject (user ID). |
| `iat` | yes | Issued at (Unix epoch seconds). |
| `exp` | yes | Expires at (Unix epoch seconds). 5-15 min for service tokens. |
| `nbf` | recommended | Not-before — defends against issued-in-future replay; allow ~30s clock skew. |
| `jti` | recommended | Unique ID — pin in a replay-tracking blocklist if you need exactly-once semantics. |
| `scope` | optional | Whitespace- or array-separated permissions. |
| `tenant_id`, custom | optional | Multi-tenant routing / RLS hints. |

## Algorithm Choice

| Algorithm | Verdict | Notes |
|---|---|---|
| **EdDSA (Ed25519)** | ✅ default | Fast, small keys, no parameter footguns. RFC 8032. |
| **ES256 (P-256)** | ✅ alternative | Widely supported in browsers/WebAuthn. |
| **RS256 (RSA-SHA256)** | ✅ if EdDSA unavailable | Larger keys (2048+), slower. |
| **HS256** | ⚠️ symmetric only | Use only when verifier == issuer. NEVER share the secret across teams. |
| **`alg: none`** | ❌ never | Library MUST reject. Switch libraries if yours doesn't. |
| **PS256** | ✅ if you need RSA-PSS | Modern padding; pick over RS256 when both are available. |

## Key Management

### Generate Keys (offline, once per rotation)

```bash
# Ed25519
openssl genpkey -algorithm Ed25519 -out priv-2026-04.pem
openssl pkey -in priv-2026-04.pem -pubout -out pub-2026-04.pem

# Then convert pub key to JWK format and add to your JWKS:
#   { "kty": "OKP", "crv": "Ed25519", "x": "...", "kid": "2026-04", "alg": "EdDSA", "use": "sig" }
```

### Storage

- **Private key** — sealed in a secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault, K8s sealed-secrets). NEVER in env vars in plaintext, NEVER in source.
- **Public keys** — published at `https://<issuer>/.well-known/jwks.json`. Include current + previous `kid` for the lifetime of the longest-lived token.

### JWKS Endpoint

```python
# FastAPI side, just for completeness — usually the issuer publishes this.
@router.get("/.well-known/jwks.json")
async def jwks():
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": current_pub_jwk_x,
                "kid": "2026-04",
                "alg": "EdDSA",
                "use": "sig",
            },
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": prev_pub_jwk_x,
                "kid": "2026-03",
                "alg": "EdDSA",
                "use": "sig",
            },
        ]
    }
```

Cache headers: `Cache-Control: public, max-age=600` (10 min). Verifiers should refresh on `kid` miss.

### Rotation Cadence

- Quarterly under normal operation.
- Immediately on suspected compromise (or any access by someone who shouldn't have it).
- Process:
  1. Generate new keypair, give it `kid = YYYY-MM`.
  2. Publish in JWKS alongside current.
  3. Wait for verifier caches to refresh (10 min).
  4. Switch issuer to mint with new `kid`.
  5. Continue publishing old `kid` until longest token expires.
  6. Remove old key from JWKS + secrets manager.

## Mint (Go Issuer)

```go
package serviceauth

import (
    "crypto/ed25519"
    "time"

    "github.com/golang-jwt/jwt/v5"
    "github.com/google/uuid"
)

type Issuer struct {
    privKey ed25519.PrivateKey
    kid     string
    issuer  string
}

type ServiceClaims struct {
    Scope    []string `json:"scope"`
    TenantID string   `json:"tenant_id,omitempty"`
    jwt.RegisteredClaims
}

func New(privKey ed25519.PrivateKey, kid, issuer string) *Issuer {
    return &Issuer{privKey: privKey, kid: kid, issuer: issuer}
}

func (i *Issuer) Mint(audience, userID, tenantID string, scopes []string, ttl time.Duration) (string, error) {
    now := time.Now()
    claims := ServiceClaims{
        Scope:    scopes,
        TenantID: tenantID,
        RegisteredClaims: jwt.RegisteredClaims{
            Subject:   userID,
            Issuer:    i.issuer,
            Audience:  jwt.ClaimStrings{audience},
            IssuedAt:  jwt.NewNumericDate(now),
            ExpiresAt: jwt.NewNumericDate(now.Add(ttl)),
            NotBefore: jwt.NewNumericDate(now.Add(-30 * time.Second)),
            ID:        uuid.NewString(),
        },
    }
    tok := jwt.NewWithClaims(jwt.SigningMethodEdDSA, claims)
    tok.Header["kid"] = i.kid
    return tok.SignedString(i.privKey)
}
```

Usage:

```go
token, err := serviceTokens.Mint(
    "ai-adapter",      // aud
    user.ID,            // sub
    user.TenantID,      // optional
    []string{"ai:chat"},
    5 * time.Minute,    // ttl
)
req.Header.Set("Authorization", "Bearer " + token)
```

## Verify (Python Verifier)

```python
import asyncio
import time

import httpx
import jwt
from cachetools import TTLCache

JWKS_CACHE: TTLCache[str, dict] = TTLCache(maxsize=4, ttl=600)
JWKS_LOCK = asyncio.Lock()


async def get_jwks(issuer: str, force_refresh: bool = False) -> dict:
    if not force_refresh and issuer in JWKS_CACHE:
        return JWKS_CACHE[issuer]
    async with JWKS_LOCK:
        if not force_refresh and issuer in JWKS_CACHE:
            return JWKS_CACHE[issuer]
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{issuer}/.well-known/jwks.json")
            resp.raise_for_status()
        jwks = resp.json()
        JWKS_CACHE[issuer] = jwks
        return jwks


async def verify_service_token(
    token: str,
    *,
    expected_issuer: str,
    expected_audience: str,
) -> dict:
    """Verify a service-to-service JWT and return its claims.

    Raises jwt.InvalidTokenError on any failure. NEVER fall back to
    accepting an invalid token — log and reject.
    """
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    if not kid:
        raise jwt.InvalidTokenError("missing kid header")

    jwks = await get_jwks(expected_issuer)
    key_jwk = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    if key_jwk is None:
        # Rotation just happened? refresh once.
        jwks = await get_jwks(expected_issuer, force_refresh=True)
        key_jwk = next((k for k in jwks["keys"] if k["kid"] == kid), None)
        if key_jwk is None:
            raise jwt.InvalidTokenError(f"unknown kid {kid}")

    if key_jwk.get("alg") != "EdDSA":
        raise jwt.InvalidTokenError("unexpected key alg")

    public_key = jwt.algorithms.OKPAlgorithm.from_jwk(key_jwk)

    payload = jwt.decode(
        token,
        public_key,
        algorithms=["EdDSA"],
        audience=expected_audience,
        issuer=expected_issuer,
        leeway=30,                      # clock skew tolerance
        options={
            "require": ["sub", "iat", "exp", "aud", "iss", "nbf"],
            "verify_iat": True,
            "verify_exp": True,
            "verify_nbf": True,
            "verify_aud": True,
            "verify_iss": True,
        },
    )
    return payload
```

### FastAPI Integration

```python
from fastapi import Depends, Header, HTTPException

async def require_service_token(
    authorization: str = Header(...),
) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "invalid_authorization_header")
    token = authorization[7:]
    try:
        return await verify_service_token(
            token,
            expected_issuer="https://business-api.app.com",
            expected_audience="ai-adapter",
        )
    except jwt.InvalidTokenError as exc:
        # NEVER leak exc detail back to the caller — log it.
        logger.warning("service token rejected", extra={"error": str(exc)})
        raise HTTPException(401, "invalid_token") from exc


def require_scope(scope: str):
    async def _check(claims: dict = Depends(require_service_token)) -> dict:
        if scope not in claims.get("scope", []):
            raise HTTPException(403, "missing_scope")
        return claims
    return _check


@router.post("/conversations/{cid}/messages")
async def send_message(
    cid: str,
    body: SendMessageRequest,
    claims: dict = Depends(require_scope("ai:chat")),
):
    user_id = claims["sub"]
    # ... use user_id in the use case ...
```

## Replay Defense

Service JWTs with 5-minute TTL + clock skew leeway = effectively 6 minutes of replay window. For sensitive operations, also track `jti`:

```python
# In-memory or Redis blocklist of recently-seen jti values.
SEEN_JTI: TTLCache[str, bool] = TTLCache(maxsize=10_000, ttl=600)

async def verify_with_jti_check(token: str, ...) -> dict:
    payload = await verify_service_token(token, ...)
    jti = payload["jti"]
    if jti in SEEN_JTI:
        raise jwt.InvalidTokenError("replay")
    SEEN_JTI[jti] = True
    return payload
```

For multi-instance deployments, back this with Redis SET NX EX.

## Error Handling — Generic Outward, Specific in Logs

```python
# WRONG — leaks reason to attacker
raise HTTPException(401, f"jwt error: {exc}")

# RIGHT — opaque to client, full detail in logs.
logger.warning("service token rejected", extra={
    "error_class": type(exc).__name__,
    "error_message": str(exc),
    "request_id": request_id,
})
raise HTTPException(401, detail="invalid_token")
```

## Common JWT Mistakes

1. **Accepting `alg: none`** — library bug; switch.
2. **Trusting `alg` from token header** without algorithm allowlist — accept only specific algs you expect.
3. **Verifying signature but not `aud`/`iss`** — token from one service accepted by another.
4. **No `exp` enforcement** — token valid forever.
5. **No clock skew leeway** — minor NTP drift causes 5% failure rate.
6. **Storing JWT secret next to code** — first leaked secret.
7. **HS256 across teams** — shared secret = no trust boundary.
8. **JWT in URL** — leaks via referrer / logs / browser history.
9. **Long TTL "to reduce DB load"** — every minute = N more minutes a stolen token is valid.
10. **No JWKS caching** — verifier hits issuer on every request.

## Source Material

- *RFC 7519* — JWT.
- *RFC 7517* — JWK / JWKS.
- *RFC 8725* — JWT Best Current Practices (the must-read).
- *Auth0 — JWT Handbook* (PDF, free).
- *OWASP JWT Cheat Sheet*.
- `golang-jwt/jwt v5` (Go), `PyJWT` (Python), `jose` (Node) — current libs.
