# OWASP Top-10 (2025) — Per-Category Defenses

The current top-10 — released **November 2025**, replaces the 2021 list. Each category in 2025 ranking order, with concrete defenses for THIS project's stack (Go+Fiber + Python+FastAPI + PostgreSQL + React Native).

## What Changed vs 2021

| 2021 | 2025 | Change |
|---|---|---|
| A01 Broken Access Control | A01 Broken Access Control | same |
| A02 Cryptographic Failures | **A04** Cryptographic Failures | ↓ 2 places |
| A03 Injection | **A05** Injection | ↓ 2 places |
| A04 Insecure Design | **A06** Insecure Design | ↓ 2 places |
| A05 Security Misconfiguration | **A02** Security Misconfiguration | **↑↑ 3 places** |
| A06 Vulnerable & Outdated Components | **A03** Software Supply Chain Failures | **renamed + scope expanded**; ↑ 3 places |
| A07 Identification & Auth Failures | A07 Authentication Failures | renamed |
| A08 Software & Data Integrity Failures | A08 Software or Data Integrity Failures | same |
| A09 Logging & Monitoring Failures | A09 Logging & **Alerting** Failures | renamed (Monitoring → Alerting) |
| A10 SSRF | — | **dropped**; subsumed under Insecure Design (A06) |
| — | **A10 Mishandling of Exceptional Conditions** | **NEW** |

Three big shifts:

1. **Misconfiguration jumped to #2.** Default credentials, missing headers, exposed admin paths are everywhere.
2. **Supply chain renamed + expanded.** No longer just "outdated libs" — full chain: build pipeline, registry credentials, malicious packages (Shai-Hulud npm worm, Bybit $1.5B wallet attack — both 2025).
3. **NEW: Mishandling of Exceptional Conditions.** Resource leaks, partial commits, information leaks via error messages.

---

## A01:2025 — Broken Access Control (still #1)

Authorization checks missing, wrong, or bypassable.

**Defenses**:

- **Default deny**. Every endpoint requires explicit auth + scope check via middleware that's hard to forget.
- **Use case checks ownership**. The `update_lesson` use case fetches the lesson, asserts `lesson.author_id == actor.user_id` or `actor.has_role('admin')`, then mutates.
- **Never trust client-supplied authorization** (`?user_id=X`, hidden form fields). Authorization derives from the validated session token.
- **Multi-tenant: tenant ID filter EVERY query**. Use Postgres RLS as a safety net.
- **IDOR (Insecure Direct Object Reference) test**: enumerate IDs as user A; verify all reads/writes return 403/404 for objects owned by user B.

```go
// CORRECT — use case asserts ownership.
func (uc *UpdateLesson) Execute(ctx context.Context, in UpdateLessonInput, actor Actor) error {
    lesson, err := uc.lessons.Get(ctx, in.LessonID)
    if err != nil { return err }
    if lesson.AuthorID != actor.UserID && !actor.HasRole("admin") {
        return Forbidden("not your lesson")
    }
    return uc.lessons.Update(ctx, lesson.WithTitle(in.NewTitle))
}
```

```python
# CORRECT — same pattern in Python use case
async def execute(self, input_: UpdateLessonInput, actor: Actor) -> None:
    lesson = await self.lessons.get(input_.lesson_id)
    if lesson.author_id != actor.user_id and not actor.has_role("admin"):
        raise Forbidden("not your lesson")
    ...
```

---

## A02:2025 — Security Misconfiguration (↑ from #5 to #2)

Default credentials, debug pages exposed, verbose errors, missing security headers, container/cloud misconfig. The 2025 jump reflects how often this is the actual breach root cause across CISA / Verizon DBIR datasets.

**Headers** (set on every response — middleware):

```go
func SecurityHeaders(c fiber.Ctx) error {
    c.Set("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
    c.Set("X-Content-Type-Options",    "nosniff")
    c.Set("X-Frame-Options",           "DENY")
    c.Set("Referrer-Policy",           "strict-origin-when-cross-origin")
    c.Set("Permissions-Policy",        "camera=(), microphone=(), geolocation=()")
    c.Set("Content-Security-Policy",   "default-src 'none'; frame-ancestors 'none'")
    c.Set("Cross-Origin-Opener-Policy",   "same-origin")
    c.Set("Cross-Origin-Resource-Policy", "same-site")
    return c.Next()
}
```

