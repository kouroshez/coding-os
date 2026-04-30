<!-- domain:SECURITY | layer:checklist | ssot:ref | updated:2026-01-01 -->
# Security Review — <Feature / Change Title>

Purpose: Per-change security checklist mapped to OWASP Top-10 (2025) + project-specific risks. Filed alongside the PR/ADR for traceability.
Read when: Before merging a change that touches auth, data exposure, external services, file upload, secret handling, or trust boundaries.
Skip when: Pure refactor with no behavior change AND no new external surface area.
Read next: [security-review.md](../../playbooks/security-review.md), [error-format.md](../../api-contracts/error-format.md)

> Nav: [Templates Index](../00-index.md)

---

## Change Context

- **PR / ADR:** <link>
- **Author:** @user
- **Date:** YYYY-MM-DD
- **Reviewer:** @user
- **Scope:** <one sentence: what's changing, what's the trust boundary>

## Threat Surface (fill in only what applies)

| Surface | Touched? | Notes |
|---|---|---|
| New endpoint or RPC | ☐ | <which> |
| Auth flow / session | ☐ | <which> |
| Authorization / permission rules | ☐ | <which> |
| User input (form / API / file upload) | ☐ | <which fields> |
| External service call | ☐ | <which provider> |
| Secret / credential handling | ☐ | <which> |
| Schema migration | ☐ | <table / column> |
| Logging / telemetry | ☐ | <what gets logged> |
| Crypto operation | ☐ | <hash / encrypt / sign> |
| Background job / scheduled task | ☐ | <which> |

## Checklist (OWASP-aligned)

### A01 — Broken Access Control
- [ ] Every new endpoint verifies authentication.
- [ ] Every new endpoint verifies the caller is authorized for the target resource (not just authenticated).
- [ ] Permission rules trace to the project Permission Matrix (link).
- [ ] No IDOR: object IDs are scoped to the caller (no `/users/{id}` without ownership check).
- [ ] Server-side rules duplicate any client-side rules — never trust the UI.

### A02 — Cryptographic Failures
- [ ] Passwords hashed with bcrypt/argon2/scrypt (never MD5/SHA1).
- [ ] Tokens signed with a key stored outside source.
- [ ] TLS used for every external call (no plain HTTP).
- [ ] Sensitive data not stored in logs / error messages.

### A03 — Injection
- [ ] DB access uses parameterized queries / ORM (no string concatenation).
- [ ] HTML output is escaped at render time.
- [ ] Shell commands use argument arrays, not interpolated strings.
- [ ] Template injection not possible (Jinja autoescape on, etc.).

### A04 — Insecure Design
- [ ] State machine covers expired/revoked/abuse states, not just happy path.
- [ ] Rate limits on enumeration-prone endpoints (login, password reset, token redemption).
- [ ] Multi-step flows resistant to step skipping or replay.

### A05 — Security Misconfiguration
- [ ] No default credentials.
- [ ] Stack traces / ORM errors not returned to users.
- [ ] CORS list explicit (no `*` for credentialed origins).
- [ ] Security headers set: HSTS, CSP (or framework default), X-Frame-Options or `frame-ancestors`.
- [ ] Debug mode off in non-dev environments.

### A06 — Vulnerable & Outdated Components
- [ ] No new dependencies added without checking advisories.
- [ ] Existing deps have a known patch path if a CVE drops.

### A07 — Identification & Authentication Failures
- [ ] Sessions invalidated on password change.
- [ ] Brute-force protected (rate limit / captcha / lockout).
- [ ] Password reset tokens single-use, short TTL (≤30 min).
- [ ] No password length cap below 64 chars.

### A08 — Software & Data Integrity
- [ ] No deserialization of untrusted data without a strict allow-list.
- [ ] Webhook payloads verified by signature, not just shared secret.
- [ ] CI artifacts pinned by hash, not floating tags.

### A09 — Logging & Monitoring
- [ ] Failed authentication logged with caller IP + identifier.
- [ ] Privilege changes logged.
- [ ] Logs do not contain passwords, tokens, full PANs, or full PII.
- [ ] Alerts wired for anomaly thresholds (link to runbook).

### A10 — Server-Side Request Forgery (SSRF)
- [ ] Outbound URL inputs validated against an allow-list or DNS rebound on each fetch.
- [ ] Cloud metadata endpoints (`169.254.169.254`) blocked.
- [ ] Internal-only services not reachable from user-controlled inputs.

### Project-Specific
- [ ] Doc anchor recorded (Rule 0) — code traces to a spec.
- [ ] Permission Matrix updated if new role/action introduced.
- [ ] Test added covering the negative case (unauthorized user blocked).
- [ ] Threat-model entry added to [risk-register.md](../risk-register.md) if a new risk class.

## Reviewer Sign-off

- [ ] Security checklist complete or every unchecked box has an explicit waiver below.
- [ ] PR description names this review.

**Waivers (with justification):**
- <item> — <why this is safe to skip>

---

> Skipped boxes are accepted risk. The reviewer owns the waiver and the runbook for it.
