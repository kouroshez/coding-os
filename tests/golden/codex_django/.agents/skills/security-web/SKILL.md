---
name: security-web
tier: cross-cutting
domain: [security]
description: Server-side / API-side security per OWASP Top-10 (2025 release). Use when writing or reviewing backend code (Go+Fiber business core, Python+FastAPI AI adapter, Node) for broken access control, security misconfiguration, supply-chain failures, cryptographic mistakes, injection, insecure design, authentication failures, integrity failures, logging/alerting gaps, mishandling of exceptional conditions, plus SSRF/CSRF/XXE/SSTI/file uploads/secrets/headers (CSP/HSTS/COOP/COEP) and JWT pitfalls. Pairs with auth-patterns and security-mobile.
last_reviewed: "2026-08-12"

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

## OWASP API Security Top-10 (2023) — What the Web Top-10 Misses

The list above is authored for web apps; these are the API-shaped risks it does not number. Same authorization concern at three granularities: **object** (whose row?), **function** (whose endpoint?), **property** (whose field?).

| ID | Risk | Rule |
|---|---|---|
| API1 | **BOLA** — object level | Same control as A01 above: load by owner+ID, never by ID alone. |
| API3 | **BOPLA** — property level | Mass assignment is the write side; the **read** side is unguarded — build responses from an explicit serializer, never `return model.to_dict()`. A denylist (`exclude=[...]`) exposes the next migration's column by default. |
| API4 | **Unrestricted resource consumption** | Clamp every client-controlled size server-side: page size, batch/array length, `include` depth, filter fan-out. One request inside the rate limit still materializes the whole table. |
| API5 | **BFLA** — function level | Deny-by-default router + explicit public-route allowlist; assert per HTTP method. Never infer privilege from the path — `/api/admin/*` is a naming convention, not a control. |
| API9 | **Improper inventory** | Retire old `/v1`, staging hosts on public DNS, undocumented debug routes. An unowned endpoint skips every control added since it shipped. |
| API10 | **Unsafe consumption of APIs** | Validate and size-cap a partner response exactly like user input; explicit timeout; never blindly follow redirects — `307`/`308` replay your POST body to whatever host the partner names, and a custom auth header follows it (clients strip only `Authorization` cross-host). |

**BFLA is a routing property, not a decorator property.** Per-handler `@require_admin` fails open the day someone adds a sibling route and forgets it; a router that refuses to boot an unannotated route cannot.

## Cross-Cutting Misses

- **Session fixation**: regenerate the session ID on login *and* on every privilege change (role switch, step-up MFA); invalidate the user's other sessions on password change. Writing new claims into the existing session object is the bug.
- **Explicit `SameSite`**: set it on every auth cookie — never rely on the browser default. Chromium's implicit `Lax` still sends the cookie on a top-level cross-site POST for the first 2 minutes. On JSON endpoints also reject the CORS "simple" content types (`text/plain`, `application/x-www-form-urlencoded`, `multipart/form-data`) — a lenient body parser makes them form-CSRF-able with no preflight.
- **Webhook HMAC — three bugs that all pass tests**: verify over the *raw bytes* before any parse (mount the JSON body-parser after the route, not globally), compare constant-time, and reject a signed timestamp outside a ~5 min window (tolerance 0 = infinite replay).
- **Tenant context at every entry point, not just HTTP**: background jobs, queue consumers, cron, exports, search indexers, and cache/rate-limit keys each carry an explicit tenant ID; a job with no tenant context must fail, not run unscoped. A `TenantContext` populated only by HTTP middleware is empty in every worker.
- **Postgres RLS only bites if you let it**: connect as a role that neither owns the tables nor holds `BYPASSRLS`, declare `ALTER TABLE … FORCE ROW LEVEL SECURITY` (policies are skipped for the owner), and set the tenant GUC with `SET LOCAL` inside the transaction — a plain `SET` persists on the pooled connection and leaks into the next request.

## File Uploads — Trust the Bytes, Not the Claims

The multipart `Content-Type` and `filename` are attacker-supplied — Burp edits both while keeping the web-shell bytes. Every upload runs this pipeline server-side, in order; the skipped step is the exploit.