For pure JSON APIs, CSP `default-src 'none'` is fine. For HTML pages, configure CSP per page (avoid `unsafe-inline`; use nonces).

**Other**:

- No `DEBUG=True` in production (Django/FastAPI).
- Stack traces NEVER returned to clients.
- Default admin paths (`/admin`, `/swagger`) protected by auth + IP allowlist + visibility hidden from public DNS.
- Container/host config: minimal base image, non-root user, read-only filesystem, drop capabilities (`--cap-drop=ALL`).
- Cloud: principle of least privilege on IAM. Audit S3 bucket policies. No public exposure unless intentional.
- Kubernetes: `securityContext` set on every workload (`runAsNonRoot: true`, `readOnlyRootFilesystem: true`, drop CAP_NET_RAW).
- CORS allowlist (NEVER `*` with credentials).

---

## A03:2025 — Software Supply Chain Failures (renamed + expanded; ↑ from #6 to #3)

The biggest scope change in the 2025 list. A06:2021 was "Vulnerable & Outdated Components" — narrow. A03:2025 covers the entire supply chain: malicious packages, compromised maintainers, build-pipeline tampering, registry account hijacks, developer-targeted attacks.

**2025 reference incidents** (cited in OWASP):

- **Shai-Hulud (2025)** — first self-propagating npm worm; harvested + exfiltrated tokens, auto-published malicious versions.
- **Bybit (2025)** — wallet supply-chain attack; $1.5 billion stolen.
- **SolarWinds (2019)** — vendor update compromise; ~18,000 organizations.
- **Log4Shell** (CVE-2021-44228) and **Struts 2 RCE** (CVE-2017-5638) — long-tail of unpatched deps.

**Defenses**:

### Patch Management + Inventory

- **SBOM per release** (CycloneDX or SPDX): `syft scan ./backend -o cyclonedx-json`. Attach to GitHub releases.
- **Continuous monitoring**: subscribe to GitHub Security Advisories, OSV (`osv-scanner`), CVE feeds.
- **Track transitive deps** via OWASP Dependency-Track / Dependency-Check / retire.js.
- **Lockfiles committed** (`go.sum`, `uv.lock`, `yarn.lock`, etc.). CI uses `--frozen-lockfile`.

### CI Vulnerability Scanning

```yaml
- run: pipx install osv-scanner && osv-scanner --recursive .   # cross-ecosystem
- run: govulncheck ./...                                         # Go-specific
- run: pipx install pip-audit && pip-audit --strict             # Python
- run: cd mobile && yarn npm audit --severity high --recursive  # Node
```

Fail the build on `severity >= high`. Allowlist exceptions with explicit expiration dates.

### Trusted Sources Only

- Components ONLY from official registries over HTTPS. Never `curl | sh` an unverified script.
- Verify package provenance where available (npm `--provenance`, sigstore for Go modules + container images).
- Prefer first-party / well-known maintainers; avoid abandoned packages (last commit > 2 years).

### Build Pipeline Hardening

- **Short-lived OIDC tokens** for cloud auth in CI (no long-lived AWS/GCP keys in env).
- **Pin GitHub Actions to commit SHA**, not tag (`uses: actions/checkout@8e5e7e5...` not `@v4`). Tag re-pointing is a real attack.
- **Two-person rule** for publishing high-impact packages.
- **Separate publish-only credentials** (no PR-merge perms).
- **Separation of duties**: no single person writes code AND promotes to production.
- **MFA + IAM lockdown** on registry accounts (npm, PyPI, Docker Hub, GitHub Releases), developer workstations, build servers.
- **Minimal base images** + scan with Trivy / Grype on every build.

### Risk-Based Patching

- Don't wait for "monthly patch day" on critical CVEs — fix in hours.
- Test library compatibility before deploying.
- Consider **virtual patches** (WAF rule, runtime allowlist) for unmaintained components you can't replace.

