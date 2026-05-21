<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-13 -->
# Critical Rules — Full Text

Purpose: Canonical expansion of every numbered rule listed in `AGENTS.md` § Critical Rules. AGENTS.md keeps the 1-line summary; this file is the rationale + enforcement reference.
Read when: A hook just blocked an action and cited a rule number, OR you are about to touch governance / hooks / MCP surfaces and need the full rationale.
Skip when: You only need the 1-line summary — read AGENTS.md instead.
Read next: [docs-system.md](docs-system.md), [agent-workflow.md](agent-workflow.md), [decision-records.md](decision-records.md)

> Nav: [Docs Index](../00-index.md) | [Governance Index](./)

---

## Conventions

- Every rule below uses the same 4-row structure: **Rule** · **Why** · **How (enforcement)** · **Where**.
- “Hook” means a script under `src/core/hooks/` registered in `src/core/hooks/registry.yaml`; the renderer surfaces it in each adapter.
- Rule numbers are stable — never reorder, only append.

---

## Rule 0 — Docs-first

- **Rule:** Every code `Write`/`Edit` must trace to a doc path recorded in `$COS_AGENT_DIR/.doc-anchor`.
- **Why:** Code without a documented spec is technical debt the moment it merges. The anchor forces an answer to “which doc does this code implement?”.
- **How:** Hook `enforce-doc-anchor.sh` (PreToolUse Write|Edit) blocks code writes when `.doc-anchor` is empty or stale.
- **Where:** [src/core/hooks/enforce-doc-anchor.sh](../../src/core/hooks/enforce-doc-anchor.sh)

## Rule 1 — Never hardcode `.claude/` in `core/`

- **Rule:** Use `$COS_AGENT_DIR` (per-agent), `$COS_STATE_DIR` (shared), `$COS_DB_PATH`. Session-id at `$COS_AGENT_DIR/session-id`. Sid string format: `ses-{agent}-YYYYMMDD-…`.
- **Why:** `.claude/` is one of N adapter dirs (`.codex/`, `.cursor/`, …). Hardcoding breaks adapter parity (P2).
- **How:** Hook `block-bad-patterns.sh` greps `src/core/**` for `.claude/`. Adapter resolves env at session start via `src/core/hooks/cos-env.sh`.
- **Where:** [src/core/hooks/cos-env.sh](../../src/core/hooks/cos-env.sh)

## Rule 2 — MCP tool names use `cos_*` prefix

- **Rule:** Every public MCP tool exposed by thinking_os/graph_os/board_os is named `cos_<verb>_<noun>` (e.g. `cos_doc_search`, `cos_task_create`).
- **Why:** Single namespace; consumer projects can grep one prefix; MCP clients can filter.
- **How:** Tests in `src/core/thinking_os/tests/test_tool_naming.py` reject non-prefixed exports.
- **Where:** [docs/governance/mcp-tool-inventory.md](mcp-tool-inventory.md)

## Rule 3 — Hooks source `cos-env.sh`

- **Rule:** Every hook starts with `source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true`.
- **Why:** Resolves `$COS_*` env vars once. Removes per-hook env discovery code.
- **How:** Hook `verify-hook-shape.sh` rejects new hooks missing the source line.
- **Where:** [src/core/hooks/cos-env.sh](../../src/core/hooks/cos-env.sh)

## Rule 4 — Scripts search config chain

- **Rule:** Lookup order is `$COS_STATE_DIR/domain-config.json` → `infrastructure/scripts/domain-config.json`.
- **Why:** Per-project state wins; repo defaults fall back. Same file shape in both locations.
- **How:** Helper `src/core/hooks/find-config.sh` encodes the chain. Scripts call it; never reinvent the lookup.
- **Where:** `src/core/hooks/find-config.sh`

## Rule 5 — Path resolution: `.resolve()` before `.relative_to()`

- **Rule:** On macOS `/tmp` symlinks to `/private/tmp`; relative-path math without `.resolve()` raises `ValueError`.
- **Why:** Subtle CI breakage; tests pass on Linux, fail on macOS.
- **How:** Pylint custom rule `cos-path-resolve` flags `Path(...).relative_to(...)` without preceding `.resolve()`.
- **Where:** `src/core/thinking_os/utils/paths.py`

## Rule 6 — Fire-and-forget needs explicit exception handling

- **Rule:** Background work uses an `_<name>_safe()` wrapper with `except Exception as exc: logger.debug("…", exc_info=exc)`. Bare `except: pass` is rejected.
- **Why:** Silent swallows hide bugs; `logger.debug` keeps the stack trace recoverable without spamming.
- **How:** Hook `block-bad-patterns.sh` rejects bare `except` in any `_safe()` helper.
- **Where:** [src/core/thinking_os/tools/_shared.py](../../src/core/thinking_os/tools/_shared.py)

