<!-- domain:META | layer:playbook | ssot:true | updated:2026-05-08 -->
# Playbook — Security Review (Per-Change Overlay)

> P: OWASP-aligned per-change checklist applied as an overlay regardless of the primary domain (backend, frontend, infra, mobile).
> R: Any change that touches authentication, authorization, secrets, input handling, file IO, network calls, or data persistence.
> S: Pure cosmetic changes (CSS, copy, dead code removal) that do not affect any of the surfaces above.
> N: [api-contract-discipline.md](../../core/rules/api-contract-discipline.md), [mcp-error-envelope.md](../engineering/mcp-error-envelope.md), [security-review-template.md](../governance/templates/security-review-template.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## When to invoke

Treat security review as an **overlay** on top of the primary playbook. It runs in addition to the domain playbook, never instead of it. The trigger conditions are mechanical:

- The change introduces or modifies an authentication or authorization path.
- Reads, writes, or transmits a secret (token, key, credential, PII).
- Accepts user input that flows into a query, file path, shell command, network call, or rendered HTML.
- Adds, removes, or changes a network endpoint exposed to consumers.
- Touches the migration / schema layer in a way that alters access control.

## The seven checks (applied per change)

1. **Authentication boundary.** Where does identity enter? Is the session / token validated against the right authority? Is the path that bypasses auth (debug routes, internal endpoints) impossible to reach in production?
2. **Authorization boundary.** Once identity is known, what gate decides what they may do? Is the gate enforced server-side (never client-side only)? Are admin / privileged paths flagged with a stricter check?
3. **Input validation.** Every input that crosses a trust boundary must be validated against an explicit schema (Pydantic, JSON-schema, struct tags). No "we'll trust it because it came from our frontend." Reject unknown fields by default.
4. **Output encoding.** Any value that flows into HTML, SQL, a shell, a header, or a log line must be encoded for that target. Parameterized queries everywhere. Template engines with auto-escape on. No string concatenation into shell.
5. **Secrets handling.** Secrets live in environment variables or a secrets manager — never in code, never in commits, never in logs. New secrets must have a rotation plan documented at introduction time.
6. **Error and log surface.** Errors returned to the client must not leak internals (stack traces, paths, query bodies). Logs may carry detail, but PII must be scrubbed before log lines leave the process. The MCP envelope (`fail(category, message)`) is the right shape for client-facing errors.
7. **Dependency and supply-chain hygiene.** Any new dependency must be locked (SHA / version pin), justified in the PR description, and reviewed for license + maintenance status. No transitive upgrades smuggled in via `*` or `^` in the manifest.

## Acceptance

- Every check above either passes or is explicitly marked "n/a, reason: …" in the PR.
- New input boundaries have schema-validated handlers.
- New auth-touching code paths have at least one test for each of: authenticated success, unauthenticated rejection, authorized-but-out-of-scope rejection.
- No secret literal appears in the diff (`grep -E '(secret|key|password|token).*=.*["\047][A-Za-z0-9_/+-]{20,}'` returns nothing).
- The change's threat model — even one paragraph — is captured either in the PR or in a linked task note. Skipping this is the most common silent regression.

## Rollback

Security regressions sometimes ship despite review. Have a rollback path that doesn't require a follow-up PR — a feature flag, a config switch, or a reverted commit that doesn't break unrelated callers. Document the path in the change description, not in tribal knowledge.

## Anti-patterns

- "It's behind auth, so input validation is optional." False — defence in depth means each layer validates as if the others may fail.
- Reusing a permission check copy-pasted from another route. Permissions belong in a single helper that is the SSOT; copies drift.
- "We'll add tests later." Auth and access-control tests are the ones that prevent the most production incidents. Skipping them is the highest-regret form of debt.
- Logging full request bodies for "debug." Bodies often contain PII. Log structured, redacted summaries.
- Adding a dependency to fix a five-line problem. Each dependency expands the supply-chain surface; weigh that against writing the five lines.