### Dependency Confusion Defense (private packages)

- Scoped packages: `@app/internal-utils`. Register the scope on npmjs.org even if you never publish, claiming it.
- Private registry FIRST in `.npmrc`:
  ```
  registry=https://registry.npmjs.org
  @app:registry=https://npm.internal.app.com
  ```
- Verify in build: assert `@app/*` resolves from your private registry, not public.

### Staged Rollouts

If a vendor pushes a tainted update, you want < 1% of fleet exposed before noticing. Canary deploys + automated rollback.

---

## A04:2025 — Cryptographic Failures (↓ from #2 to #4)

Sensitive data exposed at rest or in transit. Position dropped because TLS adoption is now near-universal — but the failures that remain are concentrated in stored-data crypto.

**Defenses**:

- **TLS 1.2+ everywhere** — TLS 1.3 preferred. Strong ciphers. HSTS header. No mixed content.
- **Encrypt at rest** for sensitive PII (SQLCipher for SQLite; pgcrypto / KMS-encrypted columns for Postgres).
- **Hashing**: passwords via Argon2id (≥250ms hash time); refresh tokens via SHA-256 (one-way; lookup by hash).
- **No plain-text secrets in logs / error responses / commit history**.
- **Random**: `crypto/rand` (Go), `secrets` (Python). NEVER `math/rand` or `random` for tokens.

```go
import "crypto/rand"
b := make([]byte, 32)
_, _ = rand.Read(b)
```

```python
import secrets
token = secrets.token_urlsafe(32)
```

- **No deprecated crypto**: MD5, SHA-1, RC4, DES, 3DES, AES-ECB, RSA-1024.
- **Modern AEAD**: AES-GCM or ChaCha20-Poly1305. Never raw AES-CBC without HMAC.
- **Key derivation**: Argon2id, scrypt, or PBKDF2 (≥600k iterations in 2026).

---

## A05:2025 — Injection (↓ from #3 to #5)

SQL, NoSQL, OS, LDAP, ORM injection. Position dropped because parameterized-query frameworks became the default — but template injection, NoSQL injection, and command injection still occur.

```python
# CORRECT — parameterized
await db.fetch_one("SELECT * FROM users WHERE email = $1", email)

# WRONG — string interpolation, SQLi
await db.fetch_one(f"SELECT * FROM users WHERE email = '{email}'")
```

```go
// CORRECT
row := db.QueryRow(ctx, "SELECT id FROM users WHERE email = $1", email)

// WRONG
row := db.QueryRow(ctx, fmt.Sprintf("SELECT id FROM users WHERE email = '%s'", email))
```

OS command execution: avoid entirely. If you must, `exec.Command` with arguments as separate strings (NEVER concat into a shell). Set `Cmd.Env` explicitly; don't inherit.

**Less-obvious injection types in 2026**:

- **NoSQL (MongoDB)**: `{ $where: req.body.query }` → JS code execution. Use parameterized find / Mongoose schema validation.
- **GraphQL**: depth + complexity limits to prevent denial-of-service via nested queries; field-level authorization.
- **LLM prompt injection**: untrusted text concatenated into a prompt sent to an LLM → can override system instructions. For your FastAPI AI adapter: treat user input as data, not part of the system prompt; use structured roles (system/user/assistant); never let a user provide the system prompt.

---

## A06:2025 — Insecure Design (↓ from #4 to #6, **now also covers SSRF**)

Architectural mistakes. Threat-modeling output is the input here. **SSRF was its own category in 2021 — in 2025 it's grouped under Insecure Design** because it's fundamentally a design flaw (the system trusts user-supplied URLs).

- **Authoritative checks server-side** — never trust client-side validation, role flags, prices, totals.
- **Idempotency on mutations** — see `api-design`. Replays are routine.
- **Rate limiting** baked into the design, not an afterthought.
- **Failure modes considered**: cache empty, DB read times out, third-party SDK throws.
- **Privacy-by-design** — collect only what's needed, retain only as long as needed, delete on request.
- **Threat model** every new feature.

