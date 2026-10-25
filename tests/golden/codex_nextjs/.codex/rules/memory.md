# Memory Policy

> **Scope — `memory` module.** Active only when the `memory` subsystem is enabled; a lean profile unlinks this file.
>
> Canonical layering SSOT (the *why*): [docs/governance/wrapper-derivation.md](../../docs/governance/wrapper-derivation.md). This rule is the operational policy.

Durable cross-session memory is plain markdown in **`.agents/memory/`**, committed with the repo. There is no database and no MCP tool behind it: every agent reads and writes the files directly, so a fresh clone carries the memory with it and every agent sees the same notes.

## The four layers

Every fact lives in exactly **one** layer. The same fact in two is drift waiting to happen.

| Layer | Tool | What lives there |
|---|---|---|
| **Code** | `Read` / `cos_graph_*` | implementations, contracts in code |
| **Docs** | `cos_doc_search` | specs, playbooks, ADRs, runbooks |
| **Tasks** | `cos_task_*` | what is in flight, queued, blocked, done |
| **Agent memory** | `.agents/memory/` files | facts that are none of the above: decisions, failure modes, user preferences |

Reach for the graph and docs first; memory is for "have I been here before?".

## Layout

- **`MEMORY.md`** — the index, loaded into every session. One line per memory: `- [Title](slug.md) — the rule`, at most 200 bytes. Claude Code loads only the first 200 lines or 25 KB of it, whichever comes first, so a line that grows into a summary pushes the newest memories out of view. Keep the rule, move the detail into the file.
- **`index-<domain>.md`** — a sub-index for recipes that only matter inside one kind of work (releases, a vendor API, a media pipeline). `MEMORY.md` carries one line per sub-index saying when to open it. Sub-indexes are one level deep. A guardrail whose absence costs something irreversible stays in `MEMORY.md`.
- **`<slug>.md`** — one fact per file, with frontmatter `name`, `description` and `metadata.type` (`user` · `feedback` · `project` · `reference`). A `feedback` or `project` memory follows the fact with **Why:** and **How to apply:** lines. Link related memories with `[[slug]]`. A `project` or `reference` memory that makes claims about live state carries `metadata.verified: YYYY-MM-DD` from the day someone re-checked them.

Every memory is linked from exactly one index line. An index line states a rule, never a status ("blocked", "done", "next") — status goes stale; point at the task or doc that owns it.

## How each agent reaches it

- **Claude Code** keeps its memory in `~/.claude/projects/<slug>/memory/`. The `ensure-agent-memory-link` SessionStart hook turns that directory into a symlink onto the repo's `.agents/memory/` (per machine, never committed), so Claude's own memory writes land in the repo.
- **Codex** has no memory directory to link. The `prime-memory-codex` hook hands it `MEMORY.md` once per session; it opens the file a line points at when the line applies.
- **Any other agent**: read `.agents/memory/MEMORY.md` at the start of a task, then the files its lines point at.

## What to write, and what not

Write a memory for something a future session cannot recover from the code, the docs, the board or `git log`: a failure mode with its root cause, a decision whose alternative was not obvious, a preference the user stated, a fact about the project's surroundings. Before saving, check for an existing memory that covers it and update that one.

Do not save code structure, doc content, task state, what you just did, or anything `git log` records. A mistake that keeps recurring needs a mechanism — a hook, rule, gate or test that fails the next offender — not only a note.

**Code wins over memory.** A memory is frozen when written; when it disagrees with the code or a doc, the memory is stale — fix or delete it. Never record secrets or personal data.

## Enforcement

`make memory-lint` checks the structure: every memory indexed exactly once, every index link and `[[wikilink]]` resolves, no status words in index lines, `MEMORY.md` within the load limits, and line and `verified` warnings for staged files. It cannot tell whether a memory's claims are still true; that stays a human judgement.
