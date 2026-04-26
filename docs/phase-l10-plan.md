<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-25 -->
# Phase L.10 — Transition Gates (DoR / DoD / Override Audit)

Purpose: SSOT for the policy-as-data architecture that replaces ad-hoc bash regex gates with a single, kind-aware, audit-trailed validator covering Definition of Ready, Definition of Done, WIP, and verify suites.
Read when: editing any `core/hooks/enforce-*.sh`, `core/board_os/workflow.py`, or adding a new gate type.

---

## Problem statement

Today, every transition gate in coding-os is implemented independently in bash:

| Gate | Where | Issue |
|---|---|---|
| Active task | `enforce-task-start.sh` | OK |
| Doc anchor | `enforce-doc-anchor.sh` | OK |
| Memory check | `enforce-memory-check.sh` | OK |
| Complexity | `thinking_os-gate.sh` | OK |
| Body completeness | **none** | **gap: `(fill in: …)` placeholder accepted into `in_progress`** |
| WIP cap | `enforce-wip-limit.sh` | OK after TASK-096 fix |
| Task size | `lint-task.sh` | hard-coded thresholds |
| Verify suite | `enforce-verify.sh` | hard-coded customer paths (`backend/`, `frontend/app/*/checkout/*`) — completely wrong for coding-os meta-repo and any non-django/nextjs consumer |
| Override audit | **none** | `COS_*_OVERRIDE=1` is silent — no row in `task_status_history` |

Five separate bash scripts, three with hardcoded thresholds, none kind-aware, no audit trail for bypasses. This violates enterprise gate-design principles and rule P2 (agent-agnostic, data-driven).

## Goals (G/W/T-level)

- **G1.** A single declarative `transition-gates.yaml` is the SSOT for *what* a task must satisfy at each transition.
- **G2.** Rules are *per-kind* (bug ≠ feature ≠ chore ≠ spike ≠ docs ≠ refactor ≠ test ≠ security).
- **G3.** A pure-python validator (`core/board_os/transition_gates.py`) returns `ValidationResult{verdict, messages}`; no bash regex.
- **G4.** Both PreToolUse hook *and* `workflow.transition()` call the same validator (no drift).
- **G5.** Every override (`COS_*_OVERRIDE=1`) requires a reason and lands in `task_status_history.override_reason`.
- **G6.** `enforce-verify.sh` derives "changed domains" from the active stack manifest (`core/scaffold_manifest.json`) and the consumer's `domain-config.json`, not from hardcoded customer paths.
- **G7.** Test matrix covers (kind × transition × verdict) with per-persona evaluation (F1 Researcher, F2 Designer, F8 Tester, F11 Refactorer).

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  transition-gates.yaml  (SSOT — declarative policy)                │
│  ├─ definition_of_ready: {default, by_kind: {bug,feature,...}}     │
│  ├─ definition_of_done:  {default, by_kind}                        │
│  ├─ wip_limits:          {in_progress, testing, emergency}         │
│  ├─ size_limits:         {warn_tokens, block_tokens}               │
│  └─ overrides:           {require_reason, audit_to}                │
└────────────────┬───────────────────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────────────────┐
│  core/board_os/transition_gates.py   (pure-python validator)       │
│  ├─ load_gates_config(path) → GatesConfig (Pydantic)               │
│  ├─ validate_transition(task, body, new_status, kind) →            │
│  │       ValidationResult(verdict={PASS,WARN,BLOCK}, messages)     │
│  └─ apply_override(reason, actor) → AuditEntry                     │
└────────┬──────────────────────────────────────┬────────────────────┘
         │ called from                          │ called from
         ▼                                      ▼
