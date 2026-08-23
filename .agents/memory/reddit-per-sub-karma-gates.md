---
name: reddit-per-sub-karma-gates
description: Reddit posts die to per-subreddit karma minimums that global karma does not satisfy; check the sub's automod gate before writing the post.
metadata:
  type: project
---

Posting the coding-os benchmark to r/LocalLLaMA on 2026-08-23 was removed by
AutoModerator within seconds: "you do not have sufficient karma on r/LocalLLaMa
... gain the minimum of 5 karma and then re-post". The account `u/coding-os` had
66 global karma at the time, which counted for nothing — the gate is **karma
earned inside that subreddit**.

**Why:** large subs gate on per-sub karma specifically because global karma is
farmable elsewhere. Sub rules pages do not list these thresholds; only automod's
removal message names them, so they are invisible until a post is already burnt.

**How to apply:** before writing a post for a new sub, land 2-3 substantive
comments there first and confirm they scored. Removal is not permanent — the
same post can be resubmitted once the threshold clears, so a removed post is a
delay, not a loss. Contrast r/ClaudeAI, where `automod_filtered` is the
*normal* path for every post ("your post will be reviewed shortly") and clears
on its own within minutes — `removed_by_category` alone does not distinguish a
rejection from a queue, so re-check before reacting.

Related: [[run-the-feature-not-just-its-tests]] — same shape of error, a status
field that reads like a verdict when it is only a queue state.
