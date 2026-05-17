<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-16 -->
# Intent Vocabulary — How the System Understands Human Intent

Purpose: Single source of truth for the FA + EN verbs that humans use to express **exhaustive** scope ("همه", "all", "completely") and the formal predicates the agent must satisfy when those verbs appear. The agent reads natural language — the system must translate that language into measurable contracts.

Read when: authoring a hook that reads user intent · debugging why an exhaustive-intent prompt was not detected · adding a new vocabulary entry · extending intent detection to a new language.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

**SSOT for vocabulary:** this file. Hooks (`detect-exhaustive-intent.sh`, `intent-primer.sh`) and the completion guardian (`completion_guardian.py`) read from `_helpers/extract_intent.py` which mirrors the tables below. When you change a verb or predicate here, also update `src/core/hooks/_helpers/extract_intent.py` — tests in `tests/test_intent_vocabulary_sync.py` enforce the mirror.

## Why this exists

A class of premature-completion bugs comes from the agent interpreting "fix همه" / "fix all" loosely — fixing 6 of 10 instances and declaring done. The agent's cultural intuition says "I addressed the main cases." The user's cultural intuition says "every single one, until zero remain." Both are valid readings; only one is what the user meant.

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
| `coverage=100%` | Every category declared at start has been covered | `categories_declared ⊆ categories_covered` in EvidenceBundle |
| `iterate-until-zero-residual` | Loop fix → re-grep → repeat until 0 hits remain | `counts_after == 0` for every category |
| `all-categories-evidence` | Every category has a non-empty evidence row | each row in `audit-<slug>.md` has `Files scanned`, `Hits before`, `Verified=yes` |
| `exhaustive-grep` | Search ran across the full repo, not a subset | `files_searched` non-empty and includes repo-wide pattern |
| `per-item-evidence` | Each item independently verified, not batch-asserted | per-item row in audit table with own `Verified` cell |
| `strict-zero-residual` | After fix, an independent re-grep finds zero hits | reviewer subagent re-grep returns 0 |

## Exhaustive verbs — Persian (FA)

These words signal the user wants **every** instance addressed, not a representative sample.

| Verb / phrase | Predicate(s) | Notes |
|---|---|---|
| همه (hame) | `coverage=100%` + `iterate-until-zero-residual` | "all" — strongest single-word marker |
| همگی (hamegi) | `coverage=100%` | "all of them" |
| تک به تک (tak be tak) | `per-item-evidence` | "one by one" — implies independent verification |
| تا اخر (ta akhar) | `iterate-until-zero-residual` | "until end" — temporal exhaustion |
| تا دونه آخر (ta doone akhar) | `iterate-until-zero-residual` + `strict-zero-residual` | "to the last one" — extremely strong |
| هر چی (har chi) | `exhaustive-grep` | "every single" — search-side exhaustion |
| هر چیزی (har chizi) | `exhaustive-grep` | "anything / everything" |
| همه جا (hame ja) | `exhaustive-grep` | "everywhere" — spatial exhaustion |
| کامل (kamel) | `all-categories-evidence` | "complete" — coverage-side exhaustion |
| کاملا (kamelan) | `all-categories-evidence` + `strict-zero-residual` | "completely" |
| صد در صد (sad dar sad) | `strict-zero-residual` | "100%" — explicit numeric |
| هیچی نپره (hichi naparre) | `strict-zero-residual` | "nothing slips through" |
| هیچی جا نمونه (hichi ja namune) | `strict-zero-residual` | "nothing left behind" |
| بدون استثنا (bedoon-e estesna) | `strict-zero-residual` | "without exception" |
| تمام (tamam) | `coverage=100%` | "all / entire" |
| تمامی (tamami) | `coverage=100%` | "the entirety of" |

## Exhaustive verbs — English (EN)

