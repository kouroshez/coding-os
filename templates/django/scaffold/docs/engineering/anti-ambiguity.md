<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-03-16 -->
# Anti-Ambiguity Guide

Purpose: Canonical policy for this workflow or engineering surface.
Read when: The task changes or depends on this policy.
Skip when: A more specific task file or playbook already governs the work.
Read next: The nearest related index or referenced policy.


> Purpose: Eliminate vague requirements. Every requirement must be testable.
> Nav: [Docs Index](../00-index.md) | [Code Style](../../CodeStyle.md)

## SMART-T Framework

Every requirement MUST be:

- **S**pecific → exact target, no "improve" or "enhance"
- **M**easurable → quantifiable metric or binary pass/fail
- **A**ctionable → clear verb: create, add, remove, configure
- **R**eferenced → points to a SSOT document for context
- **T**estable → can be verified without subjective judgment
- **T**raced → linked to a task number (TASK-###)

## Ambiguity Replacements

- `fast` → `LCP < 2.5s on page X`
- `modern` → `uses design tokens, no inline hex`
- `secure` → `implements items from REF:SECURITY §1-5`
- `user-friendly` → `passes WCAG 2.1 AA, < 3 clicks to goal`
- `scalable` → `handles 1000 concurrent users per VPS specs`
- `responsive` → `renders correctly at 375px, 768px, 1280px breakpoints`
- `clean code` → `passes ruff check + mypy with zero errors`
- `good UX` → `matches wireframe from content spec, < 3s interaction`
- `handles errors` → `returns HTTP 400 with error_code VALIDATION_ERROR for invalid input; logs at WARNING; returns 500 with SERVER_ERROR for unhandled exceptions`
- `clean code` (design sense) → `functions under 20 lines, max 3 params, guard clauses over nesting, names as documentation`
- `edge cases` → `tested for null, empty, boundary, concurrent, and service-unavailable scenarios`

## Requirement Severity Tags

- `MUST` → non-negotiable for the task to be marked complete
- `SHOULD` → expected unless explicitly justified in task notes
- `MAY` → optional enhancement, implement if time permits

## Definition of Done Template

```markdown
- Given [precondition with specific values]
- When [action with exact input]
- Then [observable outcome with measurable result]
```

**Good example:**
```markdown
- Given a product with price_cents=999 and is_active=True
- When GET /api/v1/products/{id}/ is called
- Then response status is 200 and body.price_cents equals 999
```

**Bad example:**
```markdown
- Given a product exists
- When user views the product
- Then it displays correctly
```

## Pre-Flight Ambiguity Checklist

Before starting a task, verify each requirement has:

- A specific verb + target
- A SSOT document reference
- Testable Given/When/Then acceptance criteria

This checklist is enforced at task creation time (see `make task-create`), not as a section in the task file.