## Rule 7 — Governance edits require explicit task name

- **Rule:** Edits to `AGENTS.md`, `.coding-os/`, `src/core/rules/`, `src/core/hooks/` require the active task to mention `docs-update` or `governance` in title or labels.
- **Why:** Governance drift is the most expensive drift to undo; every change must be auditable to a task.
- **How:** Hook `block-protected-files.sh` reads the active TASK title/labels and refuses unauthorized edits.
- **Where:** [src/core/hooks/block-protected-files.sh](../../src/core/hooks/block-protected-files.sh)

## Rule 8 — Multi-step verification = Python, never bash heredoc inside `$(...)` with `uv run`

- **Rule:** Write a `.py` file and call `subprocess.run([...], timeout=N)`. Do not pipe a heredoc into `uv run python -`.
- **Why:** Bash 5.3.9 + `uv run` + heredoc = silent deadlock. Documented incident: hook-startup hang, 2026-03.
- **How:** Hook `block-uv-heredoc.sh` rejects the pattern at PreToolUse Bash.
- **Where:** [src/scripts/verify_phase_c_e2e.py](../../src/scripts/verify_phase_c_e2e.py)

## Rule 9 — Schema migrations are append-only

- **Rule:** New tables → migration `vN+1`. Never edit a past migration’s body.
- **Why:** Migrations run once per consumer DB; editing the past silently diverges schemas.
- **How:** Hook `block-migration-conflict.sh` rejects duplicate version numbers in `src/core/thinking_os/database.py`.
- **Where:** [src/core/thinking_os/database.py](../../src/core/thinking_os/database.py)

## Rule 10 — Regenerate derived artifacts

- **Rule:** Edit source, then run `make regen-rules` + `make manifest-regen` + `make regen-adapter-templates`. Never hand-edit derived files.
- **Why:** `src/core/scaffold_manifest.json`, `src/core/rules/dimension-registry.md`, `src/core/rules/skill-enforcement.md`, `adapters/{claude,codex}/*.template.*`, `tests/golden/**` are generated.
- **How:** Hook `regen-reminder.sh` (PostToolUse Write|Edit on source files) prints the regen command. `warn-template-drift.sh` flags hand-edits to derived files.
- **Where:** [Makefile](../../Makefile)

## Rule 11 — No hardcoded stack/adapter literals in `src/cli/*.py`

- **Rule:** No quoted `"django"` / `"claude"` strings in CLI code. Read from `src/templates/<stack>/stack.yaml` / `src/adapters/<agent>/adapter.yaml`.
- **Why:** Adding a new stack/adapter must be a yaml change, never a code change.
- **How:** Hook `block-hardcoded-literals.sh` greps `src/cli/*.py`. Test `tests/test_no_hardcoded_stacks.py` enforces in CI.
- **Where:** [src/cli/main.py](../../src/cli/main.py)

## Rule 12 — Comments by exception, not by default

- **Rule:** Default to NO comments and NO docstrings. Code reads like prose;
  good names and small functions remove the need. Add a comment only when
  the WHY is non-obvious: a hidden constraint, subtle invariant, workaround
  for a specific bug, or behavior that would surprise a reader.
- **Exception — public MCP tools (`@mcp.tool` decorated functions):**
  ONE-line docstring is permitted because FastMCP exposes it as the tool
  description to the client. Keep it under 80 chars. No multi-section
  PURPOSE/INPUT/OUTPUT/DEPENDENCIES/NOTES blocks — they bloat tokens and
  duplicate what arg names and types already convey.
- **Why:** Comments rot, names don't (well-named code stays self-describing).
  Long header blocks balloon every file and burn tokens on every read for
  zero runtime benefit. Past convention was wrong; legacy `PURPOSE / INPUT
  / OUTPUT / DEPENDENCIES / NOTES` blocks are a tech debt to be removed
  when touching a file, not a pattern to extend.
- **How:** No automated enforcement (was never in any active hook). Code
  review rejects new PURPOSE/INPUT/OUTPUT blocks; `block-bad-patterns.sh`
  already blocks bare `except: pass`-style noise.
- **Where:** [src/core/skills/clean-code/SKILL.md](../../src/core/skills/clean-code/SKILL.md) §Self-Documenting

## Rule 13 — MCP tool response envelope

