<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-11-26 -->
# Rules Loading — How a Rule Reaches Each Agent

Purpose: The contract for where an always-active rule lives and how Claude Code and Codex each come to see it.

Read when: Adding or editing a rule in `src/core/rules/` or a stack's `rules/`, adding a session hook that injects text, or wondering why an agent did not follow a rule.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

Measured findings behind this contract: [harness-loading-audit-2026-11.md](harness-loading-audit-2026-11.md) § Codex loading (C2), § Claude loading (L1, L2), § Duplication (D2, D3).

## One owner per rule

Each rule is stated in exactly one file. Every other surface points at it with one line and never restates it.

| Rule kind | Owner | Claude Code | Codex |
|---|---|---|---|
| Core rule | `src/core/rules/<name>.md` | linked into `.claude/rules/`, loaded at launch | the `core-rules` skill, `references/<name>.md` |
| Stack rule | `src/templates/<stack>/rules/<file>.md`, with `paths:` | `.claude/rules/<stack>-<file>.md`, loaded when a matching file is read | the stack's own skill |
| Pointer | `AGENTS.md` | one line per rule | one line per rule |

`dimension-registry.md` and `skill-enforcement.md` are generated catalogs, not rules: no agent loads them.

## What each runtime reads

**Claude Code** loads `CLAUDE.md` (a link to `AGENTS.md`) and every `.claude/rules/*.md` at launch; a rule whose frontmatter has `paths:` loads only when Claude reads a matching file. `globs:` and `alwaysApply:` are Cursor keys that Claude ignores, so a rule carrying them loads in every session. Skills load on demand.

**Codex** loads `AGENTS.md` and the skills in `.agents/skills/`. It reads no prose from `.codex/rules/` (that directory holds Starlark `.rules` command policies), so coding-os renders no `.codex/rules/`. A rule body reaches Codex through the `core-rules` skill: its `SKILL.md` lists each rule and `references/<name>.md` links to the owner file.

## Gated rules

A rule owned only by a disabled module (`src/core/subsystems.yaml`) is not linked. `model-routing.md` is linked only while `hub-settings.json::model_routing.enabled` is true; `nudge-model-routing.sh` points the session at it once routing is on. After turning routing on in Hub, `cos update` links the rule.

## Session hooks restate nothing

SessionStart and compact/resume hooks carry state (task, gate, skill, alerts) and pointers. They never repeat a rule's text: the rule is already loaded (Claude) or one skill away (Codex).

## Golden scaffolds stay invisible

`tests/golden/<case>/` stores each captured `.claude/` directory as `dot-claude/`, and the parity test maps it back. Claude discovers nested `.claude/skills` and `.claude/rules`, so a captured `.claude/` would load every golden copy into this repo's own sessions.

## Adding a rule

1. Write `src/core/rules/<name>.md` (or the stack's `rules/<file>.md` with `paths:`).
2. Add its one line to `AGENTS.md` and to `src/templates/_base/fragments/rules.md.tmpl`, and a reference link under `src/core/skills/core-rules/references/`.
3. Re-run each adapter's `install.sh` (META) or `cos update` (consumer), then `make golden-capture` and `make manifest-regen`.
