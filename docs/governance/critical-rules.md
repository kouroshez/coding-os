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

- **Rule:** Every code `Write`/`Edit` must trace to a doc path recorded in `$COS_PANEL_DIR/.doc-anchor` (per-panel; falls back to `$COS_AGENT_DIR/.doc-anchor` in pre-TASK-035 layouts via `cos_state_path`).
- **Why:** Code without a documented spec is technical debt the moment it merges. The anchor forces an answer to “which doc does this code implement?”.
- **How:** Hook `enforce-doc-anchor.sh` (PreToolUse Write|Edit) blocks code writes when `.doc-anchor` is empty or stale.
- **Where:** `src/core/hooks/enforce-doc-anchor.sh`

## Rule 1 — Never hardcode `.claude/` in `core/`

- **Rule:** Use `$COS_STATE_DIR` (shared per-project), `$COS_AGENT_DIR` (shared per-agent: `.model`, `.task-mode`, `.swimlane`, `.hooks.log`, `coding-os.db`), `$COS_PANEL_DIR` (private per-panel-of-same-agent: `.task-current`, `.thinking_os-gate`, `.active-skill`, `.doc-anchor`, `.memory-check`, `.zoom-checkpoint`, `.active-formula`, `.learn-suggestions`, `session-id`), `$COS_DB_PATH`. Session-id at `$COS_PANEL_DIR/session-id`. Sid string format: `ses-{agent}-YYYYMMDD-…` (session-context.sh generated) OR runtime UUID (when `cos_panel_upgrade_from_payload` upgrades from stdin). Three-tier scope contract: [docs/engineering/state-files.md](../engineering/state-files.md).
- **Why:** `.claude/` is one of N adapter dirs (`.codex/`, …). Hardcoding breaks adapter parity (P2).
- **How:** Hook `block-bad-patterns.sh` greps `src/core/**` for `.claude/`. Adapter resolves env at session start via `src/core/hooks/cos-env.sh`.
- **Where:** `src/core/hooks/cos-env.sh`

## Rule 2 — MCP tool names use `cos_*` prefix

- **Rule:** Every public MCP tool exposed by thinking_os/graph_os/board_os is named `cos_<verb>_<noun>` (e.g. `cos_doc_search`, `cos_task_create`).
- **Why:** Single namespace; consumer projects can grep one prefix; MCP clients can filter.
- **How:** Tests in `src/core/thinking_os/tests/test_tool_naming.py` reject non-prefixed exports.
- **Where:** [docs/governance/mcp-tool-inventory.md](mcp-tool-inventory.md)

## Rule 3 — Hooks source `cos-env.sh`

- **Rule:** Every hook starts with `source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true`.
- **Why:** Resolves `$COS_*` env vars once. Removes per-hook env discovery code.
- **How:** Hook `verify-hook-shape.sh` rejects new hooks missing the source line.
- **Where:** `src/core/hooks/cos-env.sh`

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
- **Where:** `src/core/thinking_os/tools/_shared.py`

## Rule 7 — Governance edits require explicit task name

- **Rule:** Edits to `AGENTS.md`, `.coding-os/`, `src/core/rules/`, `src/core/hooks/` require the active task to mention `docs-update` or `governance` in title or labels.
- **Why:** Governance drift is the most expensive drift to undo; every change must be auditable to a task.
- **How:** Hook `block-protected-files.sh` reads the active TASK title/labels and refuses unauthorized edits.
- **Where:** `src/core/hooks/block-protected-files.sh`

## Rule 8 — Multi-step verification = Python, never bash heredoc inside `$(...)` with `uv run`

- **Rule:** Write a `.py` file and call `subprocess.run([...], timeout=N)`. Do not pipe a heredoc into `uv run python -`.
- **Why:** Bash 5.3.9 + `uv run` + heredoc = silent deadlock. Documented incident: hook-startup hang, 2026-03.
- **How:** Hook `block-uv-heredoc.sh` rejects the pattern at PreToolUse Bash.
- **Where:** `src/scripts/verify_phase_c_e2e.py`

