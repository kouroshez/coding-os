---
name: security-web
description: Server-side / API-side security per OWASP Top-10 (2025 release). Use when writing or reviewing backend code (Go+Fiber business core, Python+FastAPI AI adapter, Node) for broken access control, security misconfiguration, supply-chain failures, cryptographic mistakes, injection, insecure design, authentication failures, integrity failures, logging/alerting gaps, mishandling of exceptional conditions, plus SSRF/CSRF/XXE/SSTI/secrets/headers (CSP/HSTS/COOP/COEP) and JWT pitfalls. Pairs with auth-patterns and security-mobile.
---

# Web / Backend Security — OWASP Top-10 (2025) + 2026 Practice

A practical playbook for hardening server-side code. Anchored on **OWASP Top-10 (2025)** — released November 2025, the current standard, replaces the 2021 list. Targets the project's stack — Go+Fiber business backend + Python+FastAPI AI adapter + PostgreSQL — with concrete code per category.

## When to Use This Skill

- Writing or reviewing any backend route / handler / middleware.
- Adding a new third-party SDK / dependency.
- Setting up TLS / HSTS / CSP headers.
- Auditing existing code for OWASP categories.
- Pre-launch security review.
- Investigating a security incident or pentest finding.

For client-side mobile hardening, see `security-mobile`. For auth specifically, see `auth-patterns`.

## OWASP Top-10 (2025) — Per Category

The full per-category walk-through with concrete defenses + code samples is in [references/owasp-top-10.md](references/owasp-top-10.md). The skim summary, in 2025 ranking order:

