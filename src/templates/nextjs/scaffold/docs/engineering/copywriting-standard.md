<!-- domain:CONTENT | layer:policy | ssot:true | updated:2026-03-16 -->

# Copywriting Standard

Purpose: Define the quality bar, tone rules, and review rubric for all user-facing copy across ExampleApp.
Read when: Writing or reviewing marketing copy, product descriptions, docs copy, UI text, legal language, or CTAs.
Skip when: Working on code, infra, or backend-only tasks with no user-facing strings.
Read next: `../pages-content-spec/00-index.md`, `../../STYLE_GUIDE.md`

> Nav: [Docs Index](../00-index.md) | [Content Specs Index](../pages-content-spec/00-index.md)

---

## Why/What/How Framework

Every piece of copy must answer three questions in the user's mind:

> **Why** — Why does the user care? What pain point or aspiration does this address?
> **What** — What is being offered? (product, feature, benefit, action)
> **How** — How does the user get it? (clear next step, CTA, or process)

Copy that skips any of these three leaves friction.

---

## Quality Rubric (Target: 9/10)

Evaluate all user-facing copy against these five dimensions:

- Clarity → 2pts: instantly understandable, no jargon, reader knows what to do
- Tone-fit → 2pts: matches context (formal=docs, conversational=marketing, clear=errors, plain=legal)
- SEO → 2pts: target keywords natural, meta descriptions compelling, headings signal hierarchy
- Persuasion → 2pts: creates desire, addresses objections, clear CTA, tangible benefits
- Correctness → 1pt: no grammar/spelling/factual errors, verifiable statements, consistent tone

A score of 9 means one minor flaw that doesn't block understanding or action.

---

## Brand Voice & Tone

**ExampleApp is: premium but accessible, expert but friendly, modern but trustworthy.**

- **Premium** → polished, confident, quality-first. No typos, no filler, no bargain-bin energy.
- **Accessible** → no gatekeeping language or jargon. A high schooler should understand pricing and value props.
- **Expert** → back claims with specifics. Show domain knowledge in templates, design, AI, digital tools.
- **Friendly** → conversational. Contractions okay. Personality welcome.
- **Modern** → current references, clean language, no outdated metaphors.
- **Trustworthy** → clarity over hype. Tell the truth about limitations. Don't overpromise.

Tone depends on context — keep it consistent within a page or section:

- **Marketing** (landing pages, product cards, emails) → conversational, confident, benefit-focused. Use "you." Create desire without being pushy.
- **Documentation** (guides, API docs, onboarding) → formal, precise, action-oriented. Use imperative voice.
- **Error messages** (validation, failures, warnings) → clear, helpful, non-blaming. Always include recovery action.
- **Legal** (ToS, Privacy, Disclaimers) → formal, factual, plain language. Be exhaustive but readable.

---

## Copy Rules

1. **Active voice** over passive. "Download your template" not "Your template can be downloaded."
2. **Second person ("you")** for user-facing copy. "You get lifetime access" not "Users get lifetime access."
3. **Short sentences.** Average max 25 words. Vary length to maintain rhythm.
4. **Heading case:** H1 & H2 → Title Case; H3+ → Sentence case.
5. **CTAs use imperative verbs.** "Get started," "Download now," "Browse templates" — not "Click here" or "Learn more" alone.
6. **No unsupported superlatives.** Not "the best templates on the web" — instead "templates rated 4.9/5 by 12K+ creators."
7. **Price display:** Always show currency symbol. Omit cents for round numbers ("$29/mo" not "$29.00/mo").
8. **Avoid:** generic AI-sounding copy ("leverage synergies"), clickbait without substance, excessive exclamation marks (max one per section), unexplained buzzwords.

---

## Examples: Good vs Bad

- Bad: "This template helps you. It has lots of features." → Good: "Save 8 hours on your next project. 40+ pre-built blocks, customizable themes, and Figma source files. Get started in under 5 minutes."
- Bad: "Invalid email. Error." → Good: "That email is already linked to an account. Log in, or try a different email."
- Bad: "The best AI templates platform. We help creators achieve amazing things." → Good: "Design faster. 10,000+ creators save 12 hours per project with ExampleApp templates. Explore free — no credit card required."

---

### Error Messages

- Error messages are user-facing copy — they must be clear, non-technical, and actionable.
- Good: "Email already registered. Try logging in instead."
- Bad: "Duplicate entry in users table for email field."
- Always tell the user what to do next, not just what went wrong.
- Empty state messages should be encouraging, not negative: "No reviews yet — be the first!" not "No data found."

---

## Checklist Before Publishing

- [ ] Copy passes 9/10 rubric (or documented exception)
- [ ] Why/What/How framework is complete
- [ ] Tone matches context (marketing/docs/error/legal)
- [ ] Active voice is primary
- [ ] Shortest sentence average is <25 words
- [ ] CTA is clear and imperative
- [ ] No superlatives without supporting evidence
- [ ] No grammar, spelling, or factual errors
- [ ] Brand voice is consistent (premium, accessible, expert, friendly)
- [ ] SEO keywords appear naturally (if applicable)