### SSRF — Now Under Insecure Design

Server fetches a URL provided by user → can hit internal services / cloud metadata / private network. Mitigations unchanged:

- **Allowlist** target hosts (or block all but a known set).
- **Block private IP ranges** (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16, fc00::/7).
- **Re-resolve DNS server-side** — defeat DNS rebinding. Fetch via the resolved IP.
- **Disable HTTP redirects** OR follow with the same allowlist check.
- **Set short timeouts** (5s) — prevents hanging the worker.
- **Use a side-channel-free HTTP client** that doesn't leak responses to logs.
- **Block `169.254.169.254`** explicitly — AWS / GCP / Azure cloud metadata endpoint.

```python
import ipaddress
import socket

PRIVATE_NETWORKS = [
    ipaddress.ip_network(net) for net in [
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "169.254.0.0/16", "fc00::/7", "::1/128",
    ]
]

def assert_safe_host(host: str) -> None:
    ip = ipaddress.ip_address(socket.gethostbyname(host))
    for net in PRIVATE_NETWORKS:
        if ip in net:
            raise SSRFRefused(f"refusing to fetch internal address {ip}")
```

For external image fetches / OAuth callbacks / webhooks: this check is non-negotiable.

---

## A07:2025 — Authentication Failures (renamed)

Was "Identification and Authentication Failures" in 2021. See `auth-patterns` skill — full coverage.

Recap: passwords with Argon2id, no enumeration on login/reset, rate-limit, refresh-token rotation with theft detection, TLS-only, HttpOnly+Secure+SameSite cookies, OAuth 2.1 + PKCE, passkeys/WebAuthn (preferred default in 2026).

---

## A08:2025 — Software or Data Integrity Failures (same)

Insecure deserialization, unsigned updates, CI/CD compromise. Overlaps with A03 (Supply Chain) but focuses on integrity at runtime + at rest.

- **Never deserialize untrusted data** with format-with-code-execution (Python `pickle`, Java native serialization, PHP `unserialize`). Use JSON / Protobuf / msgpack.
- **CI/CD**: short-lived tokens (OIDC to AWS/GCP), no long-lived secrets in env.
- **Code signing** for app artifacts (Apple notarization, Play App Signing).
- **Dependency provenance** — verify checksums; sigstore where available.
- **No `eval`** anywhere, ever.
- **Webhooks**: HMAC signature verification on every incoming call.

---

## A09:2025 — Security Logging and Alerting Failures (renamed)

Was "Logging & Monitoring Failures". Renamed to highlight that **logging without alerting is useless during an incident** — alerts convert logs into actionable response.

**Cited 2025 examples**:
- Children's health provider — undetected 7-year breach due to no monitoring.
- Indian airline — multi-decade breach at a third-party host.
- European airline — €20M GDPR fine for inadequate payment-security logging.

**Log**:
- Auth events (sign-in success/failure, sign-out, 2FA enable/disable).
- Authorization denials (403 — esp. on sensitive endpoints).
- Validation failures with strange shapes (potential probe).
- Rate-limit triggers.
- Server errors (500s) with `request_id` for correlation.

**Don't log** (CWE-532 — "Insertion of sensitive information into log files"):
- Authorization headers / cookies / tokens.
- Passwords / TOTP codes / backup codes.
- Full PII (mask emails, omit names, never raw payment data).
- Output of `str(exc)` from DB / framework — use structured logging with sanitized fields.

**Alert on** (the new emphasis):
- Spike in auth failures from one IP / one user.
- Spike in 403s on sensitive endpoints.
- Rate-limit triggers per user (potential account takeover attempt).
- Outbound traffic to unexpected destinations (data exfiltration).
- New CVE matches your SBOM.

**Each alert needs a runbook**. Page-without-runbook becomes alarm fatigue. Adopt NIST 800-61 incident-response framework or equivalent.

```python
# Sanitize before sending to APM:
def before_send(event, hint):
    event = strip_pii(event)
    headers = event.get("request", {}).get("headers", {})
    headers.pop("Authorization", None)
    headers.pop("Cookie", None)
    return event

sentry_sdk.init(dsn=DSN, before_send=before_send)
```

