---
name: auth-patterns
description: Design authentication and authorization for the project's stack — JWT vs server sessions, refresh-token rotation, OAuth 2.1 + PKCE, magic links, passkeys (WebAuthn), TOTP/2FA + backup codes, RBAC vs ABAC vs ReBAC, secure cookie flags, mobile token storage. Use when adding sign-in to a new app, designing the token model between RN client and Go backend, integrating an identity provider (Better-Auth/Clerk/Auth0/WorkOS), planning password reset flows, or hardening an existing auth surface.
tier: cross-cutting
domain: [backend, security]
last_reviewed: "2026-05-11"

---

# Auth Patterns — Sessions, Tokens, Identity

Practical authentication + authorization patterns for the project's stack: React Native client → Go+Fiber business backend → Python+FastAPI AI adapter → PostgreSQL. Designed around 2026-current best practices and the realistic threat model of a consumer mobile app.

## When to Use This Skill

- Adding sign-in to a new service.
- Choosing JWT vs opaque sessions for the RN ↔ Go ↔ FastAPI token chain.
- Designing refresh-token rotation + revocation.
- Integrating a hosted identity provider (Better-Auth, Clerk, Auth0, WorkOS).
- Implementing magic-link / OTP / passkey flows.
- Adding 2FA (TOTP + backup codes).
- Defining the permissions model — RBAC vs ABAC vs ReBAC.
- Designing the password reset flow (it's the most-broken thing in most apps).
- Hardening an existing auth surface — cookie flags, CSRF, header rules.

## Default Stack — One Sentence

**Server-side opaque sessions stored in Postgres + a short-lived signed access JWT for service-to-service hops.** The RN app holds the opaque session token in Keychain/Keystore. The Go backend exchanges that for a 5-minute service JWT when it needs to call the FastAPI AI adapter. No long-lived JWTs anywhere on the client.

This combines the revocability of sessions, the statelessness of JWTs where it matters (between services), and the robust mobile storage of native secure stores.

For the alternatives and when each is right, see [references/sessions-vs-jwt.md](references/sessions-vs-jwt.md).

## Core Decision: Session vs JWT

| Factor | Server sessions (opaque token) | JWT (signed claims) |
|---|---|---|
| Revocation | Instant — delete row | Hard — needs blocklist or short TTL |
| Read cost per request | DB lookup (or Redis) | Verify signature (cheap) |
| Cross-service auth | Need to share session store or call back | Self-contained, just verify |
| Mobile-friendly | Trivial (any opaque token) | Same |
| Browser-friendly | Cookies + CSRF protection | Cookies, header, or localStorage (each with risks) |
| Auditable | Easy — table of active sessions per user | Hard unless you track usage |
| Logout-from-all-devices | DELETE WHERE user_id = X | Only with a per-user revocation versioning trick |

**Use server sessions when**: single trust domain, mobile-first, need revocation, can afford one DB lookup per request (most apps).

**Use JWT when**: stateless service-to-service, multiple trust domains, third-party callers, or genuinely large scale where the DB lookup matters. Always with short TTL (≤15 min).

**Use both** (this project's pattern): opaque session token from client → backend; backend mints a short-lived JWT to call other internal services with the user identity baked in.

## The Token Model — This Project

```
┌────────────────────────────────────────────────────────────────────┐
│  React Native client                                               │
│   Stores: { session_token: "ses_…" }   in Keychain/Keystore        │
│   Sends:  Authorization: Bearer ses_…  on every API call           │
└─────────────────────────────────┬──────────────────────────────────┘
                                  │
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│  Go + Fiber business backend                                       │
│   Looks up session_token in Postgres → user_id, scopes, exp        │
│   For internal calls to FastAPI:                                   │
│     Mint short-lived service JWT                                   │
│     { sub: user_id, scope: ["ai:chat"], iat, exp: now+5m,          │
│       iss: "business-api", aud: "ai-adapter" }                     │
│     Sign with RS256 (or EdDSA) using rotating key                  │
└─────────────────────────────────┬──────────────────────────────────┘
                                  │  Authorization: Bearer <jwt>
                                  ▼
┌────────────────────────────────────────────────────────────────────┐
│  Python + FastAPI AI adapter                                       │
│   Verifies JWT signature against business-api's public key (JWKS)  │
│   Validates iss, aud, exp, iat, scope                              │
│   Trusts identity claims; logs user_id for the request             │
└────────────────────────────────────────────────────────────────────┘
```

For the JWT signing/verification implementation patterns + JWKS rotation, see [references/jwt-and-service-tokens.md](references/jwt-and-service-tokens.md).

## Refresh Tokens — Mobile Pattern

The RN app holds:

- **Access token** (the session token) — used in `Authorization` header. TTL: 1 hour.
- **Refresh token** — opaque, separate from the access token. TTL: 30 days. Single-use (rotation).

When access expires:

```
POST /auth/refresh
Authorization: Bearer <refresh_token>

→ 200 { access_token: "ses_new…", refresh_token: "ref_new…" }
  (server has invalidated the old refresh token)
```

Critical: **refresh tokens are single-use**. Each refresh issues a new pair AND revokes the old refresh token. If the old refresh token is reused (theft scenario), it's an alarm — revoke ALL of that user's sessions.

```sql
CREATE TABLE refresh_tokens (
    id           TEXT        PRIMARY KEY,         -- the opaque token value (hashed)
    user_id      TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id    TEXT        NOT NULL,            -- groups successive refreshes for theft detection
    used_at      TIMESTAMPTZ,                     -- NULL until first use
    expires_at   TIMESTAMPTZ NOT NULL,
    revoked_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_agent   TEXT,
    ip           INET
);

-- On refresh:
--   1. Look up provided token by hash.
--   2. If used_at IS NOT NULL → THEFT DETECTED. Revoke entire family.
--   3. Otherwise: mark this row used, insert a new row with same family_id.
```

## Password Authentication — If You Must

Most consumer apps in 2026 should NOT roll their own password storage. Use Better-Auth / Clerk / WorkOS / Auth0. If you must:

- **Hash with Argon2id**, parameters tuned to your hardware (~250ms / hash).
- Per-account rate limit on login + per-IP rate limit on the endpoint.
- Generic error messages: "invalid credentials" (don't say "user not found" vs "wrong password").
- Password reset via email magic link — not "security questions".
- HIBP (haveibeenpwned) k-anonymity check on signup + reset.
- Min length 12, no max length, no composition rules (NIST SP 800-63B).

```python
import argon2

ph = argon2.PasswordHasher(
    time_cost=3,        # iterations
    memory_cost=65536,  # 64MB
    parallelism=2,      # threads
    hash_len=32,
    salt_len=16,
)
hash_str = ph.hash(plaintext_password)  # store
ph.verify(hash_str, candidate_password)  # raises VerifyMismatchError on bad
```

Better: skip passwords, go magic-link or passkey first.

## Magic Links — Passwordless via Email

```
1. User enters email at sign-in.
2. Server generates one-time token, stores hashed:
     INSERT INTO magic_links (token_hash, user_id, expires_at, used_at)
     VALUES ($1, $2, NOW() + INTERVAL '15 min', NULL);
3. Server emails: https://app.com/magic?t=<token>
4. User clicks; server validates token (not expired, not used), marks used,
   issues session token, redirects to app.
```

Rules:

- TTL ≤ 15 minutes.
- Single-use (mark `used_at` on first redemption).
- Same-device check via cookie before sending the link, OR require the link to be opened on the same device that requested it (defeats most phishing).
- Rate-limit by IP and by email.
- Generic error if email doesn't exist (don't enumerate accounts).

## Passkeys (WebAuthn) — The Future Default

In 2026, passkeys are the right primary auth method for any app with iOS / Android / web clients. They're phishing-proof, no shared secret, sync via iCloud/Google Password Manager.

```
Registration:
  POST /auth/passkey/register/begin
  → server returns { challenge, rp_id, user.id, user.name, … }
  Client: navigator.credentials.create(...)
  POST /auth/passkey/register/finish  { credential, attestation }
  → server stores public key + credential id

Sign-in:
  POST /auth/passkey/authenticate/begin
  → server returns { challenge, allowCredentials? }
  Client: navigator.credentials.get(...)
  POST /auth/passkey/authenticate/finish  { assertion }
  → server verifies signature against stored pubkey, issues session token
```

Use `simplewebauthn` (Node), `webauthn-go`, or `py_webauthn` library — never roll your own. Provide a TOTP fallback for users who can't or won't use passkeys.

For the full registration + sign-in flow + database schema, see [references/passkeys-2fa.md](references/passkeys-2fa.md).

## TOTP 2FA — Standard Implementation

When passkeys aren't available:

- TOTP per RFC 6238 (Google Authenticator / Authy / Aegis compatible).
- Store the secret encrypted at rest (envelope encrypted with a KMS key, NOT plain-text in DB).
- Provision via QR code (`otpauth://totp/...`).
- 6-digit code, 30-second window, ±1 step tolerance.
- 10 single-use backup codes generated at enrollment, hashed with Argon2id.
- Re-prompt for password OR fresh-session (≤5 min) before disabling 2FA.
- Recovery flow: user must contact support if they lose phone + backup codes (do NOT make this easy — it's where attackers attack).

## OAuth 2.1 + PKCE — Third-Party Sign-In

For "Sign in with Google / Apple / GitHub":

- OAuth 2.1 (the 2024 consolidated spec — replaces the 2.0 + various extensions).
- PKCE on every flow, including confidential clients.
- Authorization Code flow only (Implicit and Resource Owner Password Credentials are deprecated).
- For RN: native browser-tab (Custom Tabs / SFSafariViewController), NOT WebView.
- `state` parameter to prevent CSRF — bind to current session.
- Validate `iss`, `aud`, `nonce` on the returned ID token.

```typescript
// RN with expo-auth-session (Expo) or react-native-app-auth (bare RN)
import { authorize } from 'react-native-app-auth';

const config = {
  issuer: 'https://accounts.google.com',
  clientId: '<google-oauth-client-id>',
  redirectUrl: 'com.app:/oauth/callback',
  scopes: ['openid', 'profile', 'email'],
  // PKCE is automatic in this lib.
};

const result = await authorize(config);
// result.idToken → POST to your backend → backend verifies + issues session token.
```

**Never** trust the access token from the client side. The backend re-verifies the ID token signature using the provider's JWKS, then issues YOUR session token.

## Authorization — Permissions Model

| Model | Use when | Avoid when |
|---|---|---|
| **RBAC** (role-based) | Few well-defined roles (admin, editor, viewer). Stable. | Permissions need per-resource granularity. |
| **ABAC** (attribute-based) | Decisions depend on attributes (resource owner, time of day, location). | Performance-critical paths (eval can be slow). |
| **ReBAC** (relationship-based, à la Zanzibar) | Sharing graphs (Google Drive, Slack channels). | Simple ownership models. |

For this project (lessons app), **RBAC + ownership check** is the right default:

```python
# Use case checks ownership inline:
async def update_lesson(self, input_: UpdateLessonInput, actor: Actor) -> ...:
    lesson = await self.lessons.get(input_.lesson_id)
    if lesson.author_id != actor.user_id and not actor.has_role("admin"):
        raise Forbidden("you do not own this lesson")
    ...
```

For sharing-heavy or org-with-teams cases, look at OpenFGA / SpiceDB (open-source Zanzibar implementations).

## Cookies — Secure Flags

If serving a web client too (admin UI, marketing site):

```
Set-Cookie: session=ses_…; Secure; HttpOnly; SameSite=Strict;
            Path=/; Domain=app.com; Max-Age=2592000
```

Required:

- `Secure` — HTTPS only.
- `HttpOnly` — JS cannot read; mitigates XSS-based theft.
- `SameSite=Strict` (or `Lax` if you need cross-site OAuth callbacks).
- `__Host-` prefix (`__Host-session`) for extra hardening — locks to current host + Path=/.
- Short Max-Age for session cookies; longer only for "remember me" with refresh-token rotation.

CSRF defense if SameSite=Lax: double-submit token pattern, OR Origin/Referer check, OR custom header (`X-Requested-With`).

## Mobile Token Storage — Native Secure Store

NEVER use AsyncStorage / MMKV for tokens. Always:

- **iOS**: Keychain Services (`react-native-keychain`).
- **Android**: Encrypted SharedPreferences or Keystore (`react-native-keychain` handles both).

```typescript
import * as Keychain from 'react-native-keychain';

await Keychain.setGenericPassword('session', sessionToken, {
  accessControl: Keychain.ACCESS_CONTROL.BIOMETRY_ANY_OR_DEVICE_PASSCODE,
  accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  storage: Keychain.STORAGE_TYPE.AES_GCM,
});

const creds = await Keychain.getGenericPassword();
if (creds) { const token = creds.password; }

await Keychain.resetGenericPassword();  // logout
```

Optional: gate retrieval behind biometrics for sensitive operations (transfers, password changes).

## Logout — All the Right Things

Client logout MUST:

1. Call `POST /auth/logout` with the session token — server revokes it server-side.
2. Wipe Keychain entries (`Keychain.resetGenericPassword()`).
3. Clear in-memory state (Zustand `useAuthStore.getState().reset()`).
4. Navigate to sign-in screen and reset navigation state.

Server logout MUST:

1. Mark `revoked_at = NOW()` on the session row (don't DELETE — keep audit trail).
2. Mark all refresh tokens in the same family as revoked.
3. Optionally NOTIFY a websocket channel so other devices learn this session is dead.

"Logout from all devices" =  `UPDATE sessions SET revoked_at = NOW() WHERE user_id = X AND revoked_at IS NULL;`

## Common Failure Modes

1. **Storing tokens in AsyncStorage / localStorage** — XSS or filesystem inspection trivially steals.
2. **Long-lived JWTs without revocation** — leaked = compromised forever.
3. **Refresh tokens that aren't single-use** — theft is undetectable.
4. **Generic `Authorization` header parsing** — rejecting tokens via 500 instead of 401.
5. **Account enumeration via signup / login / reset** — don't say "email exists" vs "wrong password".
6. **No rate limiting on login + reset endpoints** — credential stuffing has a field day.
7. **Magic-link tokens that aren't single-use** — replay attacks.
8. **Password reset that auto-logs-in without re-auth** — magic link goes to attacker's burner email post-takeover.
9. **TOTP secret stored plaintext** — DB breach reveals everyone's 2FA.
10. **No same-device check on magic links** — phishing trivial.
11. **OAuth without PKCE** — code interception attack.
12. **Mixed `aud`/`iss`** in service JWTs — token from one service accepted by another that wasn't supposed to.

## Threat Model — Mobile Consumer App

Realistic threats for THIS project (priority ordered):

1. **Stolen device, no biometric** → app session compromised. Mitigation: biometric gate on launch + on sensitive ops; idle-timeout logout; remote logout from web admin.
2. **Phishing** → user enters credentials on attacker's site. Mitigation: passkeys (phishing-proof), or magic-link with same-device check.
3. **API token leak (logs, metrics, screenshots)** → mass compromise. Mitigation: short-lived service JWTs, scrub `Authorization` from logs at the framework boundary.
4. **Malicious or compromised library on the client** → can read in-memory state. Mitigation: minimize dependencies, audit `npm audit` / `yarn audit` weekly, prefer first-party libs.
5. **Server-side breach (RDB dump)** → all hashes exposed. Mitigation: Argon2id with current params, encrypt TOTP secrets via KMS, hash refresh tokens before storing.
6. **Replay of intercepted requests** → action repeated. Mitigation: TLS everywhere, idempotency keys on mutations (api-design skill).

Things that are NOT realistic threats for a consumer mobile app (don't waste effort): nation-state attackers, RAM scraping, side-channel attacks. Spend effort on (1)-(6) first.

## Source Material

- *NIST SP 800-63B* (Digital Identity Guidelines, Authentication) — current 2024 update.
- *OWASP ASVS v4.0.3* — Application Security Verification Standard, Authentication chapter.
- *OWASP Cheat Sheet Series* — Authentication, Session Management, Password Storage, JWT.
- *RFC 9700* (OAuth 2.1) — March 2024 consolidated spec.
- *RFC 9525* (Service Identity in TLS).
- *RFC 6749 + 7636* — OAuth 2.0 + PKCE (foundational).
- *FIDO Alliance — Passkey Specifications*.
- Better-Auth, Clerk, WorkOS docs — for hosted-IdP integration patterns.
- *Securing Web APIs with OAuth 2.1* (Manning, 2025).
