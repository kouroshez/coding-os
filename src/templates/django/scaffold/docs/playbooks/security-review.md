<!-- domain:AUTH | layer:playbook | ssot:true | updated:2026-03-17 -->
# Security Review Playbook

Purpose: Apply a consistent security review path for risky changes before code or docs are considered complete.
Read when: The task touches auth, cookies, payments, file uploads, redirects, HTML rendering, admin access, download authorization, or permission checks.
Skip when: The task is purely cosmetic docs work with no behavioral/security impact.
Read next: `docs/architecture/04-security-guardrails.md` and the relevant `04a/04b/04c` sub-file

> Nav: [Docs Index](../00-index.md) | [Security Guardrails](../architecture/04-security-guardrails.md)

## Read Selection Guide

> Complete lookup: AGENTS.md § Dimension Type Registry § Security Overlay (auto-loaded). This section adds detail for Orient phase.

Security is an overlay playbook — read the sub-files that match your task's security dimensions.

### Always Read (for any security review)

1. `docs/architecture/04-security-guardrails.md`

### Read Only If Relevant (read ALL that apply, not just one)

- `04a-auth-security.md` — if auth, JWT, sessions, or login flows are involved
- `04b-web-security.md` — if cookies, CSRF, CORS, rate limiting, or HTTP headers are involved
- `04c-download-security.md` — if file downloads or signed URLs are involved
- `04d-compliance.md` — if user data, sessions, or account lifecycle (GDPR deletion) are involved
- `docs/engineering/backend-rules.md` — if backend is touched
- `docs/engineering/frontend-rules.md` — if frontend is touched

## Review Checklist

- Authentication and authorization paths are explicit
- Cookie/session settings remain `httpOnly`, `secure` in production, `SameSite=Strict`
- Payment and webhook flows remain idempotent
- Upload/download flows validate content type and access scope
- Admin frontend routes and Django admin routes are not conflated
- Logs and error responses do not leak secrets or internal implementation details
- Error responses do not leak internal details (no str(exc), no DB column names, no provider URLs)
- All error handling is fail-closed (reject on uncertainty, not allow-and-log)
- Permission boundaries enforce the identity RBAC model (buyer/seller/agent_owner roles, staff_roles) — verify role checks on every protected endpoint

## Verification

- Run the domain verification commands from the primary playbook
- Add at least one targeted test or explicit manual check for the risky path
- If docs changed, confirm security rules and examples use current Django terminology