- **Rule:** Every `cos_*` tool returns via `ok(data)` / `fail(category, message)`. Wrapped in `@safe_tool`. Categories: `transient | validation | permission | not_found | unavailable | internal`.
- **Why:** Single-shape envelope means clients can parse without per-tool branching; categories drive retry vs. abort.
- **How:** Test `src/core/thinking_os/tests/test_envelope.py` rejects non-conforming returns.
- **Where:** [src/core/thinking_os/tools/_shared.py](../../src/core/thinking_os/tools/_shared.py) · contract: [docs/engineering/mcp-error-envelope.md](../engineering/mcp-error-envelope.md)

## Rule 14 — Tasks are pointers, not specs

- **Rule:** `docs/tasks/TASK-NNN-slug.md` MUST NOT inline content already in `docs/**` / `src/core/rules/**` / `AGENTS.md`. Four orthogonal axes: `swimlane` · `kind` (8-value enum) · `epic` · `labels` (never kind values).
- **Why:** Tasks rot; canonical docs are reviewed. Inlining causes silent divergence.
- **How:** Hook `lint-task.sh` warns >1.5k tokens, blocks >3k. `cos task-validate` rejects label values that collide with kind enum.
- **Where:** [src/core/board_os/parser.py](../../src/core/board_os/parser.py)

## Rule 15 — Role chain composed for COMPLICATED+ tasks

- **Rule:** Call `cos_compose_chain(signals)`; result written to `.coding-os/<agent>/.roles` + `.role`. Roles ARE the 11 formulas, addressed by semantic id: `researcher · analyst · architect · documenter · implementer · reviewer · debugger · security_auditor · deployer · observer · refactorer`.
- **Why:** Hard problems need a sequenced chain of formulas. Composing once at task start avoids mid-task formula thrash.
- **How:** Routing yaml at `src/core/thinking_os/roles/`, prompts at `src/core/thinking_os/agents/`. Source spec citation `Formula 1..11` retained only in `formulas-en.md`.
- **Where:** [src/core/thinking_os/roles/](../../src/core/thinking_os/roles/) · [src/core/thinking_os/agents/](../../src/core/thinking_os/agents/)

## Rule 16 — Formula dispatch produces typed EvidenceBundle

- **Rule:** Every formula records via `cos_supervise_record_output(formula_id, output_json)` matching the formula’s `output_schema` Pydantic model.
- **Why:** Without a typed output, multi-formula chains can’t verify hand-off correctness; supervisor can’t replay.
- **How:** `cos_supervise` validates the JSON against the formula schema before storing.
- **Where:** [src/core/thinking_os/dispatchers/](../../src/core/thinking_os/dispatchers/)

## Rule 17 — Situational Paths override role chain

- **Rule:** When `.coding-os/<agent>/.situation` is set, the situational path wins over the composed role chain. Six situations: `incident-response · onboarding · scope-change · external-integration · design-review · existing-project-takeover`.
- **Why:** “Production is on fire” needs a different sequence than a feature build, even if the dimensions look similar.
- **How:** Dispatcher reads `.situation` before `.roles`.
- **Where:** [src/core/thinking_os/situations/](../../src/core/thinking_os/situations/)

## Rule 18 — Task reconciliation is mandatory before implementation

- **Rule:** For every non-trivial user request: first check existing tasks via `cos_task_board` / `cos task-show`. Reuse when matched; otherwise create one, fill `Outcome` / `Read First` / `Acceptance`, then move `in_progress → testing → complete` (or `blocked` with explicit blocker).
- **Why:** Otherwise tasks duplicate, board state diverges from reality, and progress can’t be measured.
- **How:** No hook (yet) — convention enforced via review + memory.
- **Where:** [docs/governance/task-lifecycle.md](task-lifecycle.md)

## Rule 19 — Docs are the contract — never extend code beyond doc spec

- **Rule:** If the doc says “registration takes username, password, name”, do NOT add a `birthdate` field because it “feels needed”. Edit the doc first, then the code.
- **Why:** Code-first changes silently extend the contract; consumers read the doc, not the diff.
- **How:** Pair: Rule 0 anchors new code TO a doc going IN; `enforce-doc-sync.sh` (PostToolUse Write|Edit|MultiEdit) surfaces docs that drifted going OUT — three signals: (a) symbol removed/renamed + doc still mentions it, (b) signature changed (param-count diff), (c) doc mtime older than code AND mentions a current symbol. Collaborates with thinking_os FTS5 index for accurate doc lookup + graph_os `cos_graph_references` for impact context. WARN class — agent must act.
- **Where:** [src/core/hooks/enforce-doc-sync.sh](../../src/core/hooks/enforce-doc-sync.sh)

## Rule 20 — Test discipline: matrix command only, never broad sweep mid-task

