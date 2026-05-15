# Auth Pre-Launch Checklist

Run before exposing a sign-in screen to the public. Each item maps to the auth-patterns skill or its references.

## Token Model

- [ ] **Server-side opaque session** is the client-facing primary token.
- [ ] **Session token format**: prefixed (`ses_…`), ≥ 192 bits of entropy.
- [ ] **Session DB stores token hash** (SHA-256), not raw token.
- [ ] **Sessions table** has `revoked_at` column (soft-revoke, not delete).
- [ ] **Per-session metadata**: user_agent, ip, last_seen_at, expires_at.
- [ ] **Service-to-service** uses short-lived JWT (5–15 min), NOT the user session.
- [ ] **JWT alg**: EdDSA / ES256 / RS256 only. `alg: none` rejected. `aud`/`iss`/`exp`/`nbf` always verified.
- [ ] **Key rotation**: quarterly + on-demand. JWKS publishes current + previous key.

## Session Lifecycle

- [ ] **Refresh tokens are single-use** with rotation.
- [ ] **Refresh family** tracked — reuse of consumed refresh token revokes entire family.
- [ ] **Logout-from-all-devices** endpoint exists and works.
- [ ] **Idle timeout** enforced (e.g., 30 days max session).
- [ ] **Step-up `fresh_until`** marker for sensitive operations.

## Mobile Storage

- [ ] **Tokens in Keychain (iOS) / Keystore (Android)** — never AsyncStorage / MMKV / files.
- [ ] **Biometric gate** (BiometryAny + DevicePasscode fallback) on token retrieval.
- [ ] **Logout wipes Keychain** entries fully.
- [ ] **In-memory state cleared** on logout (Zustand reset, etc.).

## Sign-In Methods

- [ ] **Passkeys (WebAuthn)** primary path on iOS 16+ / Android 14+.
- [ ] **Magic link** as the universal fallback.
- [ ] **OAuth (Google/Apple/etc.)** uses Authorization Code + PKCE in a native browser tab (NOT WebView).
- [ ] **Password authentication** disabled by default. If enabled: Argon2id, NIST-aligned policy, HIBP check, generic errors.
- [ ] **Apple Sign In** offered on iOS if any other social provider is offered (App Store rule).

## 2FA

- [ ] **TOTP** offered as fallback to passkeys.
- [ ] **TOTP secret encrypted at rest** via KMS envelope encryption.
- [ ] **Backup codes** generated at enrollment (10 codes, single-use, Argon2id-hashed).
- [ ] **Account recovery** has out-of-band identity verification + cooling-off period.
- [ ] **Disabling 2FA** requires fresh-session + email confirmation.

## OAuth (if used)

- [ ] **PKCE on all flows**.
- [ ] **`state` parameter** bound to current session, validated on callback.
- [ ] **`nonce` validated** in returned ID token.
- [ ] **ID token signature** verified against provider JWKS server-side.
- [ ] **Email verification status** from provider checked (`email_verified`).
- [ ] **Native browser tab** (Custom Tabs / SFSafariViewController), not WebView.

## Magic Links

- [ ] **TTL ≤ 15 minutes**.
- [ ] **Single-use** — `used_at` marked on first redemption.
- [ ] **Same-device check** OR cookie before sending.
- [ ] **Rate limit** by IP and by email.
- [ ] **Generic response** on unknown email (no enumeration).

## Cookies (web client, if any)

- [ ] **`Secure; HttpOnly; SameSite=Strict`** on session cookie.
- [ ] **`__Host-` prefix** on cookie name.
- [ ] **Short Max-Age** for session cookie.
- [ ] **CSRF defense**: SameSite=Strict OR double-submit token.
- [ ] **`Vary: Cookie`** on cached pages that change with auth.

## Authorization

- [ ] **Permissions model documented** (RBAC / ABAC / ReBAC).
- [ ] **Authorization checked at the use case**, not the controller.
- [ ] **Owner-or-admin pattern** for resource access.
- [ ] **Default deny** — unspecified ops are forbidden.
- [ ] **Multi-tenant**: tenant_id enforced via RLS or explicit query filter.

## Hardening

- [ ] **Password / login / reset endpoints rate limited** (per-IP and per-account).
- [ ] **Account lockout** after N failed attempts in M minutes.
- [ ] **No account enumeration** anywhere — uniform responses.
- [ ] **No PII in URLs** (no email in query params).
- [ ] **No tokens in URLs** (use Authorization header).
- [ ] **TLS-only**, HSTS enabled.
- [ ] **Authorization header NOT logged** in any access log or APM tool.
- [ ] **Response error envelopes** never echo `str(exception)`.
- [ ] **Brute-force-resistant secrets**: `secrets.token_urlsafe(32)`, never `random.choice(...)`.

## Operational

- [ ] **Sessions table monitored**: graph of active session count, revocations/min.
- [ ] **Failed-auth metrics**: dashboards + alert on spike.
- [ ] **Refresh token reuse detection**: any `theft_detected` event pages on-call.
- [ ] **Periodic session cleanup**: cron deletes sessions revoked > 30 days ago.
- [ ] **Per-endpoint rate limit headers** sent to clients (`RateLimit-*`).
- [ ] **Audit log**: every auth event (login, logout, 2FA enable/disable, passkey add/remove, password change) recorded immutably.

## Tests

- [ ] **Unit**: token verification — every algorithm allowlist case.
- [ ] **Unit**: session revocation flow.
- [ ] **Unit**: refresh-token rotation + reuse detection.
- [ ] **Integration**: full sign-in / sign-out / refresh / step-up.
- [ ] **Adversarial**: replay attempt, expired token, wrong audience, alg confusion (HS vs RS), `alg: none`.

## Documentation

- [ ] **Sign-in flow diagrammed** for new contributors.
- [ ] **Token format / TTL / rotation policy** documented.
- [ ] **Recovery procedures** documented (for support team).
- [ ] **Incident playbook**: "compromised user", "leaked signing key", "all sessions invalidated".

---

If any box is unchecked, document the reason in a tracking issue with an ETA. Auth bugs are not "technical debt" — they're security incidents waiting.