## Rule 9 — Schema migrations are append-only

- **Rule:** New tables → migration `vN+1`. Never edit a past migration’s body.
- **Why:** Migrations run once per consumer DB; editing the past silently diverges schemas.
- **How:** Hook `block-migration-conflict.sh` rejects duplicate version numbers in `src/core/thinking_os/database.py`.
- **Where:** `src/core/thinking_os/database.py`

## Rule 10 — Regenerate derived artifacts

- **Rule:** Edit source, then run `make regen-rules` + `make manifest-regen` + `make regen-adapter-templates`. Never hand-edit derived files.
- **Why:** `src/core/scaffold_manifest.json`, `src/core/rules/dimension-registry.md`, `src/core/rules/skill-enforcement.md`, `adapters/{claude,codex}/*.template.*`, `tests/golden/**` are generated.
- **How:** Hook `regen-reminder.sh` (PostToolUse Write|Edit on source files) prints the regen command. `warn-template-drift.sh` flags hand-edits to derived files.
- **Where:** `Makefile`

## Rule 11 — No hardcoded stack/adapter literals in `src/cli/*.py`

- **Rule:** No quoted `"django"` / `"claude"` strings in CLI code. Read from `src/templates/<stack>/stack.yaml` / `src/adapters/<agent>/adapter.yaml`.
- **Why:** Adding a new stack/adapter must be a yaml change, never a code change.
- **How:** Hook `block-hardcoded-literals.sh` greps `src/cli/*.py`. Test `tests/test_no_hardcoded_stacks.py` enforces in CI.
- **Where:** `src/cli/main.py`

## Rule 12 — Comments by exception, not by default

- **Rule:** Default to NO comments and NO docstrings. Code reads like prose;
  good names and small functions remove the need. Add a comment only when
  the WHY is non-obvious: a hidden constraint, subtle invariant, workaround
  for a specific bug, or behavior that would surprise a reader.
- **No provenance:** A comment states the timeless WHY, never who/what
  introduced the change. No task IDs (`TASK-123`, `(TASK-123)`, `since TASK-123`),
  phase/plan labels (`Phase 2`, `Phase G`, `P5:`), or gate/work-item codes
  (`(G9)`, `(E1)`, `(B4)`) belong in a comment — `git blame` already records
  provenance, so the ID is meaningless to the next reader and stale the moment
  the work moves on. The same rule kills `TODO`/`FIXME` in committed code: file a
  task (`cos task-create`), don't leave a marker. (A domain identifier the code
  operates on — e.g. a formula id in `hex(F1)` — is not provenance and stays.)
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
- **Where:** `src/core/skills/clean-code/SKILL.md` §Self-Documenting

## Rule 13 — MCP tool response envelope

- **Rule:** Every `cos_*` tool returns via `ok(data)` / `fail(category, message)`. Wrapped in `@safe_tool`. Categories: `transient | validation | permission | not_found | unavailable | internal`.
- **Why:** Single-shape envelope means clients can parse without per-tool branching; categories drive retry vs. abort.
- **How:** Test `src/core/thinking_os/tests/test_envelope.py` rejects non-conforming returns.
- **Where:** `src/core/thinking_os/tools/_shared.py` · contract: [docs/engineering/mcp-error-envelope.md](../engineering/mcp-error-envelope.md)

## Rule 14 — Tasks are pointers, not specs

- **Rule:** `docs/tasks/TASK-NNN-slug.md` MUST NOT inline content already in `docs/**` / `src/core/rules/**` / `AGENTS.md`. Four orthogonal axes: `swimlane` · `kind` (8-value enum) · `epic` · `labels` (never kind values).
- **Why:** Tasks rot; canonical docs are reviewed. Inlining causes silent divergence.
- **How:** Hook `lint-task.sh` warns >1.5k tokens, blocks >3k. `cos task-validate` rejects label values that collide with kind enum.
- **Where:** `src/core/board_os/parser.py`