| ID | Category | 2021 → 2025 change | Top defense |
|---|---|---|---|
| A01 | **Broken Access Control** | same #1 | Default deny; use case asserts ownership; multi-tenant via Postgres RLS |
| A02 | **Security Misconfiguration** | ↑ from #5 to #2 | Security headers; no DEBUG in prod; default admin paths protected; least-privilege containers |
| A03 | **Software Supply Chain Failures** | renamed + expanded from "Vulnerable & Outdated Components" (was #6) | SBOM per release; pin commits not tags in CI; OIDC short-lived tokens; staged rollouts; MFA on registry/repo accounts |
| A04 | **Cryptographic Failures** | ↓ from #2 to #4 | TLS 1.2+; Argon2id for passwords; SHA-256 for refresh-token hashing; KMS-encrypted PII |
| A05 | **Injection** | ↓ from #3 to #5 | Parameterized queries everywhere; never concat user input into SQL/shell/templates |
| A06 | **Insecure Design** | ↓ from #4 to #6 | Server-authoritative checks; idempotency; rate limiting; threat modeling |
| A07 | **Authentication Failures** | renamed (was "Identification and Authentication Failures") | See `auth-patterns` skill |
| A08 | **Software or Data Integrity Failures** | same #8 | No insecure deserialization; signed updates; pinned action SHAs |
| A09 | **Security Logging and Alerting Failures** | renamed (was "Monitoring") | Auth events logged with request_id; alerts on anomalies; runbooks per alert |
| A10 | **Mishandling of Exceptional Conditions** | **NEW in 2025** | Catch at source; fail-closed transactions; centralized error handler; resource cleanup in `finally` |

**SSRF** (A10:2021) **dropped out** of the Top 10 — still a real risk, now treated under **Insecure Design (A06:2025)** for URL-fetching endpoints. The mitigations don't change; just the top-level numbering.

## Beyond OWASP Top-10 — Common Bonus Risks

- **SSRF** (now under A06): allowlist target hosts; block private IP ranges; re-resolve DNS; short timeouts. See [references/owasp-top-10.md](references/owasp-top-10.md) section A06 for full code.
- **CSRF** (cookie-auth web only): SameSite=Strict + double-submit token / custom header.
- **XXE**: defusedxml (Python); Go encoding/xml safe by default.
- **SSTI**: parameter binding only, never string-concat user input into templates.
- **Mass assignment**: explicit DTOs at the boundary; never `model.update(**body)`.
- **Path traversal**: `Path.resolve().is_relative_to(base)` check on every user-supplied path.
- **Open redirect**: allowlist destinations on `?return_to=` and OAuth callback URLs.

## Security Headers — JSON API Defaults

```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
X-Content-Type-Options:    nosniff
X-Frame-Options:           DENY
Referrer-Policy:           strict-origin-when-cross-origin
Permissions-Policy:        camera=(), microphone=(), geolocation=(), interest-cohort=()
Content-Security-Policy:   default-src 'none'; frame-ancestors 'none'
Cross-Origin-Opener-Policy:   same-origin
Cross-Origin-Resource-Policy: same-site
```

For HTML pages, replace CSP with a per-page policy using nonces (NOT `unsafe-inline`).

Set as middleware that runs on every response. Don't trust devs to remember per-route.

## CORS — Default Deny

```go
import "github.com/gofiber/fiber/v3/middleware/cors"

app.Use(cors.New(cors.Config{
    AllowOrigins:     []string{"https://app.com", "https://admin.app.com"},
    AllowCredentials: true,
    AllowMethods:     []string{"GET", "POST", "PATCH", "DELETE"},
    AllowHeaders:     []string{"Authorization", "Content-Type", "Idempotency-Key"},
    MaxAge:           600,
}))
```

NEVER `AllowOrigins: ["*"]` with `AllowCredentials: true`. The browser refuses, but the misconfig is a smell.

## Secrets Management

- **NEVER** in source code, Dockerfiles, env vars committed to repos.
- **Use a secrets manager**: AWS Secrets Manager / GCP Secret Manager / HashiCorp Vault / 1Password Connect.
- **App fetches secrets at startup** (or via short-lived token from secrets manager).
- **Rotate**: quarterly + immediately on any access by someone who shouldn't have it.
- **Audit access logs** of the secrets manager.
- **Don't proliferate** — one secret per purpose, no "shared utility token".

```python
async def lifespan(app):
    config = await load_config_with_secrets()  # at startup, not import-time
    app.state.config = config
    yield
```

## Supply-Chain Hardening

For the layered defense (lockfiles → vulnerability scanning → dep review → minimization → confusion defense → provenance/sigstore → CI hardening → runtime detection → SBOM), see [references/supply-chain.md](references/supply-chain.md).

Mandatory minimum:

- All lockfiles committed.
- CI runs `osv-scanner --recursive .` — fails on high.
- GitHub Actions pinned to commit SHA, not tag.
- Short-lived OIDC tokens for cloud auth.
- SBOM per release (CycloneDX or SPDX).

## Dependency Vulnerability Process

```bash
# Go
govulncheck ./...

# Python
pip-audit                # PyPI vulnerabilities
# OR
safety check

# Node
yarn npm audit --severity high --recursive

# Cross-platform (preferred — single tool, all ecosystems via OSV database)
osv-scanner --recursive .
```

CI: fail the build on `severity >= high`. Ignore via explicit allowlist with expiration date.

## Incident Response

- **Logs centralized** + retained 90+ days.
- **Runbook** for "user reports account takeover" / "leaked secret detected" / "PII data leak suspected".
- **Disclosure channel** (`security@app.com`) with 48-hour SLA.
- **Rotate** affected secrets immediately on detection.
- **Notify** affected users per regulatory requirements (GDPR: 72h to authority; CPRA: prompt user notice).

## A10:2025 Mishandling of Exceptional Conditions — The New One

NEW in 2025. Most teams have never explicitly defended against this category. Three failure modes:

1. **Resource leaks** on exception → file uploads don't close handles, eventually OOM the process.
2. **Information leak** in error responses → DB error message exposes table names → SQLi reconnaissance.
3. **Partial commits** on transaction failure → attacker exploits the half-applied state (drained accounts, duplicate transfers).

**Defenses**:

- **Catch at source, not at the top-level handler.** A 200-line `try/except Exception` in the route is a smell.
- **`with` / `defer` / `finally` for ALL resource acquisition** — file handles, DB connections, locks, GPU/ML buffers.
- **Atomic transaction OR full rollback** — `UnitOfWork.run(...)` per `hexagonal-architecture` skill. Never partial commit.
- **Centralized error envelope** — RFC 9457 (per `api-design`) — DON'T construct error JSON ad-hoc per route.
- **Fail-closed in security-relevant code**: if auth check throws, return 401 — never default to "allow because exception".
- **Resource quotas** at the framework: max body size, max upload count, max concurrent connections per user.
- **Test the unhappy path**: pytest fixtures that throw mid-transaction, mid-stream, mid-write — assert state stays clean.

```python
# BAD — leaks file handle on exception, leaks SQL detail on response
@app.post("/upload")
async def upload(file: UploadFile):
    f = open("/var/uploads/" + file.filename, "wb")
    while chunk := await file.read(1 << 16):
        f.write(chunk)
    await db.execute("INSERT INTO files (path) VALUES ($1)", file.filename)
    f.close()

# GOOD — context-managed file, validated path, generic error
@app.post("/upload")
async def upload(file: UploadFile):
    safe = safe_upload_path(file.filename)        # raises on traversal
    try:
        async with aiofiles.open(safe, "wb") as f:
            while chunk := await file.read(1 << 16):
                await f.write(chunk)
        await db.execute("INSERT INTO files (path) VALUES ($1)", safe.name)
    except DBError as exc:
        logger.error("file insert failed", extra={"path_hash": h(safe), "exc": str(exc)})
        await aiofiles.os.remove(safe)            # rollback the side effect
        raise HTTPException(500, detail="upload failed") from exc
```

## Common Backend-Security Mistakes

1. **Trusting client-side data** — client is hostile by default.
2. **No input validation** — every external string is potentially malicious.
3. **String interpolation in SQL** — SQLi waiting to happen.
4. **`eval` / `exec` / dynamic code** — almost never the right answer.
5. **Sensitive data in logs / error responses** — incident waiting to happen.
6. **Rate limit per IP only** — IPv6 makes this useless; rate limit per user too.
7. **No CSRF defense on cookie auth** — drive-by sites take action as the user.
8. **CORS `*` with credentials** — browser blocks, but the intent leaked.
9. **Long-lived secrets in env vars** — first leak forever.
10. **No security headers** — XSS / clickjacking / MIME-sniffing trivial.
11. **Outdated dependencies** — known CVEs unfixed for months.
12. **No SSRF protection** on URL-fetching endpoints.
13. **Mass assignment** without DTO — privilege escalation via crafted body.
14. **Path traversal** in upload / download endpoints.
15. **Open redirect** in OAuth callback / login flow.

## Pre-Production Checklist

See [assets/security-web-checklist.md](assets/security-web-checklist.md) — gate runs through every category with concrete checks. Unchecked items block release.

## Source Material

- *OWASP Top-10 (2025)*: <https://owasp.org/Top10/2025/> (released November 2025; current standard).
- *OWASP API Security Top-10 (2023)*: <https://owasp.org/API-Security/> (separate list specifically for APIs).
- *OWASP ASVS v5.0* (Application Security Verification Standard, 2024+).
- *OWASP Cheat Sheet Series*: <https://cheatsheetseries.owasp.org/>
- *NIST SP 800-218* — Secure Software Development Framework.
- *NIST SP 800-61* — Computer Security Incident Handling Guide (for A09 alerting / runbooks).
- *PortSwigger Web Security Academy* — best free training.
- *CISA Known Exploited Vulnerabilities catalog* — for prioritizing patch work.
