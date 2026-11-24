---
name: ask-before-spending-another-plan
description: Never spend the operator's Codex or other provider plan to verify a change without asking; a smoke needs a one-line prompt, not a full review.
metadata:
  type: feedback
---

On 2026-11-24 three full gpt-6.1-sol reviews of a 60k-character diff ran on the operator's ChatGPT plan in 17 minutes to "verify the openai-codex upgrade", with supervision off. One such review on this repo reads about 530k to 590k input tokens. The operator's 5-hour Codex limit ran out and they found out from the limit, not from me.

**Why:** the operator pays for each provider separately and watches each limit. Supervision off is their statement that no other provider should run. A verification run is still a run on their plan.

**How to apply:** before any live call to a provider other than the current session's, say which plan it uses and what it costs, and ask. To prove an adapter works, send a one-line prompt ("reply OK") through the same code path, never a real review. Related: [[run-the-feature-not-just-its-tests]].
