# Installing — user scope, both agents, no build step

The directory **is** the skill. There is nothing to compile and no installer to run: point an
agent's skill root at this folder and it works.

It carries **no dependency on coding-os** — no `cos-env.sh`, no `$COS_*` variable, no wrapper
directory. The scripts locate themselves from their own path, so the same folder behaves
identically inside a coding-os project and in one that has never heard of it.

## One source, two symlinks

Claude and Codex read from different roots, and the copies installed there are independent
directories rather than one shared folder. So a single canonical source is achieved with a
symlink per root:

```bash
SRC="$HOME/Files/Project/coding-os/src/core/skills/motion-review"

mkdir -p "$HOME/.claude/skills" "$HOME/.codex/skills"
ln -sfn "$SRC" "$HOME/.claude/skills/motion-review"
ln -sfn "$SRC" "$HOME/.codex/skills/motion-review"
```

Both roots now resolve to the same files, so an edit to the source reaches both agents with no
re-install. Verify:

```bash
ls -l "$HOME/.claude/skills/motion-review" "$HOME/.codex/skills/motion-review"
python3 "$HOME/.claude/skills/motion-review/scripts/doctor.py"
```

Some setups also scan `~/.agents/skills`. Install to **one** Codex-visible root only — a skill
present in two roots appears twice in the picker, because same-named skills are listed, not
merged.

## Standalone, away from this repo

Copy the folder anywhere and symlink from there, or drop it straight into a skills root:

```bash
cp -R motion-review "$HOME/.claude/skills/"
```

Nothing changes. The only requirement is the host tooling below.

## Host requirements

| Need | Why | Check |
|---|---|---|
| `ffmpeg` + `ffprobe` | the whole engine | `scripts/doctor.py` |
| `yt-dlp` | only to fetch a video by URL | optional |
| Playwright's own bundled ffmpeg | only to record a web page | `python -m playwright install ffmpeg` |

`scripts/doctor.py` reports each one and exits non-zero when a required binary is missing, so
it can gate a setup step. It never installs anything by itself.

## Name collisions — the one real hazard

A personal skill **overrides a project skill of the same name**, silently, in every session on
the machine. Nothing in a project can detect that it has been shadowed.

So before installing user-scope, confirm the name is free:

```bash
find "$HOME" -maxdepth 4 -name motion-review -path "*skills*" 2>/dev/null
grep -rl "^name: motion-review" "$HOME"/.claude/skills "$HOME"/.codex/skills 2>/dev/null
```

If a project you work on already ships a skill by this name, rename one of them before
installing. A shadowed project skill is the most expensive failure this layer can produce,
because it produces no error at all.

## Uninstall

```bash
rm "$HOME/.claude/skills/motion-review" "$HOME/.codex/skills/motion-review"
```

Removing the symlinks is the whole uninstall — the skill keeps no state outside the frame
directories you asked it to write.