## Rule 15 — Role chain composed for COMPLICATED+ tasks

- **Rule:** Call `cos_compose_chain(signals)`; result written to `.coding-os/<agent>/.roles` + `.role`. Roles ARE the 11 formulas, addressed by semantic id: `researcher · analyst · architect · documenter · implementer · reviewer · debugger · security_auditor · deployer · observer · refactorer`.
- **Why:** Hard problems need a sequenced chain of formulas. Composing once at task start avoids mid-task formula thrash.
- **How:** Routing yaml at `src/core/thinking_os/roles/`, prompts at `src/core/thinking_os/agents/`. Source spec citation `Formula 1..11` retained only in `formulas-en.md`. **Auto-enforced (TASK-055):** `auto-compose-roles.sh` (UserPromptSubmit) reads the recorded `.thinking_os-gate`; for COMPLICATED/COMPLEX it auto-fires the composer via `_helpers/auto_compose.py`, stamps `.roles`/`.role` AND emits a `compose_done` trace (shared writer `thinking_os/roles_state.py` — `stamp_roles` + `record_compose_traces`, the same pair `cos_compose_chain` calls, so the two paths never drift; TASK-063), so the chain exists — and the Hub Roles panel surfaces it as `composed`/planned — even if the agent never calls the tool by hand. **Rich-signal selection (TASK-057):** the hook pipes the prompt to `formula_composer.signals_from_prompt`, which derives `action`/`domain`/`scope_size` so the chain VARIES per task (debug→debugger, audit→security_auditor, …) instead of collapsing to `['analyst']`. **Phase switch (TASK-057):** `advance-role.sh` (PostToolUse) advances the active `.role` along the chain by work phase (Write/Edit→implementer, test/verify→reviewer), surfaced in the banner as `roles=<active> N/M`. `.roles`/`.role` are per-panel.
- **Where:** `src/core/thinking_os/roles/` · `src/core/thinking_os/agents/` · `src/core/thinking_os/formula_composer.py` (`signals_from_prompt`) · `src/core/hooks/auto-compose-roles.sh` · `src/core/hooks/advance-role.sh` · `src/core/thinking_os/roles_state.py`

## Rule 16 — Formula dispatch produces typed EvidenceBundle

- **Rule:** Every formula records via `cos_supervise_record_output(formula_id, output_json)` matching the formula’s `output_schema` Pydantic model.
- **Why:** Without a typed output, multi-formula chains can’t verify hand-off correctness; supervisor can’t replay.
- **How:** `cos_supervise` validates the JSON against the formula schema before storing.
- **Where:** `src/core/thinking_os/dispatchers/`

## Rule 17 — Situational Paths override role chain

- **Rule:** When `.coding-os/<agent>/.situation` is set, the situational path wins over the composed role chain. Six situations: `incident-response · onboarding · scope-change · external-integration · design-review · existing-project-takeover`.
- **Why:** “Production is on fire” needs a different sequence than a feature build, even if the dimensions look similar.
- **How:** Dispatcher reads `.situation` before `.roles`.
- **Where:** `src/core/thinking_os/situations/`

## Rule 18 — Task reconciliation is mandatory before implementation

- **Rule:** For every non-trivial user request: first check existing tasks via `cos_task_board` / `cos task-show`. Reuse when matched; otherwise create one, fill `Outcome` / `Read First` / `Acceptance`, then move `in_progress → testing → complete` (or `blocked` with explicit blocker).
- **Why:** Otherwise tasks duplicate, board state diverges from reality, and progress can’t be measured.
- **How:** No hook (yet) — convention enforced via review + memory.
- **Where:** [docs/governance/task-lifecycle.md](task-lifecycle.md)

## Rule 19 — Docs are the contract — never extend code beyond doc spec

