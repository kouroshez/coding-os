<!-- domain:META | layer:asset | ssot:false | updated:2026-06-04 -->
# Claude SDK Integration Checklist

Run when editing src/adapters/claude/** SDK / dispatcher code.

## Model + caching
- [ ] Model ids are current — `python3 scripts/check_model_ids.py <files>` → `clean`.
- [ ] Model selected by tier intent (opus/sonnet/haiku), not a magic string scattered around.
- [ ] Prompt caching on stable prefixes (system prompt, tools) — the big cost lever.
- [ ] Max tokens / temperature set deliberately, not defaults-by-accident.

## Tool-use loop
- [ ] The tool-use loop handles `stop_reason: tool_use` → run tool → feed result → continue.
- [ ] Tool errors returned to the model as tool_result, not thrown away.
- [ ] Loop bounded (max iterations) — no infinite tool ping-pong.

## Session + errors
- [ ] Session lifecycle correct (create → reuse → close); no leaked sessions.
- [ ] API errors classified (rate limit → backoff; overloaded → retry; 4xx → fail fast).
- [ ] The dispatcher protocol contract honored (every adapter satisfies the same shape — P8).

## Autonomy boundary (P8)
- [ ] No adapter SDK imported from `src/core/**`.

## Verify
- [ ] `make bench-sdk` / `make smoke-sdk` (or the dispatcher smoke) green.
- [ ] `uv run pytest tests/test_adapters.py -q`.