┌─────────────────────────┐          ┌──────────────────────────────┐
│ core/hooks/             │          │ core/board_os/workflow.py    │
│ enforce-task-body.sh    │          │ transition(... )             │
│ enforce-verify.sh       │          │ → calls validate_transition  │
│ enforce-wip-limit.sh    │          │ → records audit on override  │
│ lint-task.sh            │          │                              │
│ (thin bash → python -m) │          │                              │
└─────────────────────────┘          └──────────────────────────────┘
                 │                                    │
                 └────────────┬───────────────────────┘
                              ▼
                  ┌──────────────────────────┐
                  │ task_status_history v20  │
                  │ + override_reason TEXT   │
                  │ + override_actor TEXT    │
                  └──────────────────────────┘
```

## Schema (TASK-103)

```yaml
# core/board_os/transition-gates.yaml
version: 1

definition_of_ready:
  # gate when transitioning INTO in_progress
  default:
    sections:
      Outcome:
        required: true
        min_chars: 20
        forbid_patterns: ["(fill in", "TBD", "..."]
      Acceptance:
        required: true
        required_subitems: ["**Given**", "**When**", "**Then**"]
        forbid_patterns: ["(fill in", "..."]
      "Read First":
        required: true
        min_items: 1

  by_kind:
    chore:
      sections:
        Outcome: { required: true, min_chars: 15 }
        # acceptance + read first not strictly required for chores
    bug:
      sections:
        Outcome: { required: true, min_chars: 20 }
        "Repro Steps": { required: true, min_chars: 30 }
        Acceptance: { required: true }
    spike:
      sections:
        Outcome: { required: true, min_chars: 15 }
        # discovery — only outcome
    docs:
      sections:
        Outcome: { required: true, min_chars: 15 }
        "Read First": { required: true }
    refactor:
      sections:
        Outcome: { required: true, min_chars: 20 }
        "Read First": { required: true }
        Acceptance: { required: true }
    test:
      sections:
        Outcome: { required: true, min_chars: 20 }
        Acceptance: { required: true }
    security:
      sections:
        Outcome: { required: true, min_chars: 20 }
        "Read First": { required: true }
        Acceptance: { required: true }
        "Threat Model": { required: true, min_chars: 30 }
    feature:
      # uses default (full DoR)

definition_of_done:
  default:
    require_verify: true
    verify_max_age_seconds: 1800
    require_work_log: true
  by_kind:
    docs:
      require_verify: false
    chore:
      require_work_log: false

wip_limits:
  in_progress: 1
  testing: 3
  emergency: 2

size_limits:
  warn_tokens: 1500
  block_tokens: 3000

overrides:
  require_reason: true
  min_reason_chars: 15
  audit_to: task_status_history.override_reason
```

## Validator API (TASK-104)

```python
# core/board_os/transition_gates.py
from pydantic import BaseModel, Field
from enum import Enum

class Verdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"

class ValidationMessage(BaseModel):
    code: str            # stable identifier e.g. "DOR_OUTCOME_MISSING"
    severity: Verdict    # PASS messages omitted
    field: str | None
    message: str         # human-readable, contains repair hint

class ValidationResult(BaseModel):
    verdict: Verdict
    messages: list[ValidationMessage] = Field(default_factory=list)

    @property
    def blocked(self) -> bool: return self.verdict is Verdict.BLOCK

def validate_transition(
    *,
    task_id: str,
    kind: str,
    body: str,
    new_status: str,
    config: GatesConfig,
) -> ValidationResult: ...
```

Per-kind rules merge with `default` (deep-merge: kind keys override default keys field-by-field).

## Hook + Workflow Integration (TASK-105)

```
PreToolUse Edit on docs/tasks/TASK-*.md  ──►  enforce-task-body.sh
                                                    │
                                                    ▼ (thin bash dispatcher)
                                          python -m core.board_os.transition_gates_cli check
                                                    │
                                                    ▼
                                          parse stdin → ValidationResult
                                                    │
                                            BLOCK ──┘  exit 2 with messages
                                            WARN  ──┘  exit 0, banner to stderr
                                            PASS  ──┘  exit 0 silent
