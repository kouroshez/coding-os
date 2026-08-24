---
name: humanizer
tier: quality
domain: [universal]
description: Strip AI writing tells from prose a human will read outside the repo — README, release notes, launch announcements, blog posts, community and forum posts, PR bodies, landing copy. Use before publishing any text to an audience that did not ask for a document. Catches inflated claims, sales language, forced triads, stock vocabulary, performed candor, defending against objections nobody raised, em dashes, decorative bold, and chatbot residue — without changing a single claim. Triggers — "write a post", "blog", "announcement", "release notes", "README", "reply to", "landing page", "make this sound human", "this reads like AI". Pairs with technical-writing (structure and accuracy) and clean-code (comments).
globs: ""
paths: []
last_reviewed: "2026-08-24"
---

# Humanizer

Rewrite AI-sounding prose so it reads like the writer, without changing what it says.

The failure this prevents is not embarrassment. It is that a reader who smells generated text stops evaluating the argument and starts evaluating the author — so a correct, well-evidenced claim gets discarded on style. Published prose that trips those signals costs the credibility of everything it carries.

## The seam — this skill vs technical-writing

They run in sequence and must not fight:

| | `technical-writing` | `humanizer` |
|---|---|---|
| Owns | structure, altitude, accuracy, the doc-header contract | sentence-level texture and rhetoric |
| Asks | is it correct, findable, and at the right altitude? | does it read like a person wrote it? |
| Runs | while drafting | on the finished draft, before it ships |

Run `technical-writing` first. A humanized draft that is structurally wrong is still wrong.

## Non-negotiables

1. **Keep every claim.** Shorten dull parts, expand useful ones, merge or split paragraphs — but do not lose information. The exception is a pattern below that *requires* removal (unsupported importance, vague sources, invented context, unraised objections, fake alternatives, generic endings). Removing under one of those is correct, not a lost claim.
2. **Invent nothing.** No fact, name, number, date, quote, or citation that the source or the user did not supply. If a sentence needs a missing detail, ask for it or write a simpler sentence.
3. **Never manufacture humanity.** Do not add fake opinions, staged reactions, invented anecdotes, or fabricated specificity to make prose feel personal. That produces a different lie, not a human voice. Real voice comes from the writer's own material.
4. **Never claim to detect AI.** In a review, report the specific patterns you found with file and line. Do not assign an "AI score" or assert that a model wrote something — you cannot know, and the claim is unfalsifiable.
5. **Match the writer's voice over these rules.** If the user supplies a writing sample, read it first: sentence length, word choice, paragraph openings, punctuation, repeated phrases. Match those habits. A sample that uses em dashes keeps them; §14 is then not a ban.
6. **Leave good prose alone.** Minimum effective edit. Normalizing already-clear writing is a diff-discipline failure (Rule 22).

## The patterns

Full catalogue with before/after for every entry → [references/patterns.md](references/patterns.md). Grouped index:

