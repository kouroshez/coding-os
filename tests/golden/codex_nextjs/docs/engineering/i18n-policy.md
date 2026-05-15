<!-- domain:ALL | layer:policy | ssot:true | updated:2026-03-16 -->
# Internationalization Policy

Purpose: Locale support, message-key naming, ICU format rules, and src/frontend/backend i18n contracts.
Read when: Adding translatable strings, setting up new locales, or reviewing i18n contracts.
Skip when: Working within existing locale without adding new message keys.
Read next: `architecture/10-blog-content-i18n.md` for content backend, `copywriting-standard.md` for tone.

> Nav: [Docs Index](../00-index.md) | [Blog & i18n Architecture](../architecture/10-blog-content-i18n.md)

---

## Supported Locales

- `en` → Active (default, fallback for all missing keys)
- `es` → Planned (Americas + Spain)
- `fa` → Planned (Iran + Farsi-speaking regions)
- `de` → Planned (DACH region)
- `fr` → Planned (France + Francophone)

Format: BCP 47 lowercase, no region subtags unless required by regulation.

---

## Message Key Naming

Format: `<page>.<section>.<key>` — all lowercase, dot-separated, no camelCase or underscores.

- Page prefix matches content-spec filename slug: `home.*`, `checkout.*`, `shared.*` (header/footer), `errors.*`
- Section groups by UI region: `home.hero.*`, `checkout.payment.*`
- Key names the specific element: `checkout.payment.card-label`, `shared.nav.home`

Examples: `home.hero.title` → "Welcome to NakoDigital" | `errors.not-found.heading` → "Page not found"

---

## Message Files

Location: `src/frontend/messages/{locale}.json` — nested JSON matching dot-separated keys.

Example: `{ "home": { "hero": { "title": "Welcome to NakoDigital", "cta": "Start browsing" } }, "checkout": { "summary": { "total": "Total", "item-count": "{count, plural, one {# item} other {# items}}" } } }`

Required: `en.json` must have all keys. Other locales may be incomplete — `next-intl` falls back to English.

---

## ICU Message Format

- **Variables** → `{count}` — wrap variable names in curly braces.
- **Pluralization** → `"{count, plural, =0 {No items} one {# item} other {# items}}"` — use `=0`, `one`, `other`.
- **Date/Time** → `"{date, date, long}"` — backend provides ISO 8601, frontend formats via next-intl.
- **Currency** → `"{amount, number, currency}"` — use `Intl.NumberFormat` in components or ICU format.

---

## Frontend Setup

- Library: `next-intl` (App Router) | Config: `src/frontend/next-intl.config.ts`
- URL structure: `/[locale]/page` (e.g., `/en/home`, `/es/checkout`)
- Locale detection: `Accept-Language` header → fallback `en`
- Usage: `const t = useTranslations(); return <h1>{t('home.hero.title')}</h1>;`
- With variables: `t('cart.item-count', { count: items.length })`

---

## Backend i18n

- **Django Admin** → `gettext_lazy` for model labels, help text. Files in `locale/{locale}/LC_MESSAGES/`.
- **DRF API** → English-only error messages with machine-readable error codes (e.g., `{ "error_code": "INVALID_CARD", "message": "Invalid card number" }`). Frontend maps `error_code` → localized message via `errors.<feature>.{error_code}` key.

---

## Hardcoded vs i18n Rule

**ALL user-facing text must use message keys:** headings, labels, buttons, links, form messages, tooltips, email templates, meta descriptions.

**Hardcoded English allowed only for:** console logs, code comments, variable names, migration descriptions, git commits.

- All user-facing error messages must use i18n message keys (`errors.<domain>.<ERROR_CODE>`), never hardcoded English strings.
- Backend error responses use `error_code` only — frontend maps to localized message via `messages/{locale}.json`.

**Enforcement phasing:** Content-spec files marked `format:i18n-keys` must stay lint-clean. Frontend runtime surfaces are still migrating — `make docs-lint` inventories remaining hardcoded text without failing. Admin-only surfaces and editor/demo code stay out of docs-lint gating until a dedicated migration task promotes them.

---

## Adding a New Locale

1. Copy `en.json` → `{new-locale}.json`
2. Update `next-intl.config.ts` to register locale
3. Add to this policy's supported locales list
4. Translate all keys — no blank values in production
5. Test language switcher and URL routing
6. Update `changes.log`

## Validation

- Missing keys → compare key depth between `en.json` and target locale
- Hardcoded text → `rg '">` in `src/frontend/components/`
- Key format → `rg '\.[a-z]+\.[a-z]+\.' src/frontend/` to validate