```

`workflow.transition()` calls the same `validate_transition()` so MCP-driven moves (`cos_task_move`) get the same gate as bash-driven Edits.

## Override Audit (TASK-107)

Migration v20 adds two columns to `task_status_history`:
```sql
ALTER TABLE task_status_history ADD COLUMN override_reason TEXT;
ALTER TABLE task_status_history ADD COLUMN override_actor TEXT;
```

When a hook or `workflow.transition()` is bypassed via `COS_DOR_OVERRIDE`, `COS_VERIFY_OVERRIDE`, or `COS_WIP_OVERRIDE`, the validator demands a reason via `COS_OVERRIDE_REASON="..."`. The reason is stamped into the next history row.

Without `COS_OVERRIDE_REASON` (or with reason < `min_reason_chars`), the override is **rejected** — silent bypass becomes impossible.

## Data-driven verify (TASK-100)

`enforce-verify.sh` reads `core/scaffold_manifest.json::stacks[*].verify_suites` (per-stack) and the consumer's `domain-config.json::path_globs` (per-project), and matches changed files against those globs. No hardcoded `frontend/app/*/checkout/*` strings anywhere.

## Migration of legacy gates (TASK-101, TASK-102)

- `enforce-wip-limit.sh` → calls `validate_transition()` (cap config moved to `transition-gates.yaml::wip_limits`).
- `lint-task.sh` → calls `validate_transition()` (token thresholds moved to `transition-gates.yaml::size_limits`).
- `enforce-verify.sh` → granular: lint only files touched in `git diff`, not repo-global.

## Test matrix (G7)

For each kind (8 kinds: feature, bug, chore, spike, docs, refactor, test, security):
- DoR pass case (full body)
- DoR block case (missing field)
- DoR warn case (placeholder remnants under threshold)
- DoD pass case
- DoD block case (no verify)
- override flow (with + without reason)
- override-reject case (reason too short)

= 7 × 8 = **56 parametric pytest cases** in `core/board_os/tests/test_transition_gates.py`.

Plus persona evaluation per implemented TASK:
- **F1 Researcher**: did we examine prior art (Jira validators, Linear workflows, GH Issue templates)?
- **F2 Designer**: are concerns separated; are extension points obvious?
- **F8 Tester**: edge cases covered; failure modes named?
- **F11 Refactorer**: minimal duplication; no dead branches?

Each TASK closes only when **all four personas** issue PASS, with the score recorded in its work log.

## Acceptance per TASK

- **TASK-103**: `transition-gates.yaml` validates against `GatesConfig` Pydantic model; round-trip yaml→model→yaml is identity; bad YAML produces structured error not crash.
- **TASK-104**: 56 parametric tests pass; mutation tests (rename a section header) flip verdict from PASS→BLOCK.
- **TASK-105**: PreToolUse on `docs/tasks/TASK-*.md` with placeholder `(fill in:` blocks; same task with full body passes; MCP `cos_task_move --to in_progress` produces same verdict.
- **TASK-107**: migration v20 applies cleanly; existing rows backfill `override_reason=NULL`; bypass without reason returns BLOCK from validator.
- **TASK-100**: `enforce-verify.sh` on coding-os meta-repo correctly identifies that `core/hooks/*.sh` change requires `make verify-hooks`, not `lint-backend`. Zero hardcoded paths in script.
- **TASK-101**: existing wip-limit + size-limit tests still pass after migration; thresholds now configurable from yaml.
- **TASK-102**: `make docs-lint-changed` lints only files in `git diff` (vs `make docs-lint` global).

## Rollback

Each TASK is a self-contained PR. Rollback by reverting the merge. The new gates are additive — old gates stay during shadow run for one week (config: `enforcement_mode: shadow|warn|block`).

## Out of scope (Phase L.11+)

- Multi-tenant override policies (org-level vs project-level rules).
- ML-based gate suggestions (auto-detect placeholder language).
- Web UI for editing `transition-gates.yaml` (current: hand-edit).
