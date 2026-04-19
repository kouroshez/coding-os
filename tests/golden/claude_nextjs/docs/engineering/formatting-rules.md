<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-03-18 -->
# Documentation Formatting Rules

Purpose: Token-efficient formatting standards for all project documentation.
Read when: Creating or editing any .md file in the docs system.
Skip when: File content is unchanged and formatting is not in scope.
Read next: `docs-system.md` for layer model and naming rules.
> Nav: [Docs Index](../00-index.md) | [Docs System](../governance/docs-system.md)

## File Standard

Every `.md` file in `docs/` starts with a UFS header:

```html
<!-- domain:DOMAIN | layer:LAYER | ssot:true|ref | updated:YYYY-MM-DD -->
```

**Domain values:** ALL, AUTH, CATALOG, COMMERCE, PAYMENTS, DOWNLOADS, CONTENT, EMAIL, REVIEWS, ANALYTICS, ADMIN, INFRA, DOCS

**Layer values:** index, playbook, spec, policy, reference, adr, task

**ssot values:**
- `true` → canonical source for its topic
- `ref` → references other SSOT files

## Format Conversion Rules

### Rule 1 — Two-column data: Arrow notation

```markdown
<!-- Prefer arrow notation -->
- Name → Django
```

### Rule 2 — Settings/config: Annotated code blocks

```python
# Before: | SECURE_SSL_REDIRECT | True | Force HTTPS |
# After:
SECURE_SSL_REDIRECT = True       # Force HTTPS
```

### Rule 3 — Package/dependency lists: Structured bullets

```markdown
- `django-environ` 0.13.x — CRITICAL
  Loads env vars, parses DATABASE_URL.
```

### Rule 4 — Tables ARE justified when

- Schema definitions (column name, type, constraints, description)
- Comparison matrices (3+ items x 3+ dimensions)
- Status/enum mappings with 3+ fields

### Rule 5 — Collapse completed sections

Use `<details>` for any section that is 100% completed but kept for reference.

## General Rules

- Use bullet lists over tables when data has ≤ 2 columns.
- Keep GitHub-flavored Markdown; no HTML unless rendering requires it.
- Prefer `key → value` arrow notation for two-column mappings.
- File size limit: **300 lines max**. Split into sub-files with index if exceeded.
- Relative links only — no absolute paths to local files.

## File Header Format

Every `.md` file in `docs/` starts with a UFS metadata header (see `docs/governance/docs-system.md` for the full contract):

```html
<!-- domain:DOMAIN | layer:LAYER | ssot:true|ref | updated:YYYY-MM-DD -->
```

Immediately after the H1 heading, include the opening block: `Purpose`, `Read when`, `Skip when`, `Read next`. These lines let an agent decide within the first screenful whether to keep reading.

## Script Output Format

All infrastructure scripts source `_lib.sh` and use standardized prefixes:

| Prefix | Use | Stream |
| --- | --- | --- |
| `OK:` | Success result | stdout |
| `INFO:` | Informational data | stdout |
| `WARN:` | Non-fatal warning | stderr |
| `ERROR:` | Fatal error (exits) | stderr |

Scripts that produce structured output begin with a `=== script-name ===` header line.
