---
name: i18n
description: Internationalize and localize software — externalized message catalogs, ICU MessageFormat for plurals/gender/select, locale-aware formatting of dates/numbers/currency, RTL/bidi layout, Unicode correctness, content negotiation, and the translation pipeline. Use when extracting hardcoded UI strings, choosing an i18n library (react-i18next/FormatJS/next-intl/vue-i18n/gettext), handling plural rules across languages, formatting per-locale dates/currency, supporting RTL scripts, designing the locale-resolution chain, or wiring a translation workflow. Boundary vs a11y and frontend-fundamentals — a11y owns assistive-tech access (semantics, screen readers, keyboard, contrast) and frontend-fundamentals owns generic UI state/structure; this skill owns the language-and-locale dimension — message catalogs, pluralization/grammar, locale-aware formatting, bidi/RTL, and Unicode handling — concerns that exist even for a fully accessible single-language UI. Defers per-locale visual tokens to frontend-design.
tier: cross-cutting
domain: [frontend, backend]
last_reviewed: "2026-06-14"
---

# Internationalization & Localization — One Codebase, Every Locale

A practical guide to building software that adapts to language, region, and script without forking the code per market. Stack-agnostic; recipes target react-i18next / FormatJS (ICU) / next-intl / vue-i18n on the client and ICU / gettext on the server. The distinction that frames everything: **i18n** (internationalization) is the engineering to *make* software localizable; **l10n** (localization) is the per-locale *content and adaptation* that engineering enables.

## When to Use This Skill

- Extracting hardcoded UI strings into a message catalog for the first time.
- Choosing an i18n library and message format (ICU MessageFormat vs gettext).
- Handling plurals/gender/grammar that differ by language (not every language has "1 vs many").
- Formatting dates, numbers, currency, and lists per locale.
- Supporting right-to-left (Arabic, Hebrew) and bidirectional text.
- Designing the locale-resolution chain (URL / header / cookie / user preference).
- Wiring the translator workflow — extraction, a translation-management system, re-import.

Skip when: the only concern is screen-reader/keyboard access for a single language — that is a11y. This skill is the language-and-locale dimension; the two compose (a localized UI must still be accessible).

## Rule Zero — Never Concatenate Translated Strings

The defining beginner mistake: `t("Hello") + " " + name + t("!")` or building a sentence from fragments. Word order, agreement, and punctuation differ per language; concatenation hardcodes English grammar into every locale.

```js
// WRONG — assumes English word order, breaks in most languages
const msg = t("You have") + " " + count + " " + t("new messages");

// RIGHT — one externalized message with named placeholders; the translator owns the whole sentence
t("inbox.unread", { count });
// catalog (ICU): "You have {count, plural, one {# new message} other {# new messages}}"
```

Every user-visible string is one complete, externalized message with named interpolation placeholders. The translator receives the full sentence and reorders freely.

## ICU MessageFormat — Plurals, Gender, Select

English has two plural forms (1 / many). Arabic has six; Polish and Russian have three with non-obvious rules; Japanese and Chinese have one. **Hardcoding `count === 1 ? singular : plural` is wrong for most of the world.** ICU MessageFormat encodes the CLDR plural rules so each locale's translation picks the right form:

```
{count, plural,
  =0 {No items}
  one {# item}
  few {# items}
  many {# items}
  other {# items}}
```

- **`plural`** selects by the locale's CLDR category (`zero/one/two/few/many/other`); the translator fills the categories their language actually uses.
- **`select`** handles gender / arbitrary enums: `{gender, select, male {He} female {She} other {They}}`.
- **Nested** plural-in-select handles "He has 1 message / She has 3 messages" as one message.
- Use the platform `Intl.PluralRules` / an ICU-aware library; never reimplement plural logic in app code.

## Locale-Aware Formatting — Use `Intl`, Never Hand-Roll

Dates, numbers, and currency are formatted by the *locale*, not by a global format string.

```js
new Intl.DateTimeFormat(locale, { dateStyle: "long" }).format(date);   // "14 June 2026" / "2026年6月14日"
new Intl.NumberFormat(locale).format(1234567.89);                       // "1,234,567.89" / "1.234.567,89"
new Intl.NumberFormat(locale, { style: "currency", currency }).format(amount);
new Intl.ListFormat(locale, { type: "conjunction" }).format(items);     // "A, B, and C" / "A、B、C"
```