---

## A10:2025 — Mishandling of Exceptional Conditions (NEW)

The big new category. Catches three patterns:

1. **Resource leaks on exception** → file handles, DB connections, locks not released. Eventually exhausts the system → denial of service.
2. **Information leak in error response** → DB / framework error reaches the client. Attacker uses leaked schema names / column names / file paths for SQL injection reconnaissance or further attacks.
3. **Partial commits** → multi-step transaction fails mid-way. Attacker exploits half-applied state to drain accounts, duplicate transfers, bypass checks.

**CWEs covered** (24 total; key ones):

- **CWE-209** — Information exposure through error messages.
- **CWE-476** — NULL pointer dereference.
- **CWE-636** — "Failing Open" instead of failing securely.
- **CWE-703** / **CWE-755** — Improper exceptional condition handling.

**Defenses**:

### Catch at Source, Not at the Top

```python
# BAD — swallow everything at the top, no detail, no recovery
@app.exception_handler(Exception)
async def handle_all(request, exc):
    return JSONResponse({"error": "something failed"}, status_code=500)

# GOOD — specific handlers per known failure mode; a top-level safety net
@app.exception_handler(DBConnectionError)
async def handle_db_down(request, exc):
    logger.error("DB unreachable", extra={"request_id": request.state.request_id, "exc": str(exc)})
    return _problem(request, 503, "dependency_unavailable",
                    detail="database temporarily unavailable",
                    extra={"retry_after_seconds": 30})

@app.exception_handler(ValidationError)
async def handle_validation(request, exc):
    return _problem(request, 422, "validation_failed",
                    detail="request shape invalid",
                    errors=[{"field": e["loc"][-1], "code": e["type"], "message": e["msg"]} for e in exc.errors()])
```

### Resource Cleanup — `with` / `defer` / `finally` Always

```python
# BAD — file handle leaks on exception in DB call
async def upload(file):
    f = open(path, "wb")
    while chunk := await file.read(1 << 16):
        f.write(chunk)
    await db.execute("INSERT ...")     # if this throws, f is never closed
    f.close()

# GOOD — context-managed; cleanup even on exception
async def upload(file):
    async with aiofiles.open(path, "wb") as f:
        while chunk := await file.read(1 << 16):
            await f.write(chunk)
    try:
        await db.execute("INSERT ...")
    except DBError:
        await aiofiles.os.remove(path)  # rollback the side effect
        raise
```

```go
// Always defer close right after acquire.
f, err := os.Create(path)
if err != nil { return err }
defer f.Close()
// ... if anything below errors, f.Close() still runs.
```

### Atomic Transactions — Full Rollback or Nothing

Never partial commit. Use the `UnitOfWork` outbound port from `hexagonal-architecture`:

```go
err := uc.uow.Run(ctx, func(ctx context.Context) error {
    if err := uc.orders.Save(ctx, o); err != nil { return err }
    if _, err := uc.payments.Charge(ctx, ...); err != nil { return err }
    o.MarkPaid(...)
    return uc.orders.Save(ctx, o)
})
// If ANY step fails, the entire UoW rolls back. No partial commit.
```

### Fail-Closed in Security Code

```python
# BAD — exception in auth check defaults to allow
def is_admin(user):
    try:
        roles = fetch_roles(user)
    except Exception:
        return False  # OK — fail closed
    return "admin" in roles

# WORSE — defaults to allow!
def is_admin(user):
    try:
        return "admin" in fetch_roles(user)
    except Exception:
        return True  # !! catastrophe
```

### Centralized Error Envelope

Per `api-design` skill: every error response uses RFC 9457 ProblemDetails. Single `_problem(...)` helper. Never construct error JSON ad-hoc per route — that's how detail leaks happen.

### Resource Quotas at the Framework

- Max body size (1MB default, raise per-endpoint).
- Max upload count per user per minute.
- Max concurrent connections per IP / per user.
- Max query result rows.
- Max LLM context tokens (for the FastAPI AI adapter — runaway prompts blow your budget).

