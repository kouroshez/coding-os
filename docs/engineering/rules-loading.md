<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-18 -->
# Rules Loading — How `src/core/rules/*.md` Actually Become Active

Purpose: Explicit, honest answer to "when is a rule file actually loaded, and by whom?" — because the files in `src/core/rules/` carry YAML frontmatter (`globs`, `alwaysApply`) that *looks* like auto-loading but neither Claude Code nor Codex consume that frontmatter.

Read when: Adding a new `src/core/rules/*.md` file · wondering why a rule didn't seem to apply · deciding whether to rely on rule frontmatter or on explicit AGENTS.md references.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## TL;DR

> **Neither Claude Code nor Codex auto-load `src/core/rules/*.md` based on the frontmatter in those files.** Rules become effective because `AGENTS.md` explicitly instructs the agent to read them. On today's runtimes the frontmatter is decorative — a machine-readable description, not a load trigger.

## The frontmatter you may see

Some rule files carry:

```yaml
---
description: Thinking OS Kernel — cognitive operating system for structured problem solving
globs: "**/*"
alwaysApply: true
---
```

These keys (`globs`, `alwaysApply`) describe *which* files a rule is meant to govern and whether it is always active. **Claude Code and Codex do not consume these keys** — they neither auto-inject the rule nor scope it by `globs`.

Keeping the frontmatter is harmless: it serves as a machine-readable description of the rule's scope plus a hint to the reader, at a cost of a few lines per file.

## What each runtime actually auto-loads

### Claude Code (runtime behavior on 2026-04-18)

Auto-loaded at session start or when entering a directory:
- `CLAUDE.md` at project root (in this repo, a symlink → `AGENTS.md`).
- `@path/to/file.md` imports declared inside `CLAUDE.md` (we do not use this today).
- `CLAUDE.md` files inside subdirectories when entering them (we do not ship any).
- `.claude/skills/*/SKILL.md` are **not auto-loaded into context** — they are invoked on demand via `Skill` tool, and may be blocked by `enforce-skill.sh` until invoked.

**Not auto-loaded:** `.claude/rules/*.md`. The directory is a coding-os convention, not a Claude Code primitive.

### Codex CLI (runtime behavior on 2026-04-18)

Auto-loaded at session start:
- `AGENTS.md` at project root.
- Codex config layers: project `.codex/config.toml` overrides, then `~/.codex/config.toml` user defaults.

**Not auto-loaded:** `.codex/rules/*.md`. The `src/adapters/codex/install.sh` itself notes (lines 55–58):

> "Codex CLI's Starlark sandbox scanner expects `.rules` files; `.md` files in this dir are ignored by that scanner and serve only as agent-readable content."

## So how do `src/core/rules/*.md` take effect?

Through explicit reference in **AGENTS.md**, which both runtimes DO load automatically.

The relevant lines in this repo's [AGENTS.md](../../AGENTS.md):

```
Always-active (no retrieval, full-read): AGENTS.md, CLAUDE.md, playbooks, src/core/rules/, current task detail.
```

and:

```
- Behavioral rule / protocol (how to classify, how to verify, how to route)
  → NEVER retrieve; the rule is already in context as src/core/rules/*.md.
  If you think you need to retrieve it, re-read the rule file instead.
```

This tells the agent, on every session, to full-read every file in `src/core/rules/` as part of orientation. The agent's compliance is the load mechanism — not the runtime.

## Why this design is defensible

1. **Symmetric across runtimes.** If we relied on `@import` in CLAUDE.md (Claude only), Codex users would silently miss the rule. The AGENTS-reference approach works identically on both.
2. **Token-economical.** Rules are loaded once, not re-injected per file edit.
3. **Hook-compatible.** Hooks like `enforce-skill.sh` and `block-protected-files.sh` have their own embedded logic — they do NOT parse `src/core/rules/*.md`. So the rule files are purely for agent context, not for runtime enforcement. This separation is why the system still works when a rule is rephrased but the hook logic is unchanged.

## What happens if we DID want auto-loading

Three options, each with a trade-off:

### Option A — Add `@import` to AGENTS.md

Inside `AGENTS.md` add:

```
@src/core/rules/thinking_os.md
@src/core/rules/memory.md
```

**Pro:** Claude Code injects the content automatically.
**Con:** Codex does not support `@imports`. Agent behavior diverges between runtimes. Rejected for this reason.

### Option B — SessionStart hook that prints rule bodies

A hook that on `SessionStart` reads `src/core/rules/*.md` and echoes them to stderr so the content lands in the agent's context.

**Pro:** Works on both runtimes (both support SessionStart).
**Con:** Burns context tokens every session for content the agent can also just fetch with `Read`. For a large rule corpus, that's a cost per session that grows with rule count.

### Option C — Status quo (what we do today)

AGENTS.md contains the reference. Agents full-read `src/core/rules/` on orientation. A hook (`check-agents-md-refs.sh`) warns if AGENTS.md references paths that don't exist.

**Pro:** Zero runtime cost until needed. Works identically on both runtimes.
**Con:** Relies on agent self-discipline (prompt-level, not programmatic).

**Chosen:** C. The deterministic-enforcement layer (hooks) doesn't depend on rule loading, so the probabilistic nature of "agent reads the rule file" is acceptable.

## Adding a new rule

1. Add `src/core/rules/<name>.md` with YAML frontmatter + body.
2. Reference it from `AGENTS.md` (either in Navigation Cheatsheet, Modularity Map, or inline in the Critical Rules section).
3. Run `make sync` — `install.sh` for each adapter re-creates the symlink in `.claude/rules/` and `.codex/rules/`.
4. `check-agents-md-refs.sh` will warn if the reference is missing.

## Why keep the frontmatter at all?

Cost of keeping it: ~4 lines per rule file. Benefit: a machine-readable record of each rule's scope (`globs`) and always-active status (`alwaysApply`) that documents intent for both agents and humans. Cheap enough to keep.

## Debugging — "this rule didn't apply"

Diagnostic order:

1. **Is it referenced from AGENTS.md?** `grep -n '<rule-name>' AGENTS.md`. If no, add the reference.
2. **Is the symlink live?** `ls -l .claude/rules/ .codex/rules/`. If missing, `make sync`.
3. **Did the agent read it?** This is the probabilistic part. Hooks don't verify. If you need deterministic enforcement, the rule's content must also be encoded in a hook (e.g., `enforce-skill.sh` encodes part of `skill-enforcement.md`).

## References

- [src/core/rules/thinking_os.md](../../src/core/rules/thinking_os.md) — example always-active rule
- [src/core/rules/skill-enforcement.md](../../src/core/rules/skill-enforcement.md) — generated from `src/templates/*/stack.yaml`
- [AGENTS.md](../../AGENTS.md) — where rules are referenced
- [docs/engineering/hooks-reference.md](hooks-reference.md) — `check-agents-md-refs.sh` + `block-protected-files.sh`
- [docs/engineering/adapter-parity.md](adapter-parity.md) — confirms both adapters symlink the same rule files