- **Rule:** If the doc says “registration takes username, password, name”, do NOT add a `birthdate` field because it “feels needed”. Edit the doc first, then the code.
- **Why:** Code-first changes silently extend the contract; consumers read the doc, not the diff.
- **How:** Pair: Rule 0 anchors new code TO a doc going IN; `enforce-doc-sync.sh` (PostToolUse Write|Edit|MultiEdit) surfaces docs that drifted going OUT — three signals: (a) symbol removed/renamed + doc still mentions it, (b) signature changed (param-count diff), (c) doc mtime older than code AND mentions a current symbol. Collaborates with thinking_os FTS5 index for accurate doc lookup + graph_os `cos_graph_references` for impact context. WARN class — agent must act.
- **Where:** `src/core/hooks/enforce-doc-sync.sh`

## Rule 20 — Test discipline: matrix command only, never broad sweep mid-task

- **Rule:** `pytest tests/ -q` runs 743 integration tests (~6 min). Match changed files → matrix command (15s–90s) per `test-discipline.md`. Full sweep is permitted **only** pre-merge/release, cross-cutting refactor touching ≥3 matrix rows, or when the user explicitly asks. Single-test debug: `pytest path::TestClass::test_name -v` before re-running the file.
- **Why:** Six minutes per change × N iterations = the user waits and productivity dies.
- **How:** Convention + Rule. SSOT is `src/core/rules/test-discipline.md`; AGENTS.md § Verification Matrix mirrors it.
- **Where:** `src/core/rules/test-discipline.md`

## Rule 21 — Never use `isolation: "worktree"` in this repo

- **Rule:** Subagent dispatch is allowed **only** for read-only research / inventory / verification (Agent tool without `isolation`). Write work runs single-agent on the main working tree. Never pass `isolation: "worktree"` to the Agent tool.
- **Why:** Past worktree runs left orphaned `.claude/worktrees/<slug>/` plus locked `worktree-*` branches with broken `.git` links — required manual `find .git/worktrees/...` cleanup and deadlocked sessions.
- **How:** Convention. The `worktree-orchestration` skill has been removed from `src/core/skills/` and `src/templates/_base/base.yaml`. Reviewers reject re-introduction.
- **Not the same as pr-mode worktrees:** Rule 21 bans the **Agent-tool** `isolation:"worktree"` — an ephemeral *subagent's* checkout that the dying parent never GCs (→ orphans). The consumer-only **pr-mode** git worktree is a *different* mechanism: a live *main-loop* session's durable workspace, GC'd by an owner-independent reaper (`cos pr reap` / `pr-reap.sh`). That reaper is exactly the missing piece that made Rule 21 necessary, so the ban and pr-mode coexist (no conflict). See [ADR-0013](../architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md) · [pr-workflow.md § 7](../playbooks/pr-workflow.md).
- **Where:** [AGENTS.md](../../AGENTS.md) § Critical Rules

## Rule 22 — Anti-overengineering

- **Rule:** Solve the problem in front of you with the smallest correct change. Reuse what exists, do not speculate, do not duplicate. Five sub-rules: (1) **Reuse-First** — search graph / docs / grep before writing anything; (2) **No-Speculation** — build only what the current task requires, no "might need it later"; (3) **Diff-Minimal** — smallest correct change, bug-fix-only commits, no ride-along refactors; (4) **No-Premature-Abstraction (Rule of Three)** — extract only when three divergent call sites need it; (5) **Defer-by-Default** — ask "what can I remove?" at task close. Applies to **every artifact** — code, docs, hooks, skills, templates, tests, CLI, configs.
- **Why:** Every line written is paid for forever. Over-engineering grows surface area, hides intent, slows review, and trains the next agent that bloat is the house pattern. In an enterprise codebase the cumulative cost dominates any single addition.
- **How:** Convention — automated detection is too false-positive-prone (numeric thresholds, abstraction counts, file additions). Enforcement is the reality-check matrix in the rule body, code review, and `cos_search` observations that surface prior incidents. Tactical instances (no abbreviations, no magic numbers, no positional booleans, nesting ≤ 2) are enforced through the `clean-code` skill.
- **Where:** `src/core/rules/anti-overengineering.md`. Cross-links: `api-contract-discipline.md`, `test-discipline.md`, `clean-code skill`.

