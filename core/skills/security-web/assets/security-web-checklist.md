# Server-Side Security Pre-Production Checklist (OWASP Top-10 2025)

Run before promoting a backend service to production traffic. Each item is a concrete check; uncheck → block release.

Sections in 2025 ranking order.

## Broken Access Control (A01:2025) — still #1

- [ ] Every endpoint requires explicit auth check.
- [ ] Role/scope validated server-side, never trusted from client.
- [ ] Use cases assert resource ownership (or admin) before mutating.
- [ ] Multi-tenant: tenant_id filter in every query OR Postgres RLS active.
- [ ] IDOR test: enumerate IDs as user A, verify all reads/writes for user B return 403/404.
- [ ] Admin endpoints behind separate auth + IP allowlist.

## Security Misconfiguration (A02:2025) — ↑ from #5

- [ ] Security headers set on every response (HSTS, CSP, COOP, CORP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, X-Frame-Options).
- [ ] CORS allowlist; no `*` with credentials.
- [ ] No `DEBUG=True` in production.
- [ ] Stack traces never returned to clients.
- [ ] Default admin paths (`/admin`, `/swagger`) gated by auth + IP allowlist.
- [ ] Container: minimal base image, non-root user, read-only FS, dropped capabilities (`--cap-drop=ALL`).
- [ ] Kubernetes `securityContext`: `runAsNonRoot: true`, `readOnlyRootFilesystem: true`.
- [ ] Cloud IAM: principle of least privilege; no wildcard policies.
- [ ] No leftover dev tools / debug endpoints / test data in production.

## Software Supply Chain Failures (A03:2025) — renamed + expanded; ↑ from #6

- [ ] All lockfiles committed (`go.sum`, `uv.lock`, `yarn.lock`, etc.). CI uses `--frozen-lockfile`.
- [ ] CI runs `osv-scanner --recursive .` (cross-ecosystem) — fails on high.
- [ ] Plus per-ecosystem: `govulncheck` / `pip-audit` / `yarn npm audit`.
- [ ] No deps unpatched > 30 days for high-severity CVEs.
- [ ] No abandoned deps (last commit > 2 years).
- [ ] Dependency PRs reviewed (Dependabot / Renovate not auto-merged blindly).
- [ ] SBOM generated per release (CycloneDX or SPDX); attached to GitHub release.
- [ ] **GitHub Actions pinned to commit SHA, not tag** (e.g., `actions/checkout@8e5e7e5...`).
- [ ] **Short-lived OIDC tokens** for cloud auth in CI (no long-lived AWS/GCP keys in env).
- [ ] **MFA + IAM lockdown** on registry accounts (npm, PyPI, Docker Hub, Releases).
- [ ] **Separation of duties**: no single person writes code AND promotes to prod.
- [ ] **Two-person rule** for high-impact package publishes.
- [ ] Components only from official registries over HTTPS; no `curl | sh`.
- [ ] Private packages: scoped (`@app/*`) + private registry first in `.npmrc`.
- [ ] Container images scanned (Trivy/Grype) on every build.
- [ ] Staged rollouts (canary + automated rollback) for vendor-update consumption.

## Cryptographic Failures (A04:2025) — ↓ from #2

- [ ] TLS 1.2+ everywhere (TLS 1.3 preferred). HSTS header set.
- [ ] No mixed content (HTTP assets on HTTPS pages).
- [ ] PII encrypted at rest where applicable (KMS-encrypted columns / SQLCipher).
- [ ] Passwords hashed with Argon2id (≥250ms / hash on prod hardware).
- [ ] Refresh tokens stored as SHA-256 hash, not plain.
- [ ] No deprecated crypto (MD5, SHA-1, RC4, DES, 3DES, AES-ECB, RSA-1024).
- [ ] AEAD ciphers only (AES-GCM or ChaCha20-Poly1305).
- [ ] `crypto/rand` (Go) / `secrets` (Python) for any token generation.

## Injection (A05:2025) — ↓ from #3

- [ ] All SQL via parameterized queries / prepared statements / sqlc.
- [ ] All NoSQL via parameterized API; no string interpolation; no `$where` with user input.
- [ ] No `os.system` / `exec.Command(shell)` with user input concatenated.
- [ ] All XML parsing via `defusedxml` or equivalent (XXE off).
- [ ] All template rendering uses parameter binding, not string concat.
- [ ] Mass assignment blocked: explicit DTO at the boundary.
- [ ] GraphQL: depth + complexity limits set; field-level authz.
- [ ] **LLM prompt injection**: user input never substituted into system prompt; structured roles (system/user/assistant); output filtered for sensitive patterns.

## Insecure Design (A06:2025) — ↓ from #4 (now also covers SSRF)

- [ ] Server-authoritative checks for prices, quantities, totals, role flags.
- [ ] Idempotency keys on all mutations.
- [ ] Rate limiting on auth + sensitive endpoints (per-user AND per-IP).
- [ ] Failure modes for cache miss, DB timeout, third-party failure planned + tested.
- [ ] Privacy: collect minimum data, retain minimum time, delete on request.
- [ ] Threat model documented for new features.
- [ ] **SSRF** (was A10:2021, now under here): URL-fetching endpoints validate target host, block private IPs (10/8, 172.16/12, 192.168/16, 127/8, 169.254/16, fc00::/7, cloud metadata 169.254.169.254), re-resolve DNS, short timeouts (5s).

