<!-- domain:BACKEND | layer:asset | ssot:false | updated:2026-06-04 -->
# LLM Feature Checklist

Run before shipping a feature that calls an LLM.

## Grounding (if it answers from data)
- [ ] Retrieval (RAG) grounds answers in sources; citations returned.
- [ ] Chunking + `k` + reranking tuned; retrieval quality measured.

## Measurement
- [ ] An eval set built from real inputs/failures.
- [ ] Changes gated on the eval (no prompt tweak ships without a green eval).
- [ ] Quality tracked over time, not vibes.

## Guardrails
- [ ] Structured output (schema/tool mode) + validation — not free-text parsing.
- [ ] User/retrieved content treated as data, delimited; can't override system instructions.
- [ ] Model output validated before acting (generated SQL/code is still untrusted).
- [ ] Deterministic fallback/refusal path for failures + low confidence.

## Cost & latency
- [ ] `python3 scripts/estimate_tokens.py <prompt> --rate <usd_per_1m>` — budget known.
- [ ] Prompt caching on stable prefixes; model tiering for easy cases.
- [ ] Context capped (retrieve what's needed; trim history).
- [ ] Tokens + cost per request exported as a metric (observability).
- [ ] Streaming for UX; batching for offline work.