---

## Rule 23 — Trunk-based git workflow

- **Rule:** Work on the default branch (`main`). Do NOT create feature branches or worktrees — commit directly to `main` with explicit paths, `git pull --rebase` before every push. This OVERRIDES any agent-runtime "branch first" default. **The agent also commits its own work autonomously after each logical unit — it does NOT wait to be asked, which OVERRIDES the runtime "commit only when the user asks" default; `push` stays gated to task-close / user-ask.** The `COS_GIT_WORKFLOW` env var selects the mode: `trunk` (default — branches blocked) or `pr` (**consumer-only opt-in, default OFF** — a *positive policy*, not blanket-allow: `agents/*` branches + worktrees pass, but HEAD-rewrites/commits on the shared integration checkout and pushes to protected branches stay BLOCKED). coding-os itself stays trunk; pr-mode ships for consumer projects and is dogfooded through a fixture (ADR-0013). Full spec: [pr-workflow.md](../playbooks/pr-workflow.md).
- **Why:** The runtime's "branch first" default produced branch sprawl — branches lingered unmerged and a second concurrent session landed on a first session's branch, tangling unrelated work. Trunk-based development is the modern enterprise standard (DORA / Accelerate); for a single-user agent-driven project it is correct and simpler than long-lived feature branches. Concurrency is handled by git's own `index.lock` plus explicit-path commits — no custom write-lock is built (it would reinvent `index.lock` and add a crash-deadlock failure mode). The runtime's *other* conservative default — "commit only when the user asks" — is also wrong for this repo: a session abandoned mid-work would strand uncommitted edits, and no review (the `reviewer` role / `/code-review` / CI) can run without a committed diff. The enterprise split is commit-vs-publish, not commit-vs-wait: `commit` is local and trivially reversible (`amend` / `reset` / `revert`), so the agent does it freely per logical unit; `push` / merge is the irreversible, wide-blast-radius step (here `src/core/**` reaches every consumer via live symlinks), so it stays gated.
- **How:** `branch-guard.sh` (PreToolUse:Bash) BLOCKs `git checkout -b`, `git branch <name>`, `git switch -c`, and `git worktree add` in trunk mode. In `pr` mode the same hook applies the *positive policy* (allow `agents/*` + worktrees, block shared-checkout HEAD-rewrites/commits + protected pushes), `block-shared-tree-edit.sh` isolates Write/Edit to worktrees, and the `cos pr` CLI drives the worktree→PR→CI→merge→cleanup loop with an owner-independent reaper. The autonomous-commit + push-gated contract is documented in `src/core/rules/git-workflow.md § When to commit` (loaded every session). `session-context.sh` surfaces any *leftover* dirty tree at session startup so a half-finished unit from an abandoned session is recovered, not blind-committed.
- **Where:** `src/core/rules/git-workflow.md`. Hook: `src/core/hooks/branch-guard.sh`.

### Trunk-based mechanics (rationale)

- **HEAD-moving on the shared checkout is blocked.** `git reset HEAD~N`, `git reset <sha>`, `git checkout <other-branch>`, `git switch <other-branch>`, and `git rebase` move HEAD off a published commit — that clobbers a peer session's work and orphans commits. Undo a published commit with `git revert <sha>` (a new commit, history preserved). For integration before push use `git pull --rebase origin main` — a `pull` subcommand, so only your *local* commits move.
- **Why no custom write-lock hook.** Git's own `index.lock` plus explicit-path commits cover the real collisions; a custom lock would reinvent `index.lock` and add a crash-deadlock failure mode. Two commits the same instant → `index.lock` rejects one → wait ~1s and retry. Two pushes the same instant → non-fast-forward reject → `pull --rebase` → retry.
- **Live-symlinked safety hooks need atomic edits.** `src/core/hooks/*.sh` are live symlinks into every consumer project, so a half-written `block-*`/`enforce-*` hook is executed by sibling sessions at every intermediate save. Prefer a single atomic `Edit`; for a larger rewrite, edit out-of-tree then `mv` into place after `bash -n` + `make verify-hooks`. Snapshot isolation is deferred — it removes the hazard but breaks the instant-propagation property that makes the symlink design valuable.

