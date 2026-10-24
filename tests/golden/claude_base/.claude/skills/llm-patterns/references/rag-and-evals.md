<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# RAG, Evals, Guardrails, Cost

> P: Build an LLM feature that is grounded, measurable, guarded, and affordable.
> R: Adding retrieval, writing an eval suite, hardening an agent loop, or controlling spend.
> S: The raw Claude SDK wiring — that's the claude-sdk-integration skill (present on meta-stack projects).
> N: [SKILL.md](../SKILL.md), [llm-feature-checklist.md](../assets/llm-feature-checklist.md)

> Nav: [Skill](../SKILL.md)

## RAG — retrieve, then generate

```
query → embed → vector search (top-k) → rerank → stuff context → generate → cite
```

Ground answers in retrieved sources to cut hallucination. The levers: chunk size
(too big = noise, too small = lost context), `k` (recall vs context budget),
**reranking** (a cross-encoder over the top-k beats raw vector order), and
**citations** (return the source so the answer is verifiable). Retrieval quality
caps answer quality — a great model over bad chunks still lies.

## Evals — you can't improve what you don't measure

```
dataset of (input, expected/rubric) → run → score (exact / LLM-judge / rubric) → track over time
```

Build an eval set from real failures. Score with exact-match where possible,
an LLM-judge with a rubric where not. Gate changes on the eval (a prompt tweak
that helps one case may regress five). Treat the eval suite like a test suite —
[testing-strategy](../../testing-strategy/SKILL.md) applies.

## Guardrails — assume the model and the input are adversarial

- **Structured output**: force a schema (tool/JSON mode) and validate it — never
  parse free text you can avoid.
- **Prompt-injection defense**: treat retrieved/user content as data, delimit it
  clearly, and never let it override system instructions; don't grant the model
  tools it doesn't need.
- **Output validation**: check the result before acting on it (a generated SQL
  query is still untrusted — parameterize, sandbox).
- **Refusal/fallback**: a deterministic path when the model fails or low-confidence.

## Cost + latency control

```bash
python3 scripts/estimate_tokens.py prompt.txt --rate 3.00   # budget before sending
```

- **Prompt caching** for stable prefixes (system prompt, few-shot) — large savings
  on repeated calls.
- **Model tiering**: a small/cheap model for easy cases, escalate to a large one
  only when needed.
- **Cap context**: retrieve `k` you need, not the whole corpus; trim history.
- **Stream** for perceived latency; **batch** offline work.

Track tokens + cost per request as a metric ([observability](../../observability/SKILL.md)) —
an unmonitored LLM feature is an unbounded bill.
