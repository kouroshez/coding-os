<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-21 -->
# Destructive-Edit Guard — Friction Before Destruction

Purpose: Canonical contract for the `warn-destructive-edit` hook — a PreToolUse
reflex that interrupts an autonomous agent the moment it is about to delete a
large block from, or wholesale-overwrite, a **load-bearing** file, and hands it
the cheap git command to see what was there and why. It exists because an
autopilot agent that silently clobbers a spec/contract is the project's stated
#1 failure mode, and no surveyed agent system (Cursor, Devin, Git AI) attributes
*before* the edit — they all record *at commit time*, after the loss.

Read when: editing [warn-destructive-edit.sh](../../src/core/hooks/warn-destructive-edit.sh)
or its helper · changing the load-bearing file set · tuning the deletion
threshold · debugging a false-positive warn.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Why a hook, not a rule (and not an audit subsystem)

A rule is soft — an autopilot agent rationalizes it away. The repo's own
philosophy is *hooks enforce where rules get ignored* (the `doc-anchor` is a hook,
not a suggestion). So the destructive-edit reflex is a hook.

It is deliberately **not** an audit subsystem. The audit concept was retired
(TASK-397/401: `git is the single forensic record; never reintroduce`). This
guard honors that: it writes **no** DB row, MCP tool, UI tab, or reason-store.
The "what was here / who / why" answer stays 100% git-native — the hook only
*prompts the read at the dangerous moment* and points at `git`. The agent PULLs
the detail with `git log -L` / `git show` only if it is uncertain.

## The contract

| Property | Value |
|---|---|
| Event / matcher | `PreToolUse` · `Write\|Edit\|MultiEdit` |
| Phase / blocking | `enforcement` · default non-blocking (warn); `strict` mode blocks |
| Exit codes | `0` = allow (silent or warn on stderr) · `2` = block (strict mode only) |
| Failure posture | **fail-open** — any internal error (no git, not a repo, bad JSON, missing config) exits 0 |
| New persistent state | **none** (no DB, no MCP tool, no marker file) |

### Environment (mirrors `enforce-graph-context`)

- `COS_DESTRUCTIVE_GUARD` — `off` (`0`) disables · `warn` (default, also `1`) warns on stderr, exit 0 · `strict` blocks with exit 2.
- `COS_DESTRUCTIVE_GUARD_MIN_LINES` — net removed-line threshold below which the hook is silent. Default `12`.

### Load-bearing file set (reused, no new config)

A file is load-bearing when **either** holds:

1. its repo-relative path is under `docs/` (the contract layer, Rule 19) —
   excluding `docs/tasks/` (board-owned, churns), `docs/_templates/`,
   `docs/_meta/`, and any `archive/` segment; **or**
2. it matches a glob in `.coding-os/rag-config.yaml::graph.enforce_context_on`
   (the same load-bearing **code** set `enforce-graph-context` already guards),
   matched by the shared [graph_context_match.py](../../src/core/hooks/_helpers/graph_context_match.py).

Anything else (scratch files, `node_modules/`, build output, new files) is never
load-bearing → the hook is silent.

## Detection — what counts as "destruction"

The helper reads the PreToolUse `tool_input` and computes **net removed lines**:

- **Edit** — `old_string` newline-count minus `new_string` newline-count.
- **MultiEdit** — summed over every `edits[]` entry.
- **Write** — only when the target **already exists**: current file line-count
  minus new `content` line-count. A Write that creates a new file, or grows a
  file, is never destruction.

If `net_removed < MIN_LINES`, or the file is not load-bearing, the hook prints
nothing and exits 0 (the self-throttling property: silent on the ~95% case).

## The warning (what the agent sees)

One stderr line, high-signal, no history dump (the dump would re-create the
token-burn the audit retirement removed):

```
warning: destructive edit — removing N line(s) from <path>
  last changed by <%h> "<commit subject>" (<author>, <date>)
  before you overwrite/delete, confirm intent:  git log -L<a>,<b>:<path>   |   git show <sha>:<path>
```

Provenance is the **file-level last commit** (`git log -1 --format … -- <path>`),
chosen for a predictable sub-200ms hot-path cost on repos of any size; deeper
line-level attribution is the agent's PULL via the printed `git log -L`. In
strict mode the same body is emitted and the hook exits 2 with a remediation
footer (`set COS_DESTRUCTIVE_GUARD=warn to downgrade, or split the deletion`).

## What this does NOT catch (by design)

- Semantic breakage / contract drift / blast radius → already `cos_graph_impact`
  + `api-contract-discipline` + the verification matrix.
- Whole-file `rm` / `git rm` (Bash surface) → partly `block-dangerous-commands`;
  a future extension may add a Bash matcher.
- "Which session" attribution → git records the human committer only; closing
  that gap would require the retired side-store, so it is intentionally omitted.

## See also

- [enforce-graph-context.sh](../../src/core/hooks/enforce-graph-context.sh) — the pattern + load-bearing-code set this guard reuses.
- [critical-rules.md](../governance/critical-rules.md) — Rule 19 (docs are the contract), Rule 22 (anti-overengineering), Rule 24 (no audit attribution in commits).
- [registry.yaml](../../src/core/hooks/registry.yaml) — hook registration SSOT.