| # | Step | Rule |
|---|---|---|
| 1 | **Size** | Cap while streaming — at the proxy (`client_max_body_size`) AND in the handler as bytes arrive. A first check on `file.size` runs after the framework already buffered the body. Add a per-user total-storage quota. |
| 2 | **Type** | Sniff the leading bytes (libmagic / `puremagic` / `file-type` / Tika); accept only if the *detected* type is in a per-context allow-list, fail closed on detection error. Never branch on the part's `Content-Type` or on the extension. |
| 3 | **Name** | Derive the stored extension from the detected type. If the client's name is read at all: URL-decode + Unicode-normalize, take the last segment splitting on both `/` and `\`, reject NULs, control chars and >1 extension component, case-fold, allow-list only — deny-lists lose to `.phtml`, `.phar`, `x.php.jpg`, `x.pHp`, `x.php.`, `.htaccess`. |
| 4 | **Decode ceiling** | Set `Image.MAX_IMAGE_PIXELS` and catch `DecompressionBombError`; for archives cap member count and declared size *before* extracting **and** abort on a running byte ceiling *while* decompressing — the central directory's sizes are attacker-forged, so the pre-flight sum alone is bypassable. A 4 KB file that decodes to 40 GB passes every size check. |
| 5 | **Sanitize** | Re-encode images through an in-process decoder (Pillow / libvips / sharp) and persist only the re-emitted bytes — this strips EXIF and the polyglot tail. `verify()` / `identify()` validates, it does not sanitize: a valid `FF D8 FF` header with `<?php … ?>` appended passes step 2. |
| 6 | **Store** | Server-generated opaque name (UUID or content hash), outside the webroot, on a mount/prefix with script execution off, private bucket. The user's filename is a display column, never a path. |
| 7 | **Scan** | Hold in quarantine until AV (ClamAV / GuardDuty Malware Protection for S3) returns clean; fail closed on error or timeout. Never write to the live path and delete on a bad verdict — the file is served during the race. |
| 8 | **Serve** | Separate registrable domain (`…usercontent.com` — a sibling subdomain still receives the `.app.com` cookies) or a short-expiry signed storage URL, `Content-Disposition: attachment` (RFC 6266 `filename*=UTF-8''…`), server-chosen `Content-Type`, `nosniff` set on the object — the header middleware below covers the API origin only. Never reflect the uploaded type back. |

**Type-specific**

- **SVG / `.svgz` out of image allow-lists by default** — it is executable XML: `<script>`, `onload=`, `xlink:href` become stored XSS in the viewer's session. Product needs it? Rasterize server-side, or sanitize (DOMPurify SVG profile / `svg-sanitize`) and serve as `attachment` from the separate origin — never inline from the app origin.
- **Every XML-bearing upload** — SVG, `.xml`, and the OOXML zips (`.docx` / `.xlsx` / `.pptx`) — gets the XXE treatment above, with XInclude off too. XXE reaches you through a CV upload with no XML endpoint in the API.
- **Archives** — never `extractall()`. Apply the path-traversal check above per member, and reject absolute, symlink, hardlink and device entries (Zip Slip). Allow-listing `.docx` / `.xlsx` / `.pptx` opts you into this.
- **No shell-invoked converters** on untrusted input (`convert`, `ffmpeg`, `soffice`, `gs`) — ImageTragick executes through delegates and ImageMagick guesses format from content, so `identify` is not a type check. Use in-process libs; where ImageMagick is unavoidable, pin a `policy.xml` disabling the EPHEMERAL/URL/HTTPS/MVG/MSL/TEXT/SHOW coders and drop network egress.
- **Presigned direct-to-storage** — the API never sees the bytes, so steps 2–7 are silently skipped while the code still looks correct. Constrain the policy (`content-length-range`, fixed key prefix, exact content-type), land in a private quarantine prefix, and run the pipeline in a post-upload handler before the object becomes linkable.

**Client-side `accept=`, JS MIME and JS size checks are UX only** — replayed in curl they vanish. Never drop a server-side check because the UI has one.

**Tests** — none of these fail loudly; the upload returns 200 and only a replayed request shows the hole. Assert rejection *and* no persisted artifact for: a web shell renamed `.jpg` with a forged image `Content-Type` · `x.php.jpg` and `x.pHp` · `../` and `..\` names · a valid-header polyglot with a script tail · an SVG containing `<script>` · a `.docx` with an external-entity DTD · a zip-slip archive · a decompression bomb.

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

# GOOD — context-managed file, server-generated name, generic error
@app.post("/upload")
async def upload(file: UploadFile):
    dest = UPLOAD_DIR / uuid4().hex               # never the client's name (step 6)
    try:
        async with aiofiles.open(dest, "wb") as f:
            while chunk := await file.read(1 << 16):
                await f.write(chunk)
        await db.execute("INSERT INTO files (path) VALUES ($1)", dest.name)
    except DBError as exc:
        logger.error("file insert failed", extra={"path_hash": h(dest), "exc": str(exc)})
        await aiofiles.os.remove(dest)            # rollback the side effect
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