- **Decimal/thousands separators flip** between locales (`1,234.56` vs `1.234,56`) — never format numbers with string ops.
- **Currency is a data attribute, not a locale attribute.** A French user can see USD; pass the currency code explicitly, let `Intl` place the symbol per locale.
- **Always store/transmit timestamps in UTC (ISO 8601);** format to the user's timezone only at display time. Storing local time is a recurring DST bug.
- **Translatable text is data, code formats it** — keep format logic out of the catalog.

## RTL / Bidi and Unicode Correctness

- **Right-to-left layout** (Arabic, Hebrew, Persian) mirrors the whole UI. Use CSS logical properties (`margin-inline-start`, not `margin-left`) and set `dir="rtl"` on `<html>` — then layout flips for free. Physical left/right hardcodes LTR.
- **Bidi text** (an English word inside an Arabic sentence) needs Unicode isolation (`Intl` / bidi control chars) or interpolated values render in the wrong order.
- **Unicode discipline**: normalize to NFC on input; a "character" the user sees may be multiple code points (combining marks, emoji ZWJ sequences) — count grapheme clusters, not code units, for length limits. Compare strings with locale-aware collation (`Intl.Collator`), not raw byte order, for sorting.
- **Text expands.** German runs ~30% longer than English; CJK is shorter but taller. Design flexible layouts; never size a button to the English string.

## The Locale Resolution Chain & Pipeline

- **Resolve locale** in a defined precedence: explicit user setting → URL/path (`/de/...`, best for SEO) → `Accept-Language` header → cookie → default. Pick one order, document it, fall back gracefully to a default locale on any miss.
- **Lazy-load catalogs** per locale (and per route/namespace) — shipping every translation to every user bloats the bundle. Load the active locale's catalog only.
- **Catalogs are the contract with translators.** Extract strings to catalog files (JSON/PO/XLIFF), push to a translation-management system (Crowdin, Lokalise, Tolgee), re-import. Never hand-edit translated files in code; never let untranslated keys ship as raw key names — fall back to the source locale.
- **Pseudolocalization in CI** (`[!!! ḺöREM !!!]`) surfaces hardcoded strings and truncation before a human translator is paid.

## Anti-Patterns (reject in review, fix on sight)

- **Concatenating translated fragments** — hardcodes English grammar everywhere.
- **`count === 1 ? x : y` pluralization** — wrong for most languages; use ICU plural + CLDR.
- **Hardcoded date/number format strings** — `MM/DD/YYYY` is wrong outside the US; use `Intl`.
- **Physical CSS (`left`/`right`, `padding-left`)** — breaks RTL; use logical properties.
- **Hardcoded UI strings** left in components — nothing to translate; extract to the catalog.
- **Storing local time instead of UTC** — DST and timezone bugs.
- **Treating currency as derivable from locale** — pass the currency code explicitly.
- **Byte-length limits on user text** — breaks multibyte scripts; count grapheme clusters.
- **Shipping all locales' catalogs to every user** — bundle bloat; lazy-load the active locale.
- **Translator-facing keys named `string1`/`btn2`** — give descriptive keys + context for accurate translation.

## Tools per surface (2026 defaults)

| Need | Default | Alternatives |
|---|---|---|
| React i18n | react-i18next, FormatJS (react-intl) | next-intl (Next.js), Lingui |
| Vue i18n | vue-i18n | nuxt/i18n |
| Message format | ICU MessageFormat | gettext (PO) for server/legacy |
| Locale formatting | platform `Intl` (`DateTimeFormat`/`NumberFormat`/`PluralRules`/`ListFormat`) | Luxon, date-fns-tz |
| Server-side i18n | ICU4J / ICU4C, gettext, Python `babel` | — |
| Translation management | Crowdin, Lokalise, Tolgee | Phrase, Weblate |
| QA | pseudolocalization, screenshot diff per locale | — |

## Pairs With

- **a11y** — owns assistive-technology access; this skill owns the language/locale dimension. A localized UI must still be accessible — set `lang`/`dir` so screen readers announce correctly (the seam between the two).
- **frontend-fundamentals** — owns generic UI structure/state; this skill adds the localization layer over it.
- **frontend-design** — owns per-locale visual tokens and the flexible layouts that absorb text expansion.
- **api-design** — `Accept-Language` content negotiation and locale-aware error messages cross the API boundary.
- **technical-writing** — source strings written for clarity and translatability (short, context-rich, no idioms) start in the catalog.

## See also

- Unicode CLDR — plural rules, locale data, collation.
- ICU MessageFormat / `Intl` (MDN) — the canonical formatting APIs.
- W3C Internationalization — bidi, language tags (BCP 47), text layout.
- *Going Global with JavaScript and Globalize.js* and the FormatJS docs — practical ICU patterns.
