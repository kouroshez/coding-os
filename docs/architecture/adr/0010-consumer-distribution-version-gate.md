<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-10-24 -->

# ADR-0010: Consumer distribution needs a version gate before the first real consumer

- **Status:** Accepted, amended (2026-10-24, TASK-1065) — see § Amendment: clone-ready adapter dirs. Originally proposed 2026-06-19 (TASK-462).
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** modularity, adapters, distribution, blast-radius, strategic-audit-2026-06

## Context

`cos init` / `cos update` wire a consumer project's `.claude/hooks/*` as **live
symlinks** that point straight into the installed core
(`src/core/scripts/install-adapter.sh` → `ln -sf`; `src/cli/update.py:319`
→ `link.symlink_to`). The Modularity Map in [AGENTS.md](../../../AGENTS.md)
states the consequence plainly: `src/core/hooks/*.sh` propagates to **ALL
consumer projects** with **Rebuild: none**.

That means there is **no version boundary between core and its consumers**:

- A single bad edit to any of the 21 PreToolUse BLOCK hooks — or a syntax error
  in `cos-env.sh`, which all 89 hooks `source` (Rule 3) — reaches every consumer
  **instantly**, with no pin, no canary, no staged rollout.
- The only version mechanism that exists today, `src/cli/core_version.py`, is a
  **passive WARN** on `cos update` / `cos doctor` (`update.py:455-461` reports
  drift and re-stamps regardless). Its own module docstring admits the gap:
  *"Consumers pin to core via live symlinks with no version signal (D6); a
  breaking hook/MCP change otherwise breaks them silently on `cos update`."*

The strategic audit (2026-06-19) flagged this as the single sharpest
**coupling / failure-scenario** risk for the moment consumers exist. It is not a
problem **today**: there are zero external consumers and the operating reality is
"breaking changes are free." Building a rollout system now would be premature
(Rule 22) — but the *decision* should exist before it is needed, so it is not
made under pressure during a live incident.

## Decision

**Record the seam now; do not build it yet.** When the first real external
consumer is onboarded, the distribution posture changes from *editable symlinks*
to *versioned, copied artifacts* behind a **blocking** compatibility gate:

1. **Ship copies, not symlinks.** Consumers receive core hooks/rules as **copied
   files** (a wheel / pinned snapshot), so a core edit does not mutate a running
   consumer mid-session. The live-symlink mode stays the default **only** for the
   meta-repo dogfood and for local development, where instant propagation is the
   point. This is a posture flip in `install-adapter.sh` (symlink vs copy), not a
   new subsystem.
2. **Promote `core_version` from WARN to BLOCK.** `cos doctor` / `cos update`
   **fails closed** when a consumer's stamped core version is incompatible with
   the installed core, with a remediation path — rather than re-stamping and
   warning. The stamp + comparison already exist; only the exit behavior changes.
3. **Stage propagation.** Core releases are tagged; consumers opt into an update
   explicitly (`cos update`) rather than inheriting every `main` commit through a
   live link.

The trigger to implement is binary: **the first non-dogfood consumer that the
maintainer does not personally control.** Until then this ADR is the gate.

## Consequences

- **Positive:** the highest-blast-radius failure mode (one bad hook → global
  consumer outage) gets a deliberate boundary; the decision is made calmly, in
  advance, with the cheap-fix path (`symlink → copy`) already named.
- **Positive:** keeps the meta-repo's fast inner loop (live symlinks) intact —
  the gate applies only to external distribution.
- **Negative / cost:** when implemented, copied artifacts mean consumers no
  longer get core fixes instantly — they must run `cos update`. That is the
  intended trade (safety over instant propagation), but it adds an update step
  and a compatibility matrix to maintain.
- **Deferred:** no code lands from this ADR. A future task implements (1)–(3)
  gated on the first-consumer trigger. Linked from the audit memory
  `strategic-audit-2026-06`.

## Amendment: clone-ready adapter dirs (2026-10-24, TASK-1065)

The trigger fired without an external consumer: CI, a second Mac and cloud
agent sessions all clone a project and found no `.claude/`, `.codex/` or
`.mcp.json`, because `cos init` gitignored them — they held 373 symlinks to
absolute paths on one machine. The posture is now: **every link `cos` writes
resolves inside the repository, and the adapter dirs are committed.**

- **coding-os itself** links relatively into its own `src/` — dogfood keeps live
  propagation, and a clone works.
- **A consumer** gets real copies of the static agent content — rules, skills
  (with their `references/` / `scripts/` / `assets/`), commands — pinned to the
  core that wrote them; `cos update` rewrites them, so a core change reaches a
  consumer as a reviewable diff, never mid-session.
- **Hooks are not copied.** They are thin shells over the coding-os runtime
  (`../thinking_os/*.py`, `_helpers/`, the `cos` package), so a copy would be a
  second kernel drifting from the installed one. Each `<agent>/hooks/<name>.sh`
  is instead a relative symlink to one tracked shim, `.coding-os/hook-shim.sh`,
  which runs the same-named hook from this machine's coding-os install (located
  through the `cos` entry point, cached in the untracked
  `.coding-os/.core-root`). Without an install the shim exits 0: nothing can
  enforce without the runtime, and a clone must not error on every tool call.
- `.mcp.json` already names `cos server-start`, and `.coding-os/Makefile.base`
  already resolves `COS_ROOT` through `cos hooks-dir` at make time; both are
  committed as they are.
- Only machine-local state stays ignored: `.claude/settings.local.json`, the
  runtime under `.coding-os/` (including `.core-root`) and `.codex/config.toml`.
  The last one carries this machine's absolute state paths, and Codex reads a
  project's config only after the machine trusts it — the trust step is where
  `cos update` writes it. The rest of `.codex/` is committed.

Item 2 (BLOCK on version skew) stays deferred: with the copies pinned, the stamp
in `core-version.json` is finally true, and the existing WARN names the
`cos update` that brings a consumer forward.

## See also

- [ADR-0006: External task-tracker seam](0006-external-task-tracker-seam.md) — same "name the contract before building it" pattern.
- `src/cli/core_version.py` — the existing (WARN-only) version stamp this ADR promotes to a gate.
- [AGENTS.md](../../../AGENTS.md) Modularity Map — the `Rebuild: none` propagation row this ADR bounds.
