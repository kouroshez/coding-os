<!-- domain:OPS | layer:runbook | ssot:true | updated:2026-06-14 -->
# Migration Guide — Pre-0.3 → Current

Purpose: Upgrade a consumer project scaffolded by a pre-0.3 coding-os core to the
current core, without re-running `cos init`.
Read when: A project's `.coding-os/.core-version` is older than the installed core,
`cos update` warns about core drift, or agent symlinks dangle after the meta-repo moved.
Skip when: The project was scaffolded by the current core (no drift warning) — nothing to do.
Read next: [Release Process (SSOT)](release-process.md).

## When you need this

`cos update` prints a `WARN: core drift` line when the project's stamped
`core_version` differs from the installed core. Pre-0.3 scaffolds predate three
things the current core relies on:

1. The composed `.coding-os/*.yaml` verify map (`enforce-verify.sh` reads it).
2. The `core_version` stamp in `.coding-os/.core-version`.
3. Stable agent-dir symlink targets that survive a meta-repo move.

The upgrade is **non-destructive** — `cos update` never touches `docs/`,
`AGENTS.md`, or any user-authored file. It re-links assets, re-stamps the
version, and runs append-only DB migrations.

## Upgrade path (run from the project root)

### 1. Update the core, then sync the project

```bash
# In the coding-os checkout — pull the new core, refresh the installed CLI:
git pull && uv tool install --editable .

# In your project — apply the diff (dry-run first to read it):
cos update --dry-run        # shows added/removed assets + DB migrations
cos update --yes            # applies; re-stamps .core-version
```

`cos update` is safe to re-run. It applies new hooks/skills/rules/commands,
removes orphans, runs DB migrations, and re-stamps the core version. The drift
warning disappears on the next run.

### 2. Repair dangling symlinks (if the meta-repo moved)

Pre-0.3 agent-dir symlinks point at absolute paths in the old meta-repo
location. If you moved or re-cloned the coding-os checkout, those links dangle.
Any `cos` command nudges you with a `WARN: dangling coding-os symlinks` line.
Repair them:

```bash
cos sync-doctor --repair        # re-runs install.sh on projects with dangling links
```

### 3. Refresh the verify config

Pre-0.3 `.coding-os.yaml` has an empty `verify:` map, so `enforce-verify.sh`
cannot tell which suite a changed-file glob requires. `cos update` repopulates
the map from the installed stacks. Confirm it landed:

```bash
cos doctor                      # reports verify-map coverage + symlink health
```

If `cos doctor` still flags an empty verify map after `cos update`, the project
was scaffolded without a stack — add one with `cos add-stack <id>` (which
recomposes the verify map).

## Verify the upgrade

```bash
cos update --dry-run            # second run shows NO changes → fully synced
cos doctor                      # green: version stamped, links live, verify map populated
```

A clean dry-run plus a green `cos doctor` means the project is on the current
core. No re-init is ever required — `cos init` is for fresh projects only.

## Preview before you commit

Use `cos init --dry-run` (zero writes) to inspect the scaffold tree a fresh
init would produce for a given stack set — useful for confirming a new stack's
file layout before adding it to an existing project.

## See also

- [Release Process (SSOT)](release-process.md) — version-bump rules and release notes.
- [Critical Rules — Full Text](critical-rules.md) — Rule 23 (trunk-based git) and the upgrade discipline behind `cos update`.
