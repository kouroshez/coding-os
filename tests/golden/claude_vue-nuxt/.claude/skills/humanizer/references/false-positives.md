<!-- domain:UNIVERSAL | layer:reference | ssot:false | updated:2026-08-24 -->
# False positives and human details worth keeping

Purpose: what NOT to flag when applying `Skill humanizer`, and which details carry the writer's voice.
Read when: reviewing prose for AI patterns, before acting on any single hit.
Skip when: you are drafting rather than reviewing — start from [patterns.md](patterns.md).
Read next: [../SKILL.md](../SKILL.md)

Over-application is the more expensive failure. A rewrite that strips a writer's habits produces prose that is clean, flat, and just as obviously machine-touched — and it destroys the specific detail that made the text worth reading. Adapted from [blader/humanizer](https://github.com/blader/humanizer) (MIT, © 2025 Siqi Chen); see [NOTICE](../NOTICE).

## Not evidence on its own

A person may write any of these. None is proof by itself.

- **Perfect grammar and consistent style.** Many writers are professionals or have been edited. Polish is not a tell.
- **Mixed casual and formal register.** Reflects field, age, or habit.
- **Bland or dry prose.** Generated text has *specific* tells. Dryness without them is just dry writing.
- **Formal or academic vocabulary.** §7 names specific overused words. Do not simplify every formal word you meet.
- **A salutation or sign-off** on a comment or email. Both predate chatbots by centuries.
- **One transition word.** *Additionally*, *moreover*, *consequently* are tells only when piled up. A single *however* means nothing.
- **Curly quotes alone.** macOS, Word, Google Docs, and most CMSes auto-curl by default.
- **Em dashes alone.** Editors and journalists use them heavily. They are evidence only alongside sales-y rhythm.
- **One short sentence for emphasis.** Flag fragments only when several run together.
- **Deliberate repeated openings.** "She came. She saw. She conquered." is rhythm, not repetition-penalty failure.
- **"Honestly" or "look" mid-sentence.** Ordinary in casual writing. The tell is the standalone theatrical opener.
- **Scope statements, legal notices, safety warnings, real corrections, named objections, FAQ answers.** These are load-bearing limits, not hedging.
- **Real alternatives** in a design doc, tutorial, or argument. §35 targets only an unlikely option raised and never used again.
- **Unsourced claims.** Most writing is unsourced. Missing citations prove nothing.
- **Clean, complex formatting.** Templates and visual editors produce it without help.
- **Secondhand text.** Never rewrite a watched phrase inside a quotation, a title, a proper name, or an example where the phrase is being *discussed* rather than used.
- **Text written before 30 November 2022.** ChatGPT's public launch. Older text is, with rare exceptions, not model-written.

When unsure, look for several patterns together in the same passage.

## Human details to protect

Keep these unless they damage meaning. They are usually the reason the text is worth reading.

- **Specific, odd detail.** A real address, a strange quote, "the lawyer who used to work upstairs from my dentist." Generated prose reaches for the representative example; people remember the particular one.
- **Mixed feelings and unresolved tension.** "I think this is mostly good, but it bothers me and I can't fully explain why."
- **Dated, era-bound references.** Slang, memes, and in-jokes anchored to a specific year and subculture. Models lag by a year or more.
- **Deliberate first-person choices.** A cut or an unusual word the writer can justify.
- **Variety in sentence length.** Real writing alternates short and long; generated writing drifts toward an even mid-length cadence. This is the detection counterpart of pattern 36.
- **Genuine asides and self-corrections.** "(I keep wanting to say 'almost' here, but it really was certain.)" Models rarely interrupt themselves.
- **The writer's own errors of register.** A non-native speaker's phrasing, an abrupt sentence, a word used slightly off. Smoothing these is the single fastest way to make honest prose read as generated.

## Reviewing, not rewriting

For a review-only request:

- Report the specific patterns found, each with a clickable file and line.
- Do not assign an AI score, a percentage, or a confidence rating.
- Do not claim to know whether a model wrote the text. You cannot, and the claim cannot be checked.
- Rank by cost to the reader, not by count. One inflated claim in the opening paragraph outweighs six curly quotes.