- **Content (1-6)** — inflated importance · name-dropping · shallow `-ing` analysis · sales language · vague sources · formulaic challenges-and-outlook sections.
- **Language (7-13)** — stock AI vocabulary · avoiding *is*/*are* · "not X but Y" · forced groups of three · synonym cycling and repeated sentence openings · false "from X to Y" ranges · passive voice with a missing subject.
- **Style (14-19)** — em and en dashes · decorative bold · lists of bold mini-headings · Title Case headings · emoji · curly quotes.
- **Chatbot residue (20-22)** — greetings and offers left in the text · knowledge-cutoff disclaimers and plausible guesses · praising the user before answering.
- **Filler and rhetoric (23-35)** — filler phrases · stacked qualifiers · generic positive endings · hyphen pairs · fake depth ("at its core") · announcing the next point · a heading restated in its first sentence · describing the previous version · forced punchlines and manufactured gravity · formulaic sayings · fake-candid openings ("Honestly?", "Look") · answering objections nobody raised · rejecting alternatives nobody proposed.
- **Rhythm (36)** — uniform sentence and paragraph length. Patterns 1-35 work at word and phrase level; prose can pass all of them and still read generated because the sentences sit in one narrow length band.

What **not** to flag, and the human details worth protecting → [references/false-positives.md](references/false-positives.md). Read it before any review pass. One em dash proves nothing; several stock patterns in one passage is the signal.

## Where this applies in coding-os

**Apply to:** `README.md` and every doc a non-contributor reads · release notes and `CHANGELOG` prose (not the generated entries) · launch announcements, blog and forum posts · PR bodies · Hub UI copy · issue replies.

**Do not apply to:** task files under `docs/tasks/**` (their contract is G/W/T, not prose) · work-log lines · commit messages (Rule 24 owns those: ≤100-char title, ≤3 body lines) · code comments (Rule 12 owns those) · generated artifacts under `tests/golden/**` and `src/core/rules/{dimension-registry,skill-enforcement}.md`.

**Never touch inside a rewrite:** code blocks, inline code spans, YAML frontmatter, link targets, command strings, schema field names, and any watched phrase appearing inside a quotation or as the subject of discussion rather than in use.

## Community posts — the failure modes that actually cost us

Measured, not hypothetical: four posts published from this repo in August 2026. One scored 1.0 upvote ratio; one scored **0.13** and drew *"please go back to linkedin"* and *"this is ai, JUST WRITE LIKE A PERSON"*. The two comments written the same day, in the same voice, scored +4 and +2. Format and framing carried the difference, not vocabulary.

- **Thought-leader titles.** `I stopped doing X and started doing Y` and `here is what actually stuck` are LinkedIn templates. A flat, boring title outperforms: name the artifact and the number.
- **A formula repeated across posts.** `Honest state:` opened all four. One reader quoted it back mockingly. Any phrase reused verbatim across posts becomes the tell, however good it was once.
- **Performed humility.** "I put the number that hurts me in the README because leaving it out would have been dishonest" reads as marketing. State the number. Drop the commentary about your own integrity.
- **Essay architecture in a community post.** Setup → what survived → what I got wrong → honest state is a content-marketing skeleton. A post to a forum is a message, not an article.
- **Length.** 500 words about your own project reads as an ad; 150 words answering someone's question reads as help.

The correction is not better disguise. Shorter, flatter, and answering a real question beats a polished essay.

## Return modes

**Pasted text** (default): the draft, a short list of remaining patterns, then the final rewrite.
**File** (user names a path): run the full process, write only the final text, then summarize. Prose only — code, frontmatter, data, and link targets unchanged.
**Embedded** (another task calls this skill for a PR body, commit, or doc): return the final text only.

## Process

**Two passes, and the second one is not optional.** Reading this skill before drafting does not produce clean prose; it produces a draft that is wrong in fewer places. Treat the first draft as suspect by default and audit it against the pattern list as a separate act.

### Pass 1 — draft

1. Read the source and mark each pattern.
2. Draft. Read it aloud. Check rhythm, concrete detail, plain verbs (*is*, *has*), and formality level.
3. State each point naturally rather than patching one flagged phrase at a time. If a sentence stays awkward, rewrite the paragraph around its point.

### Pass 2 — audit the draft you just wrote

Re-read the finished text against [references/patterns.md](references/patterns.md) as if someone else wrote it. Name every hit by number. At minimum check:

- §9 "not X, it's Y" and clipped negative tails
- §10 forced groups of three
- §14 em and en dashes — **search for the characters**, do not eyeball it
- §31 forced punchlines and manufactured gravity
- §33 fake-candid openings
- §34 answering objections nobody raised
- §36 uniform sentence and paragraph length

Then two checks the pattern list cannot make for you:

- **Cross-draft formula.** Any construction reused from another draft in this session is a tell even when each instance is fine. One session shipped `Honest state:` in four posts and a reader quoted it back mockingly.
- **Unsourced facts.** Every number, name, and claim must trace to something in this session. "I have seen setups north of 30k" is invention, not voice.

Fix what you found, then record the receipt:

```bash
bash ".$COS_AGENT/hooks/write-state.sh" .humanizer-audit "reviewed:<count>"
```

`enforce-humanizer-audit.sh` blocks the end of any turn that drafted prose without that receipt. Report the findings to the user in the reply; `reviewed:0` is a claim you are making to them, not a formality.

**Why the gate exists.** During the session that produced this skill, the agent loaded it, drafted three posts, and shipped text carrying §9 in all three, an em dash, an invented statistic, and a fix it claimed to have applied but had not. Every one of those survived because "skill loaded" was mistaken for "skill applied" — the same shape as a test command that runs nothing and exits 0.

## Source

Adapted from [blader/humanizer](https://github.com/blader/humanizer), whose patterns derive from Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) maintained by WikiProject AI Cleanup. Guardrails against manufactured personality and against asserting that a text was model-written are adapted from [vercel/eve](https://github.com/vercel/eve) (Apache-2.0). Full provenance and the changes made when vendoring: [NOTICE](NOTICE).

> Copyright (c) 2025 Siqi Chen. Licensed under the MIT License. Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files to deal in it without restriction, subject to including the above copyright notice and this permission notice in all copies or substantial portions. The software is provided "as is", without warranty of any kind.

That notice is inline rather than linked because a consumer project receives `SKILL.md` on its own: the `references/` directory and `NOTICE` stay in the kernel.

Wikipedia's underlying point: a language model "guesses what should come next," so it converges on "the most statistically likely result that applies to the widest variety of cases." Every pattern below is a shape of that average.