| Verb / phrase | Predicate(s) | Notes |
|---|---|---|
| all | `coverage=100%` + `iterate-until-zero-residual` | strongest single-word marker |
| every | `exhaustive-grep` + `per-item-evidence` | per-instance scope |
| everything | `exhaustive-grep` | object-side exhaustion |
| everywhere | `exhaustive-grep` | spatial exhaustion |
| every single | `per-item-evidence` + `strict-zero-residual` | per-item + strict |
| completely | `all-categories-evidence` + `strict-zero-residual` | coverage + strict |
| comprehensive / comprehensively | `coverage=100%` + `all-categories-evidence` | coverage scope |
| exhaustive / exhaustively | `coverage=100%` + `iterate-until-zero-residual` | by definition |
| thorough / thoroughly | `all-categories-evidence` | depth marker |
| deep audit / deep review | `all-categories-evidence` + `per-item-evidence` | depth + per-item |
| until done | `iterate-until-zero-residual` | temporal loop |
| no exceptions | `strict-zero-residual` | hard zero |
| none missed | `strict-zero-residual` | hard zero |
| 100% | `strict-zero-residual` | explicit numeric |
| down to the last one | `iterate-until-zero-residual` + `strict-zero-residual` | strongest natural phrase |
| each and every | `per-item-evidence` | per-item emphasis |
| top to bottom | `coverage=100%` + `all-categories-evidence` | spatial coverage |

## Scope verbs

Exhaustive vocab alone is not a trigger. Exhaustive vocab **combined with a scope verb** is the trigger — "all my dreams" is not an audit; "fix all the failing tests" is.

| Verb (EN) | Verb (FA) | Action class |
|---|---|---|
| find | پیدا کن, جستجو کن | search |
| fix | فیکس کن, درست کن, اصلاح کن | repair |
| update | آپدیت کن, به‌روز کن | replace |
| rename | rename, تغییر نام بده | rename |
| migrate | migrate, منتقل کن | migrate |
| audit | audit, بررسی کن | audit |
| verify | verify, وریفای کن | verify |
| check | چک کن, بررسی کن | verify |
| sweep | sweep, جارو کن | search |
| search | جستجو کن, سرچ کن | search |
| review | review, بررسی کن | audit |
| refactor | refactor | restructure |
| remove | حذف کن, پاک کن | delete |
| replace | جایگزین کن | replace |

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

- "همه چیز ok بود" / "all good" → no scope verb. Not exhaustive intent.
- "all my code is broken" → "all" is descriptive, not imperative. Heuristic: exhaustive verb must precede or follow scope verb within a clause (~20 tokens window).
- "find me one example" → "find" is scope verb but "one" overrides exhaustive default.
- "fix the test" (singular, no exhaustive marker) → not triggered.

The classifier uses a 20-token sliding window for co-occurrence rather than whole-prompt match. Tests in `tests/test_intent_classifier.py` enforce the window contract.

## Extending the vocabulary

When adding a new verb:

1. Add row to the FA or EN table above with the predicate it implies.
2. Mirror the addition in `src/core/hooks/_helpers/extract_intent.py::EXHAUSTIVE_VERBS_FA` / `EXHAUSTIVE_VERBS_EN`.
3. Add a positive test in `tests/test_intent_vocabulary.py` covering the new verb with a scope verb.
4. Add a false-positive test ensuring the new verb without a scope verb does NOT trigger.
5. Update the SessionStart card in `src/core/hooks/intent-primer.sh` if the verb is one a typical user would say often (keep card under 300 tokens — high-frequency verbs only).
6. Re-run `make verify-hooks` and `uv run pytest tests/test_intent_*.py -q`.

When extending to a new language: add a new table section, mirror in `extract_intent.py` with a `LANG_<code>` constant, add language detection (or always-on multi-language matching — current design).

## Cultural note

Persian and English speakers express exhaustion differently. Persian leans on doubled markers ("تک به تک" — "one by one" literally "single to single"; "تا دونه آخر" — "until the last seed"). English leans on amplifiers ("every single", "down to the last"). Both are valid. The vocabulary table captures the common surface forms; the predicates capture the underlying invariant the agent must satisfy. The invariant is language-independent — only the surface form differs.

This is the same principle by which legal contracts work: parties may speak different languages, but the obligations are the same. Intent vocabulary is the system's way of converting natural language into obligations the agent can be held to.

## See also

- [docs/governance/critical-rules.md § Rule 22](../governance/critical-rules.md#rule-22--anti-overengineering) — don't over-engineer the predicate set.
- [docs/engineering/mcp-error-envelope.md](mcp-error-envelope.md) — EvidenceBundle schema the predicates depend on.
- [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml) — hooks that fire on detected intent.
- [src/core/hooks/_helpers/extract_intent.py](../../src/core/hooks/_helpers/extract_intent.py) — implementation mirror of the tables above.
- [src/core/skills/thinking_os/SKILL.md](../../src/core/skills/thinking_os/SKILL.md) — when Cognitive Cycle invokes intent reading.
