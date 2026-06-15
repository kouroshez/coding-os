<!-- domain:SECURITY | layer:playbook | ssot:true | updated:2026-03-17 -->
# Security Review Playbook

Purpose: Apply a consistent security review path for risky changes before code or docs are considered complete.
Read when: The task touches auth, cookies, payments, file uploads, redirects, HTML rendering, admin access, download authorization, or permission checks.
Skip when: The task is purely cosmetic docs work with no behavioral/security impact.
Read next: your stack's engineering rules and the relevant API-contract doc for the risky path

> Nav: [Docs Index](../00-index.md) | [Docs System](../governance/docs-system.md)

## Read Selection Guide

> Complete lookup: AGENTS.md § Dimension Type Registry § Security Overlay (auto-loaded). This section adds detail for Orient phase.

Security is an overlay playbook — read the sub-files that match your task's security dimensions.

### Read Only If Relevant (read ALL that apply, not just one)

- Auth / JWT / sessions / login flows — your stack's auth-pattern docs
- Cookies / CSRF / CORS / rate limiting / HTTP headers — your stack's web-security docs
- File downloads or signed URLs — your stack's download-authorization docs
- User data, sessions, or account lifecycle (GDPR deletion) — your stack's compliance docs
- `docs/engineering/*-rules.md` — the engineering rules for the layer you are touching

## Review Checklist

- Authentication and authorization paths are explicit
- Cookie/session settings remain `httpOnly`, `secure` in production, `SameSite=Strict`
- Payment and webhook flows remain idempotent
- Upload/download flows validate content type and access scope
- Admin routes and privileged endpoints are not conflated with public routes
- Logs and error responses do not leak secrets or internal implementation details
- Error responses do not leak internal details (no raw exception text, DB column names, or provider URLs)
- All error handling is fail-closed (reject on uncertainty, not allow-and-log)
- Permission boundaries enforce the project's RBAC model — verify role checks on every protected endpoint

## Verification

- Run the domain verification commands from the primary playbook
- Add at least one targeted test or explicit manual check for the risky path
- If docs changed, confirm security rules and examples use current stack terminology
