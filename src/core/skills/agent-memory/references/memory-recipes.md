<!-- domain:META | layer:reference | ssot:true | updated:2026-06-04 -->
# Agent-Memory Recipes — Write, Read, Learn Loop

> P: The mechanical `cos_*` sequences for writing, recalling, and tuning agent memory.
> R: Capturing a breakthrough, recalling a past pattern, or running the learn loop.
> S: The memory *policy* (what belongs in memory, hygiene) — that's the co-shipping rule src/core/rules/memory.md.
> N: [SKILL.md](../SKILL.md), [memory-checklist.md](../assets/memory-checklist.md)

> Nav: [Skill](../SKILL.md)

The policy (four-layer model, what to store, privacy) is SSOT in
[memory.md](../../../rules/memory.md) — this is the *how*.

## Write — record an observation

```
cos_observation_record(
  summary="schema migration X needed a backfill before the NOT NULL constraint",
  memory_type="error",          # pattern | workflow | error | decision | discovery
  confidence=0.5,                # default 0.5; raise to 0.8+ only after a 2nd confirmation
  impact=0.6,
)
```

Validate the payload first: `python3 scripts/check_observation.py --file obs.json`
(confidence range, required fields, no PII/secrets). Record breakthroughs, failure
modes, and non-obvious decisions — never recaps, code facts, or git history.

## Read — recall in the Orient phase

```
cos_search("query about past patterns", min_confidence=0.3, since_days=90)
cos_learn_suggest(task_id="TASK-NNN", k=5)     # ranked patterns for this task
cos_timeline(scope="recent")                    # what changed lately
```

`min_confidence=0.3` drops decayed low-trust rows; `since_days=90` for "recent"
questions. Zero hits with those filters → fall through to docs (`cos_doc_search`)
or code (`cos_graph_*`).

## The learn loop (cross-session compounding)

```
cos_learn_extract   → distill observations into a candidate pattern
cos_learn_suggest   → surface ranked patterns for the active task
cos_learn_validate  → confirm/deny a pattern (feeds confidence)
cos_learn_feedback  → reinforce or decay after using it
```

Validating a pattern that held raises its confidence; one that didn't decays it.
This is how the N-th session gets faster than the 1st — the killer feature.

## Trust the code over memory

Memory is frozen at write time; code evolves. If recall says "`foo` does X" but a
`Read` shows it doesn't, the memory is stale — update or delete the observation,
then trust the code. Every `cos_search` result carries the record timestamp;
re-verify when it predates the file's last change.
