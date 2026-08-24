---
name: loading-a-skill-is-not-applying-it
description: Invoking a skill before drafting does not produce clean output; only a separate, receipted second pass over the finished text does.
metadata:
  type: feedback
---

On 2026-08-24 the humanizer skill was loaded before drafting three Reddit posts.
All three shipped carrying the patterns that skill names: `not X, it's Y` in
every one, an em dash, an invented statistic ("setups north of 30k") sourced from
nothing, and a fix claimed in chat that had never been applied. The operator's
words: an agent that has used the skill is still wrong roughly nine times in ten,
so the text must be re-checked against the skill after it is written.

**Why:** loading a skill changes what the model attends to while generating; it
does not inspect the artifact. That is the same shape as a test command that
collects nothing and exits 0 — a step that looks done and produced no signal.
Self-assessment inside the generating pass is not a check.

**How to apply:** treat pass 1 as suspect by default. After any prose is written,
re-read it against `references/patterns.md` as if a stranger wrote it, name every
hit by number, then record `write-state.sh .humanizer-audit "reviewed:<n>"`.
`enforce-humanizer-audit.sh` (Stop, blocking) refuses to end the turn otherwise.
Two checks the pattern list cannot make: a construction reused across drafts in
the same session, and any number that no source in the session supports.

The same lesson generalises past prose: a verification script's own assertion can
be wrong. Two of three "FAIL"s in the audit script written that day were brittle
string matches (`November 30, 2022` vs `30 November 2022`), not real defects — a
bad check reports failure as confidently as a real one.

Related: [[run-the-feature-not-just-its-tests]] · [[dry-run-in-repo-before-trusting-units]]