## Authentication Failures (A07:2025) — renamed (was "Identification & Authentication")

(Refer to `auth-patterns` checklist when present — full auth audit.)

- [ ] Passwords with Argon2id, no enumeration on login / reset.
- [ ] Rate-limit login (per-user + per-IP).
- [ ] Refresh-token rotation with theft detection.
- [ ] Session cookies: Secure + HttpOnly + SameSite.
- [ ] OAuth uses 2.1 + PKCE.
- [ ] Passkeys / WebAuthn offered where possible (preferred default 2026).

## Software or Data Integrity Failures (A08:2025) — same

- [ ] No insecure deserialization (`pickle`, native serialization) of untrusted data.
- [ ] CI/CD uses short-lived tokens (OIDC) — no long-lived secrets in env.
- [ ] GitHub Actions pinned to commit SHA, not tag.
- [ ] Code-signing verified for app artifacts.
- [ ] Webhooks: HMAC signature verification on every incoming call.
- [ ] No `eval` anywhere.

## Security Logging and Alerting Failures (A09:2025) — renamed (Monitoring → Alerting)

- [ ] Auth events logged with `request_id`, `user_id`, `event_type`.
- [ ] Authorization denials logged.
- [ ] No tokens / passwords / 2FA codes / full PII in logs (CWE-532).
- [ ] Sensitive headers (Authorization, Cookie) scrubbed in framework logs + APM.
- [ ] **Alerts** configured (the 2025 emphasis): auth-failure spikes, 403-spike, rate-limit triggers, outbound-traffic anomaly, new CVE matches your SBOM.
- [ ] **Each alert has a runbook** — page-without-runbook = alarm fatigue.
- [ ] Incident-response framework adopted (NIST 800-61 or equivalent).
- [ ] Log retention ≥ 90 days for security events.

## Mishandling of Exceptional Conditions (A10:2025) — NEW

- [ ] **Catch at source**, not just at top-level handler.
- [ ] **Resource cleanup** in `with` / `defer` / `finally` for ALL handles (file, DB, lock, GPU buffer).
- [ ] **Atomic transactions** — `UnitOfWork.run(...)` per `hexagonal-architecture`; no partial commit.
- [ ] **Fail-closed** in security code (auth check exception → deny, not allow).
- [ ] **Centralized error envelope** (RFC 9457 ProblemDetails per `api-design`); never construct error JSON ad-hoc per route.
- [ ] **No `str(exc)` in client-facing detail** (CWE-209: information leak).
- [ ] **Resource quotas** at framework: max body, max upload count, max concurrent connections, max LLM context tokens.
- [ ] **Unhappy-path tests**: pytest fixtures that throw mid-transaction / mid-stream / mid-write — assert state stays clean.
- [ ] **Global exception handler** as a safety net (sanitized response + full log + alert).

## CSRF (cookie-auth web clients only)

- [ ] `SameSite=Strict` (or `Lax` justified) on session cookies.
- [ ] Double-submit token OR custom-header check on state-changing endpoints.
- [ ] Origin/Referer validation on POST.

## Path Traversal / Open Redirect

- [ ] No user input concatenated into filesystem paths without `is_relative_to(base)` check.
- [ ] Open-redirect endpoints (`?return_to=`) restricted to allowlist (relative paths or specific hosts).
- [ ] OAuth callback `redirect_uri` allowlist enforced server-side.

## Secrets Management

- [ ] No secrets in source code, lockfiles, Dockerfiles, config files in repo.
- [ ] Secrets manager (AWS / GCP / Vault) used; app fetches at startup.
- [ ] Secrets rotated quarterly + on suspected leak.
- [ ] Access to secrets audited.
- [ ] No "shared utility token" — one secret per purpose.

## Network

- [ ] Outbound-traffic allowlist at network layer (egress firewall).
- [ ] Database not internet-reachable (private VPC).
- [ ] Internal services use mTLS or service-mesh equivalent.

## Operational

- [ ] Incident runbook documented (account takeover, leaked secret, suspected breach).
- [ ] `security@app.com` mailbox monitored; SLA documented.
- [ ] Pentest within last 12 months OR scoped engagement queued.
- [ ] On-call playbook covers security incidents (not just availability).

## Pre-Production Verification

- [ ] **OWASP ZAP** baseline scan against staging — no high.
- [ ] **`osv-scanner` recursive** — zero high.
- [ ] **`govulncheck ./...`** — clean.
- [ ] **Manual auth bypass attempt** — try to access endpoints without auth, with wrong scope, with expired token.
- [ ] **mitmproxy capture** of typical traffic — verify no PII in URLs, no tokens in logs, headers correct.
- [ ] **Dependency review** of any new direct deps in this release.
- [ ] **SBOM diff** vs previous release — flag major dependency changes.

---

Unchecked items block release. Document waivers in a tracking issue with an ETA.
