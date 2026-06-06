<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-16 -->
# Intent Vocabulary — How the System Understands Human Intent

Purpose: Single source of truth for the English verbs that humans use to express **exhaustive** scope ("all", "every", "completely") and the formal predicates the agent must satisfy when those verbs appear. The system is English-default; the agent reads natural language and translates it into measurable contracts regardless of the language used.

Read when: authoring a hook that reads user intent · debugging why an exhaustive-intent prompt was not detected · adding a new vocabulary entry.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

**SSOT for vocabulary:** this file. Hooks (`detect-exhaustive-intent.sh`, `intent-primer.sh`) and the completion guardian (`completion_guardian.py`) read from `_helpers/extract_intent.py` which mirrors the tables below. When you change a verb or predicate here, also update `src/core/hooks/_helpers/extract_intent.py` — tests in `tests/test_intent_classifier.py` enforce the mirror.

## Why this exists

A class of premature-completion bugs comes from the agent interpreting "fix all" loosely — fixing 6 of 10 instances and declaring done. The agent's intuition says "I addressed the main cases." The user's intuition says "every single one, until zero remain." Both are valid readings; only one is what the user meant.

The fix is not to ask the user to write more precise prompts (that's pushing load the wrong way). The fix is to give the system a **canonical interpretation contract**: when these verbs appear, the agent's done-condition is no longer "I judge it sufficient" — it is "predicate P holds and evidence E proves it."

## How it flows

```
UserPromptSubmit prompt → extract_intent.py → .intent.json
                                                   │
                              ┌────────────────────┤
                              ▼                    ▼
              detect-exhaustive-intent.sh     completion_guardian.py
              (injects "evidence required")  (asserts predicate at Stop)
```

`SessionStart::intent-primer.sh` injects a short card listing the vocabulary at every session boundary so the agent enters every session already primed.

## Predicate contract

Each predicate is a **measurable** condition the agent must satisfy. No predicate is satisfied by self-report — only by evidence captured in the EvidenceBundle (see [mcp-error-envelope.md § EvidenceBundle](mcp-error-envelope.md)).

| Predicate ID | Meaning | Evidence required |
|---|---|---|
| `coverage_100` | Every category declared at start has been covered | `categories_declared ⊆ categories_covered` in EvidenceBundle |
| `iterate_until_zero_residual` | Loop fix → re-grep → repeat until 0 hits remain | `counts_after == 0` for every category |
| `all_categories_evidence` | Every category has a non-empty evidence row | each row in `audit-<slug>.md` has `Files scanned`, `Hits before`, `Verified=yes` |
| `exhaustive_grep` | Search ran across the full repo, not a subset | `files_searched` non-empty and includes repo-wide pattern |
| `per_item_evidence` | Each item independently verified, not batch-asserted | per-item row in audit table with own `Verified` cell |
| `strict_zero_residual` | After fix, an independent re-grep finds zero hits | reviewer subagent re-grep returns 0 |

## Exhaustive verbs (English)

These words signal the user wants **every** instance addressed, not a representative sample. English is the default vocabulary — a deterministic pre-classifier; the agent's own comprehension covers prompts in other languages, so the system stays English-default rather than privileging one non-English vocabulary.

| Verb / phrase | Predicate(s) | Notes |
|---|---|---|
| all | `coverage_100` + `iterate_until_zero_residual` | strongest single-word marker |
| every | `exhaustive_grep` + `per_item_evidence` | per-instance scope |
| everything | `exhaustive_grep` | object-side exhaustion |
| everywhere | `exhaustive_grep` | spatial exhaustion |
| every single | `per_item_evidence` + `strict_zero_residual` | per-item + strict |
| completely | `all_categories_evidence` + `strict_zero_residual` | coverage + strict |
| comprehensive / comprehensively | `coverage_100` + `all_categories_evidence` | coverage scope |
| exhaustive / exhaustively | `coverage_100` + `iterate_until_zero_residual` | by definition |
| thorough / thoroughly | `all_categories_evidence` | depth marker |
| deep audit / deep review | `all_categories_evidence` + `per_item_evidence` | depth + per-item |
| until done | `iterate_until_zero_residual` | temporal loop |
| no exceptions | `strict_zero_residual` | hard zero |
| none missed | `strict_zero_residual` | hard zero |
| 100% | `strict_zero_residual` | explicit numeric |
| down to the last one | `iterate_until_zero_residual` + `strict_zero_residual` | strongest natural phrase |
| each and every | `per_item_evidence` | per-item emphasis |
| top to bottom | `coverage_100` + `all_categories_evidence` | spatial coverage |

## Scope verbs

Exhaustive vocab alone is not a trigger. Exhaustive vocab **combined with a scope verb** is the trigger — "all my dreams" is not an audit; "fix all the failing tests" is.

| Verb | Action class |
|---|---|
| find | search |
| fix | repair |
| update | replace |
| rename | rename |
| migrate | migrate |
| audit | audit |
| verify | verify |
| check | verify |
| sweep | search |
| search | search |
| review | audit |
| refactor | restructure |
| remove | delete |
| replace | replace |

## Trigger rule (formal)

```
intent.exhaustive = True IF:
  ∃ verb ∈ user_prompt where verb ∈ exhaustive_verbs
  AND
  ∃ verb ∈ user_prompt where verb ∈ scope_verbs

Predicates inherited from matched exhaustive verbs are UNIONED.
The strictest predicate wins on conflict.
```

When `intent.exhaustive=True`, the agent enters "evidence-required mode":
1. SessionStart card has already primed agent on what this means.
2. `detect-exhaustive-intent.sh` writes `.intent.json` with `predicates: [...]`.
3. `enforce-audit-artifact.sh` blocks Edit until `docs/tasks/audits/audit-<slug>.md` exists.
4. `cos_supervise_record_output` requires EvidenceBundle satisfying all inherited predicates.
5. Stop event `verify-completion-claim.sh` → `completion_guardian` blocks "done" claim unless all predicates evaluate True.
6. `cos task-done` spawns reviewer subagent for independent re-verification.

## False-positive guards

Some phrasings look exhaustive but are not actually scope+verb pairs:

- "all good" → no scope verb. Not exhaustive intent.
- "all my code is broken" → "all" is descriptive, not imperative. Heuristic: exhaustive verb must precede or follow scope verb within a clause (~20 tokens window).
- "find me one example" → "find" is scope verb but "one" overrides exhaustive default.
- "fix the test" (singular, no exhaustive marker) → not triggered.

The classifier uses a 20-token sliding window for co-occurrence rather than whole-prompt match. Tests in `tests/test_intent_classifier.py` enforce the window contract.

## Extending the vocabulary

When adding a new verb:

1. Add row to the exhaustive-verbs table above with the predicate it implies.
2. Mirror the addition in `src/core/hooks/_helpers/extract_intent.py::EXHAUSTIVE_VERBS_EN`.
3. Add a positive test in `tests/test_intent_classifier.py` covering the new verb with a scope verb.
4. Add a false-positive test ensuring the new verb without a scope verb does NOT trigger.
5. Update the SessionStart card in `src/core/hooks/intent-primer.sh` if the verb is one a typical user would say often (keep card under 300 tokens — high-frequency verbs only).
6. Re-run `make verify-hooks` and `uv run pytest tests/test_intent_*.py -q`.

Language: the table is English-default — a deterministic pre-classifier. The agent's own comprehension reads intent in any language, so the system does not hardcode a second vocabulary.

## Why English-default

The keyword table is a deterministic pre-classifier in English — the lingua franca of the consumer base. The agent's own comprehension reads intent in any language, so the table privileges no single non-English vocabulary. The predicates capture the underlying invariant the agent must satisfy; that invariant is language-independent — only the surface form differs.

This is the same principle by which legal contracts work: parties may speak different languages, but the obligations are the same. Intent vocabulary is the system's way of converting natural language into obligations the agent can be held to.

## See also

- [docs/governance/critical-rules.md § Rule 22](../governance/critical-rules.md#rule-22--anti-overengineering) — don't over-engineer the predicate set.
- [docs/engineering/mcp-error-envelope.md](mcp-error-envelope.md) — EvidenceBundle schema the predicates depend on.
- [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml) — hooks that fire on detected intent.
- [src/core/hooks/_helpers/extract_intent.py](../../src/core/hooks/_helpers/extract_intent.py) — implementation mirror of the tables above.
- [src/core/skills/thinking_os/SKILL.md](../../src/core/skills/thinking_os/SKILL.md) — when Cognitive Cycle invokes intent reading.
