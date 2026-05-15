Record the Complexity Gate (Cynefin × dimensions) for the current task before any code edit.

The Complexity Gate is mandatory per [Rule 7](docs/governance/critical-rules.md) and [core/rules/thinking_os.md](core/rules/thinking_os.md). It tells future hooks + reviewers what cognitive depth this task warrants. Skip → `enforce-skill.sh` may block edits on COMPLICATED+ paths.

Steps:
1. If `$ARGUMENTS` is provided in the form `Q1 Q2` (e.g. `COMPLICATED 3`), use it directly. Otherwise infer from the conversation:
   - **Q1 (Cynefin):** `CLEAR` (known fix) | `COMPLICATED` (known type, needs design) | `COMPLEX` (unknown answer, needs experiment) | `CHAOTIC` (broken now, act first) | `CONFUSION` (decompose first).
   - **Q2 (dimensions):** integer count of distinct concerns this task touches (auth + DB + UI = 3).
2. State your classification + one-sentence rationale.
3. Persist via:
   ```
   bash core/skills/thinking_os/scripts/classify.sh --q1 <Q1> --q2 <Q2>
   ```
   This writes `$COS_AGENT_DIR/.thinking_os-gate` and unblocks downstream skill/edit hooks.
4. If `Q1` is `COMPLICATED` or `COMPLEX`, invoke `Skill thinking_os` for the full Zoom cycle.
5. If `Q1` is `CHAOTIC`, treat as an incident — load `Skill incident-response`, stabilize first.

Output format:
```
Classification: <Q1> <Q2>
Rationale: <one sentence>
Next step: <Plan | Zoom cycle | Incident stabilization>
```