### Test the Unhappy Path

```python
# pytest fixture: throw mid-transaction
async def test_place_order_rollbacks_on_payment_failure(uc, fake_payments, fake_orders):
    fake_payments.fail_next("declined")
    with pytest.raises(PaymentDeclined):
        await uc.execute(PlaceOrderInput(...))
    # Verify NO order was persisted.
    assert await fake_orders.find_by_user(USER_ID) == []
```

Build a fixture for every external dep that can throw, then write a test per "what if this fails mid-way" scenario.

---

## Bonus — Risks Not in the Top-10 But Common

### CSRF (cookie-auth web clients)

If you have any cookie-based client (admin panel, web app):

- `SameSite=Strict` (or `Lax` if you need cross-site OAuth callbacks).
- Double-submit token OR custom header (`X-Requested-With`) check.
- Origin / Referer header validation on POST.

For API-only servers using `Authorization: Bearer …`, CSRF is N/A.

### XXE (XML External Entity)

If you parse XML (rare in 2026, but still SOAP / SAML / RSS):

- Disable external entity resolution at the parser level.
- Python: `defusedxml` instead of stdlib.
- Go: `encoding/xml` is safe by default; just don't enable entity resolution manually.

### Server-Side Template Injection (SSTI)

If you render templates with user input (Jinja2, Go html/template):

- NEVER concat user input into the template source.
- Use the template's parameter binding (`{{ .Title }}` from struct, NOT `Render(fmt.Sprintf(template, userInput))`).
- Auto-escape ON by default.

### Mass Assignment / Over-Posting

Client posts `{ "name": "X", "is_admin": true }` and you blindly map → admin escalation.

- **Allowlist fields** explicitly per endpoint. NEVER `model.update(**request.body)` or `bind.Body(&model)` without a DTO.
- DTOs at the boundary, then map field-by-field to domain entities.

### Path Traversal

User input becomes a file path → `../../etc/passwd`.

```python
from pathlib import Path
def safe_path(user_input: str) -> Path:
    base = Path("/var/uploads").resolve()
    target = (base / user_input).resolve()
    if not target.is_relative_to(base):
        raise PermissionError("path escape")
    return target
```

### Open Redirect

Endpoint accepts a `?return_to=` URL → attacker uses your domain to redirect to phishing.

- Allowlist destinations (relative paths only, OR specific external hosts).
- Reject anything not on the allowlist.

### LLM Prompt Injection (FastAPI AI adapter)

Untrusted user text concatenated into a prompt → user can override system instructions or extract data:

- **Treat user input as data, not as part of the system prompt.** Use structured roles (system / user / assistant / tool).
- **Never let users supply or modify the system prompt.**
- **Output filtering** — scan model output for sensitive patterns (other users' data, prompts, API keys) before returning.
- **Tool / function calls** require server-side authorization on every invocation. The LLM can REQUEST a tool call; the server decides whether to honor it.
- **Resource budget** per session (max tokens, max calls per minute) — runaway recursion is real.

### Sensitive Endpoints — Block Public Exposure

- `/admin`, `/swagger`, `/.git`, `/config.yaml`, `/healthz` (if it leaks version) — gated by auth + IP allowlist + ideally not on the public domain at all.
- Robots.txt does NOT protect anything; treat it as an "interesting paths" attacker hint.

---

## References

- *OWASP Top-10 (2025)*: <https://owasp.org/Top10/2025/> (released November 2025; current standard).
- *OWASP API Security Top-10 (2023)*: <https://owasp.org/API-Security/> (separate list specifically for APIs).
- *OWASP ASVS v5.0* (Application Security Verification Standard, 2024+).
- *OWASP Cheat Sheet Series*: <https://cheatsheetseries.owasp.org/>
- *NIST SP 800-218* — Secure Software Development Framework.
- *NIST SP 800-61* — Computer Security Incident Handling Guide (for A09 alerting / runbooks).
- *PortSwigger Web Security Academy* — best free training.
- *CISA Known Exploited Vulnerabilities catalog* — for prioritizing patch work.