- **Rule:** `pytest tests/ -q` runs 743 integration tests (~6 min). Match changed files → matrix command (15s–90s) per [test-discipline.md](../../src/core/rules/test-discipline.md). Full sweep is permitted **only** pre-merge/release, cross-cutting refactor touching ≥3 matrix rows, or when the user explicitly asks. Single-test debug: `pytest path::TestClass::test_name -v` before re-running the file.
- **Why:** Six minutes per change × N iterations = the user waits and productivity dies.
- **How:** Convention + Rule. SSOT is `src/core/rules/test-discipline.md`; AGENTS.md § Verification Matrix mirrors it.
- **Where:** [src/core/rules/test-discipline.md](../../src/core/rules/test-discipline.md)

## Rule 21 — Never use `isolation: "worktree"` in this repo

- **Rule:** Subagent dispatch is allowed **only** for read-only research / inventory / verification (Agent tool without `isolation`). Write work runs single-agent on the main working tree. Never pass `isolation: "worktree"` to the Agent tool.
- **Why:** Past worktree runs left orphaned `.claude/worktrees/<slug>/` plus locked `worktree-*` branches with broken `.git` links — required manual `find .git/worktrees/...` cleanup and deadlocked sessions.
- **How:** Convention. The `worktree-orchestration` skill has been removed from `src/core/skills/` and `src/templates/_base/base.yaml`. Reviewers reject re-introduction.
- **Where:** [AGENTS.md](../../AGENTS.md) § Critical Rules

## Rule 22 — Anti-overengineering

- **Rule:** Solve the problem in front of you with the smallest correct change. Reuse what exists, do not speculate, do not duplicate. Five sub-rules: (1) **Reuse-First** — search graph / docs / grep before writing anything; (2) **No-Speculation** — build only what the current task requires, no "might need it later"; (3) **Diff-Minimal** — smallest correct change, bug-fix-only commits, no ride-along refactors; (4) **No-Premature-Abstraction (Rule of Three)** — extract only when three divergent call sites need it; (5) **Defer-by-Default** — ask "what can I remove?" at task close. Applies to **every artifact** — code, docs, hooks, skills, templates, tests, CLI, configs.
- **Why:** Every line written is paid for forever. Over-engineering grows surface area, hides intent, slows review, and trains the next agent that bloat is the house pattern. In an enterprise codebase the cumulative cost dominates any single addition.
- **How:** Convention — automated detection is too false-positive-prone (numeric thresholds, abstraction counts, file additions). Enforcement is the reality-check matrix in the rule body, code review, and `cos_search` observations that surface prior incidents. Tactical instances (no abbreviations, no magic numbers, no positional booleans, nesting ≤ 2) are enforced through the `clean-code` skill.
- **Where:** [src/core/rules/anti-overengineering.md](../../src/core/rules/anti-overengineering.md). Cross-links: [api-contract-discipline.md](../../src/core/rules/api-contract-discipline.md), [test-discipline.md](../../src/core/rules/test-discipline.md), [clean-code skill](../../src/core/skills/clean-code/SKILL.md).

---

## Rule Index (quick lookup)

| # | Rule | Hook |
|---|---|---|
| 0 | Docs-first | enforce-doc-anchor.sh |
| 1 | No `.claude/` in core | block-bad-patterns.sh |
| 2 | `cos_*` prefix | test_tool_naming.py |
| 3 | Hooks source cos-env.sh | verify-hook-shape.sh |
| 4 | Config chain | find-config.sh |
| 5 | `.resolve()` before `.relative_to()` | pylint custom |
| 6 | Fire-and-forget exception handling | block-bad-patterns.sh |
| 7 | Governance task name | block-protected-files.sh |
| 8 | No bash heredoc with `uv run` | block-uv-heredoc.sh |
| 9 | Append-only migrations | block-migration-conflict.sh |
| 10 | Regenerate derived artifacts | regen-reminder.sh + warn-template-drift.sh |
| 11 | No hardcoded literals in cli/ | block-hardcoded-literals.sh |
| 12 | Function header convention | lint-function-header.sh |
| 13 | MCP envelope `ok`/`fail` | test_envelope.py |
| 14 | Tasks are pointers | lint-task.sh |
| 15 | Role chain composed | (none — convention) |
| 16 | Typed EvidenceBundle | cos_supervise validation |
| 17 | Situational Paths override | (none — dispatcher logic) |
| 18 | Task reconciliation | (none — convention) |
| 19 | Docs are contract | enforce-doc-sync.sh |
| 20 | Test discipline | (none — convention) |
| 21 | No worktree isolation | (none — convention) |
| 22 | Anti-overengineering | (none — convention; clean-code skill for tactical) |
