<!-- domain:UNIVERSAL | layer:reference | ssot:false | updated:2026-08-24 -->
# AI writing patterns — full catalogue

Purpose: the 36 patterns behind `Skill humanizer`, each with a before/after.
Read when: rewriting or reviewing prose a human will read outside the repo.
Skip when: you need the process and guardrails only — those live in [SKILL.md](../SKILL.md).
Read next: [false-positives.md](false-positives.md)

Adapted from [blader/humanizer](https://github.com/blader/humanizer) (MIT, © 2025 Siqi Chen); source patterns from Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing). See [NOTICE](../NOTICE).

One pattern alone proves nothing. Several in one passage is the signal. Check [false-positives.md](false-positives.md) before acting on any single hit.

## Content patterns

### 1. Inflated claims about importance and legacy

**Watch:** stands/serves as, is a testament/reminder, a vital/significant/crucial/pivotal/key role/moment, underscores/highlights its importance/significance, reflects broader, symbolizing its ongoing/enduring/lasting, contributing to the, setting the stage for, marking/shaping the, represents/marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted
**Problem:** an ordinary detail is presented as a major change, a legacy, or a broad trend.
**Before:** The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. This initiative was part of a broader movement across Spain to decentralize administrative functions.
**After:** The Statistical Institute of Catalonia was established in 1989, part of a wider decentralization of administrative functions in Spain.

### 2. Name-dropping to prove importance

**Watch:** independent coverage, local/regional/national media outlets, written by a leading expert, active social media presence
**Problem:** a list of well-known publications or follower counts stands in for context.
**Before:** Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence with over 500,000 followers.
**After:** Her views have been cited in The New York Times and the BBC.

Keep a citation that says what the person said and where. Do not invent context to justify a shorter version.

### 3. Shallow analysis with -ing phrases

**Watch:** highlighting/underscoring/emphasizing…, ensuring…, reflecting/symbolizing…, contributing to…, cultivating/fostering…, encompassing…, showcasing…
**Problem:** a trailing `-ing` clause makes a plain fact sound deeper than it is.
**Before:** The temple's palette of blue, green, and gold resonates with the region's natural beauty, symbolizing Texas bluebonnets and the Gulf of Mexico, reflecting the community's deep connection to the land.
**After:** The temple is painted blue, green, and gold, colors meant to evoke Texas bluebonnets and the Gulf of Mexico.

### 4. Sales language

**Watch:** boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies, commitment to, nestled, in the heart of, groundbreaking (figurative), renowned, breathtaking, must-visit, stunning, seamless, robust, powerful
**Problem:** the prose reads as an advertisement, especially for places, products, and organizations.
**Before:** Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and stunning natural beauty.
**After:** Alamata Raya Kobo is a town in the Gonder region of Ethiopia.

### 5. Vague sources

**Watch:** Industry reports, Observers have cited, Experts argue, Some critics argue, studies show, several sources/publications (when few cited)
**Problem:** a claim is assigned to unnamed experts, critics, reports, or observers.
**Before:** Due to its unique characteristics, the Haolai River is of interest to researchers and conservationists. Experts believe it plays a crucial role in the regional ecosystem.
**After:** Researchers and conservationists study the Haolai River for its unusual characteristics.

Name a real source when the text supplies one. Otherwise remove the claim. Never invent a source.

### 6. Formulaic challenges and outlook sections

**Watch:** Despite its… faces several challenges, Despite these challenges, Challenges and Legacy, Future Outlook
**Problem:** a stock section about challenges or future growth repeats vague claims instead of adding facts.
**Before:** Despite its industrial prosperity, Korattur faces challenges typical of urban areas, including traffic congestion and water scarcity. Despite these challenges, with its strategic location and ongoing initiatives, Korattur continues to thrive.
**After:** Korattur has recurring traffic congestion and water shortages.

## Language and grammar patterns

### 7. Overused AI vocabulary

**Watch:** actually, additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, gate/gated/gating (figurative — keep established technical usage), highlight (verb), interplay, intricate, key (adjective), landscape (abstract), leverage, pivotal, quietly, showcase, tapestry, testament, underscore, utilize, valuable, vibrant
**Problem:** these appear far more often in generated text than in most writing, especially in clusters.
**Before:** Additionally, a distinctive feature of Somali cuisine is the incorporation of camel meat. An enduring testament to Italian colonial influence is the widespread adoption of pasta in the local culinary landscape, showcasing how these dishes have integrated into the traditional diet.
**After:** Somali cuisine also includes camel meat. Pasta dishes, introduced during Italian colonization, remain common.

### 8. Avoiding is and are

**Watch:** serves as / stands as / marks / represents [a], boasts / features / offers [a]
**Problem:** simple verbs are replaced with longer phrases that add nothing.
**Before:** Gallery 825 serves as LAAA's exhibition space for contemporary art. The gallery features four separate spaces and boasts over 3,000 square feet.
**After:** Gallery 825 is LAAA's exhibition space for contemporary art. It has four separate spaces and over 3,000 square feet.

The rewrite keeps "four separate spaces" and the "over 3,000" lower bound. Tightening a verb must not tighten a number.

### 9. Not X but Y, and clipped negative endings

**Problem:** overuse of "Not only… but…", "It's not just X, it's Y", and clipped tails such as "no guessing" in place of a clause.
**Before:** It's not just about the beat riding under the vocals; it's part of the aggression and atmosphere. It's not merely a song, it's a statement.
**After:** The heavy beat adds to the aggressive tone.
**Before:** The options come from the selected item, no guessing.
**After:** The options come from the selected item, so the user does not have to guess.

### 10. Forced groups of three

**Problem:** ideas are padded into triads to sound complete.
**Before:** The event features keynote sessions, panel discussions, and networking opportunities. Attendees can expect innovation, inspiration, and industry insights.
**After:** The event includes talks and panels. There is also time for informal networking between sessions.

### 11. Synonym cycling and repeated sentence openings

**Problem:** repetition is handled by rule instead of by ear — the same subject gets renamed every sentence, or several sentences open on the same word.
**Before (cycling):** The protagonist faces many challenges. The main character must overcome obstacles. The central figure eventually triumphs. The hero returns home.
**After:** The protagonist faces many challenges but eventually triumphs and returns home.
**Before (repeated openings):** She noted the door. She noted the lock on it. She filed both away.
**After:** She noted the door and its lock, then filed both away.

Fix the repeated *pattern*, not the repeated word. The surviving sentence may still begin with "She."

### 12. False from X to Y ranges

**Problem:** "from X to Y" where X and Y do not form a range.
**Before:** Our journey through the universe has taken us from the singularity of the Big Bang to the grand cosmic web, from the birth of stars to the enigmatic dance of dark matter.
**After:** The book covers the Big Bang, star formation, and current theories about dark matter.

### 13. Passive voice and missing subjects

**Problem:** who acts is hidden or dropped.
**Before:** No configuration file needed. The results are preserved automatically.
**After:** You do not need a configuration file. The system preserves the results automatically.

## Style patterns

### 14. Em and en dashes

**Rule:** the final text contains no em dashes (—) or en dashes (–) unless the writer's sample uses them. Replace with a period, comma, colon, or parentheses, or rewrite. Check spaced dashes (` — `) and double hyphens (` -- `) too.
**Before:** The term is promoted by Dutch institutions—not by the people themselves. You don't say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official documents.
**After:** The term is promoted by Dutch institutions, not by the people themselves. You don't say "Netherlands, Europe" as an address, yet this mislabeling continues in official documents.

Before returning a rewrite, search for `—` and `–` explicitly. This is the one pattern worth verifying mechanically.

### 15. Decorative bold

**Problem:** words and phrases are bolded with no reason a reader can infer.
**Before:** It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and tools such as the **Business Model Canvas (BMC)**.
**After:** It blends OKRs, KPIs, and tools like the Business Model Canvas.

Keep bold for an interface label or one genuinely critical fact.

### 16. Lists of bold mini-headings

**Problem:** every list item opens with a bold label and a colon, and the content after it restates the label.
**Before:**
> - **User Experience:** The user experience has been significantly improved with a new interface.
> - **Performance:** Performance has been enhanced through optimized algorithms.
> - **Security:** Security has been strengthened with end-to-end encryption.

**After:** The update improves the interface, speeds up load times, and adds end-to-end encryption.

### 17. Title Case headings

**Before:** `## Strategic Negotiations And Global Partnerships`
**After:** `## Strategic negotiations and global partnerships`

### 18. Emoji as decoration

**Problem:** emoji are attached to headings and list items for texture.
**Before:** 🚀 **Launch Phase:** The product launches in Q3 · 💡 **Key Insight:** Users prefer simplicity
**After:** The product launches in Q3. User research showed a preference for simplicity.

### 19. Curly quotation marks

**Problem:** curly quotes (“…”) where the writer or the target format uses straight quotes ("…"). Weak on its own — most editors auto-curl. Counts only alongside other tells.

## Chatbot residue

### 20. Assistant text left in the answer

**Watch:** I hope this helps, Of course!, Certainly!, You're absolutely right, Would you like…, Want me to…, Want me to give examples?, Should I continue, let me know, here is a…
**Before:** Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand on any section.
**After:** The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest.

### 21. Knowledge-limit disclaimers and plausible guesses

**Watch:** as of [date], up to my last training update, while specific details are limited/scarce, based on available information, not publicly available, maintains a low profile, keeps personal details private, prefers to stay out of the spotlight, likely [grew up/studied/began], it is believed that
**Problem:** the model notes that it could not find a source, then fills the gap with something plausible.
**Before:** Information about her early life is not publicly available, suggesting she maintains a low profile. She likely grew up in a middle-class household, which shaped her later interest in education reform.
**After:** Her early life is not documented in the available sources. (Or cut the section.)

State what the source does not show. Never present a guess as a fact.

### 22. Praising the user before answering

**Before:** Great question! You're absolutely right that this is a complex topic. That's an excellent point about the economic factors.
**After:** The economic factors you mentioned are relevant here.

## Filler, rhetoric, and rhythm

### 23. Filler phrases

- "In order to achieve this goal" → "To achieve this"
- "Due to the fact that it was raining" → "Because it was raining"
- "At this point in time" → "Now"
- "In the event that you need help" → "If you need help"
- "The system has the ability to process" → "The system can process"
- "It is important to note that the data shows" → "The data shows"

### 24. Stacked qualifiers

**Watch:** to be fair, it's also possible, could potentially, might arguably, in some cases it may, this is an inference
**Problem:** successive edits pile on hedges until every claim sounds uncertain. Remove caveats that only repair an earlier overstatement.
**Before:** It could potentially possibly be argued that the policy might have some effect on outcomes.
**After:** The policy may affect outcomes.

### 25. Generic positive endings

**Before:** The future looks bright for the company. Exciting times lie ahead as they continue their journey toward excellence.
**After:** (Cut it. End on the last concrete fact. If the source states real plans, use those.)

### 26. Hyphenated pairs everywhere

**Watch:** third-party, cross-functional, client-facing, data-driven, decision-making, well-known, high-quality, real-time, long-term, end-to-end
**Rule:** hyphenate before a noun (`a high-quality report`), not after (`the report is high quality`).

### 27. Pretending to reveal a deeper truth

**Watch:** the real question is, at its core, in reality, what really matters, fundamentally, the deeper issue, the heart of the matter
**Before:** The real question is whether teams can adapt. At its core, what really matters is organizational readiness.
**After:** The question is whether teams can adapt. That mostly depends on whether the organization is ready to change its habits.

### 28. Announcing the next point

**Watch:** let's dive in, let's explore, let's break this down, here's what you need to know, now let's look at, without further ado, quick note, heads up, before I forget
**Problem:** the text announces what it is about to say instead of saying it. Recasting the announcement into a casual register does not fix it — the announcement itself has to go.
**Before:** Let's dive into how caching works in Next.js. Here's what you need to know.
**After:** Next.js caches data at multiple layers, including request memoization, the data cache, and the router cache.
**Before (casual):** One thing that bit me hard, so pay attention to this part: the webpack dev server doesn't send the CORS header by default.
**After:** The webpack dev server doesn't send the CORS header by default.

### 29. A heading restated in its first sentence

**Signs to watch:** a heading followed by a one-line paragraph that simply restates it before the real content begins.

**Before:** `## Performance` followed by "Speed matters." then the real content.
**After:** `## Performance` followed directly by "When users hit a slow page, they leave."

### 30. Writing about the previous version

**Problem:** documentation and comments describe what changed instead of what is. Keep change talk in changelogs, release notes, and migration guides.
**Before:** This function was added to replace the previous approach of iterating through all items, which caused O(n²) performance.
**After:** This function uses a hash map for O(1) lookups.

### 31. Forced punchlines and manufactured gravity

**Watch:** Read that again · Let that sink in · periods between single words ("every. single. day.") · a lone ALL-CAPS word for emphasis
**Problem:** each sentence is turned into a closing line, or the reader is instructed to feel weight the claim has not earned. One short sentence adds emphasis; a row of fragments feels staged.
**Before:** Then AlphaEvolve arrived. It had no preference for symmetry. No aesthetic prior. No nostalgia for human taste. The old rules were gone.
**After:** AlphaEvolve changed the search because it did not favor symmetry or human-looking designs, which made some older assumptions less useful.

### 32. Formulaic sayings

**Watch:** X is the Y of Z, X becomes a trap, X is not a tool but a mirror, the language of, the currency of, the architecture of
**Before:** Symmetry is the language of trust. Efficiency becomes a trap when teams forget the human layer.
**After:** Symmetric layouts often feel more predictable to users. Teams can over-optimize workflows and miss how people actually use them.

### 33. Fake-candid openings

**Watch:** Honestly? · Look, · Here's the thing · The thing is · Let's be honest · Real talk · I'm no expert but · This might be controversial but — used as standalone hooks or staged pauses before an ordinary point.
**Before:** Is it worth the price? Honestly? It depends on how often you'll use it.
**After:** Whether it's worth the price depends on how often you'll use it.

"Honestly" or "look" mid-sentence is ordinary speech. The tell is the theatrical standalone opener.

### 34. Answering objections nobody raised

**Watch:** This isn't (mainly/really) about, I'm not saying/arguing/trying to, To be clear, Don't get me wrong, This is not to say, You could argue/frame this differently but, Some might say… but
**Problem:** the text defends against an objection that appears nowhere in it — usually residue from the drafting conversation.
**Before:** This isn't mainly about prompt length, and I'm not arguing that documentation doesn't matter. You could categorize the problem another way, but the issue is whether the agent can use the instruction when it acts.
**After:** The issue is whether the agent can use the instruction when it acts.

Remove only the undefended defense. A named, answered objection stays. A direct claim ("the API is not thread-safe") is not this pattern.

### 35. Rejecting alternatives nobody proposed

**Watch:** a tempting option/approach would be, one might be tempted to, an obvious approach would be, you might think… but, it would be easy to just, Some would suggest
**Problem:** an option no reader would consider is raised, dismissed in a clause, and never mentioned again.
**Before:** Session tokens are rotated every 24 hours. A tempting approach would be to rotate them by restarting the auth service on a cron job, but that would drop every active session. Rotation happens in place, and clients refresh transparently.
**After:** Session tokens are rotated every 24 hours, in place, and clients refresh transparently.

One rejected option can be legitimate in a design doc. Several short unrelated rejections is the stronger sign.

### 36. Uniform sentence and paragraph length

**Problem:** patterns 1-35 work at word and phrase level, and prose can satisfy every one of them while still reading generated, because the sentences settle into one narrow length band and the paragraphs come out the same size with the same internal shape. [false-positives.md](false-positives.md) lists length variety as a signal worth protecting; this is its generative counterpart.
**Fix:** read the draft aloud and listen for a flat cadence. Merge two short sentences that carry one idea; split a long one that carries three. Let one paragraph run to six sentences and the next to one, when the content justifies it. Do not impose variety on prose that is already uneven.
