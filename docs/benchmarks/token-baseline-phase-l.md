<!-- domain:ALL | layer:benchmark | ssot:true | updated:2026-04-20 -->
# Token Cost Baseline — Phase L

> Measured via `scripts/measure_token_baseline.py`.
> Token ≈ `wc -w × 1.3` (conservative OpenAI-style estimate).

## Components

| Component | Words | Approx. tokens | File |
|---|---:|---:|---|
| CLAUDE.md (always loaded) | 4,364 | 5,673 | `AGENTS.md` |
| Pre-L legacy task (example) | 317 | 412 | synthetic |
| Post-L lean task (example) | 144 | 187 | synthetic |

## Startup context (CLAUDE.md + one active task)

| Era | Tokens | Δ |
|---|---:|---|
| Pre-Phase-L | **6,085** | baseline |
| Post-Phase-L | **5,860** | **+225 (-3.7%)** |

## Interpretation

- Phase L saves ~**4%** of startup context per active task.
- Over a 10-turn session touching 3 task files, the compound savings are ~**675 tokens**.
- Lean task files enforce Rule 15 (pointers, not specs): `lint-task.sh` blocks > 3k tokens, warns > 1.5k.

## Notes

- CLAUDE.md itself is ~8k tokens — it dominates startup regardless.
- The `task-authoring.md.tmpl` fragment adds ~120 tokens to CLAUDE.md as of L.9; the savings above already factor this in.
- These numbers are **per-task**, not per-session; a session with three tasks in rotation sees the savings multiplied.