## Rule 24 — Commit message contract

- **Rule:** Title ≤100 chars, Conventional Commit shape (`<type>(scope)?!: subject`, type ∈ feat/fix/docs/perf/refactor/build/ci/test/chore/style/revert). Body ≤3 non-empty lines of plain "why" prose. No `Co-Authored-By:` trailers, no agent/AI attribution (`🤖`, `Generated with [Claude`, `noreply@anthropic.com`, `claude.com/claude-code`, `@anthropic.com`), no prompt leaks (lines beginning `USER`, or quoted text >40 Persian/Arabic chars).
- **Why:** Every line in a commit message exists forever. Verbose bodies (audit tables, file lists, verification blocks) bloat `git log`, leak ephemeral context into permanent history, and inflate token cost for every future agent that runs `git log`. Enterprise convention (Linux kernel, Chromium, Google) is title + tight 2–3 line "why". release-please parses the title to derive the version bump — an unparseable type silently drops the change from `CHANGELOG.md`. Verbose content belongs in the PR description or the work-log.
- **How:** `enforce-commit-message.sh` (PreToolUse Bash) blocks the agent before `git commit`; the git-level `commit-msg` hook (installed via `src/scripts/install-git-hooks.sh`) blocks human-direct + Codex-GUI commits. Both call `check_commit_message.py`. `--no-verify` is blocked for agents by `block-secrets.sh` (no escape hatch); a human running git directly may still use it in a genuine emergency.
- **Where:** `src/core/rules/git-workflow.md § Commit Message Contract`. Hook: `src/core/hooks/enforce-commit-message.sh`.

---

## Rule 25 — Cognitive-state mutations go through semantic ops, never hand-edit

- **Rule:** Task/board status, the Cynefin gate, the doc-anchor, and any `.coding-os/**` state file are mutated ONLY through their semantic op — never a raw `Edit`/`Write`. Task status → `cos_task_move` / `cos task-done` / `cos_task_reposition`. Gate → `cos_classify_prompt` (records when a panel session is resolvable; else use the `write-state.sh` fallback it returns — the low-level contract the gate hook reads). `.task-current` → set automatically by `cos task-start` / `cos_task_move → in_progress`. Task lookup → `cos task-show` / `cos_task_search` / `cos_task_show` (MCP) — NEVER raw `ls`/`grep`/`cat`/`Read` on `docs/tasks/`.
- **Why:** The markdown task file is the SSOT; the board DB is a cache synced from it. The semantic ops are the only writers that run the transition gates (DoR/DoD), WIP caps, and reviewer hint. A raw `Edit` writes the same SSOT ungated — it skips every gate. Raw `ls|grep` lookups waste tokens and read stale files instead of the board-aware view.
- **How:** `enforce-task-transition.sh` (PreToolUse Write|Edit) BLOCKs a `status:`/`**Status:**`/checkbox transition on `docs/tasks/**/*.md`; allow-listed for `governance`/`docs-update`/`template-update` tasks or `COS_ALLOW_TASK_EDIT=1`. `nudge-task-discovery.sh` steers `TASK-NNN` prompts + `ls/grep docs/tasks` Bash to `cos task-show`. `sync-task-current.sh` auto-writes `.task-current`. A SessionStart rules-primer loads the prohibition turn-1.
- **Where:** `src/core/hooks/{enforce-task-transition,nudge-task-discovery,sync-task-current}.sh`, `docs/governance/task-lifecycle.md`.

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
| 12 | Comments by exception | (none — convention) |
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
| 23 | Trunk-based git workflow | branch-guard.sh |
| 24 | Commit message contract | enforce-commit-message.sh + commit-msg hook |
| 25 | Semantic state ops, no hand-edit | enforce-task-transition.sh |
