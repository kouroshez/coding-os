<!-- domain:META | layer:reference | ssot:true | updated:2026-06-05 -->
# Agent-Memory Recipes — Read + Learn Loop

> P: The mechanical `cos_*` sequences for recalling memory and running the learn loop.
> R: Recalling a past pattern in the Orient phase, or reinforcing a pattern after using it.
> S: The memory *policy* (what belongs in memory, hygiene) — that's the co-shipping rule src/core/rules/memory.md.
> N: [SKILL.md](../SKILL.md), [memory-checklist.md](../assets/memory-checklist.md)

> Nav: [Skill](../SKILL.md)

Writes are automatic (edit-derived capture); the agent mostly **reads**. Every
signature below is verified against src/core/thinking_os/server.py. Policy (four-layer
model, what to store, privacy) is SSOT in [memory.md](../../../rules/memory.md).

## Read — recall in the Orient phase

```
cos_search("query about past patterns", min_confidence=0.3, since_days=90)
cos_details(pattern_id=1234, source="learned_patterns")   # source ∈ observations|learned_patterns|task_outcomes
cos_learn_suggest(domain="BACKEND", complexity="COMPLICATED", limit=5)   # ranked patterns for the task
cos_timeline(days=14)                                       # what changed lately
```

`min_confidence=0.3` drops decayed low-trust rows; `since_days=90` for "recent"
questions. Zero hits with those filters → fall through to docs (`cos_doc_search`)
or code (`cos_graph_*`).

## Write — automatic, not freeform

Observations are captured automatically by the PostToolUse hook for every
Write/Edit/MultiEdit (capture.py derives title/narrative/memory_type/impact,
sanitizes, dedups, inserts). To force-capture one file where the hook did not
fire (e.g. Codex):

```
cos_observation_record(file_path="src/core/X.py", tool_name="Edit")
```

There is no freeform record — title, confidence and impact are derived, never
supplied. Record discipline is about WHAT you edit, not a manual call.

## The learn loop (cross-session compounding)

```
cos_learn_extract(min_occurrences=3)                 # corpus scan → mint learned_patterns
cos_learn_suggest(domain=, complexity=, limit=5)     # surface ranked patterns for the active task
cos_learn_validate(pattern_id=42, was_helpful=True)  # reinforce (LTP) / decay (LTD) confidence
```

Confidence is system-computed: validating a pattern that held raises it, one that
didn't lowers it. This is how the N-th session gets faster than the 1st.

## Trust the code over memory

Memory is frozen at write time; code evolves. If recall says "`foo` does X" but a
`Read` shows it doesn't, the memory is stale — trust the code. Every `cos_search`
result carries the record timestamp; re-verify when it predates the file's last change.
