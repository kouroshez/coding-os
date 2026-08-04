<!-- domain:META | layer:playbook | ssot:false | updated:2026-05-21 -->
# Screencast / Demo GIF Guide

Purpose: a repeatable script for capturing the README demo GIF so
every release shows the same 30-second story at the same quality.

Read when: refreshing the README demo, or recording a release video.

Skip when: not touching project marketing assets.

> Nav: [Docs Index](00-index.md) | [README](../README.md)

## Why a scripted demo

The README's first impression is the demo. An improvised recording
drifts in pacing and content between releases. This guide fixes the
**exact commands**, **timing**, and **export settings** so the GIF is
reproducible.

## The 30-second story

The demo must show, in order:

| Beat | Seconds | What's on screen |
| ---- | ------- | ---------------- |
| 1 | 0–5   | `cos --version` → `cos init --agent claude --template django --name demo --yes` |
| 2 | 5–10  | `cd demo && cos doctor` — the 14-check health pass |
| 3 | 10–18 | `cos hub start` → browser opens `http://127.0.0.1:9188` |
| 4 | 18–26 | Hub: click through Graph → Board → Cognition tabs |
| 5 | 26–30 | Land on the graph canvas, gently zoom one cluster |

Keep it under 30 seconds. A longer GIF balloons the README payload
and loses the viewer.

## Tooling

| Need | Tool | Notes |
| ---- | ---- | ----- |
| Terminal recording | [asciinema](https://asciinema.org) or [t-rec](https://github.com/sassman/t-rec) | t-rec exports GIF directly |
| Screen region capture | [Kap](https://getkap.co) (macOS) / [peek](https://github.com/phw/peek) (Linux) | for the browser portion |
| GIF optimization | [gifsicle](https://www.lcdf.org/gifsicle/) | `gifsicle -O3 --lossy=80` |
| Terminal → GIF | [vhs](https://github.com/charmbracelet/vhs) | **recommended** — scripted, deterministic |

**vhs is the recommended path** — the recording is itself a script
(`.tape` file), so it is reproducible and diffable.

## Recommended: vhs tape

Create `docs/assets/demo.tape` — run `mkdir -p docs/assets` first, the
directory is not tracked in the repo:

```tape
Output docs/assets/demo.gif
Set FontSize 16
Set Width 1200
Set Height 700
Set Theme "Dracula"
Set TypingSpeed 60ms

Type "cos --version" Enter Sleep 1s
Type "cos init --agent claude --template django --name demo --yes" Enter Sleep 3s
Type "cd demo && cos doctor" Enter Sleep 4s
Type "cos hub start" Enter Sleep 3s
# Browser portion captured separately and composited.
```

Render:

```bash
vhs docs/assets/demo.tape
gifsicle -O3 --lossy=80 docs/assets/demo.gif -o docs/assets/demo.gif
```

## Export settings

- **Dimensions:** 1200×700 (terminal), ≤ 1280 wide (browser).
- **Frame rate:** 12–15 fps — enough for terminal + UI, keeps size down.
- **Target size:** **≤ 3 MB**. GitHub renders inline; over ~5 MB it
  loads slowly on the README. Run gifsicle until it fits.
- **Loop:** infinite.

## Wiring it into the README

Place the final GIF at `docs/assets/demo.gif` and reference it near
the top of `README.md`, just under the quickstart:

```markdown
![coding-os 30-second demo](docs/assets/demo.gif)
```

Commit the GIF with `docs(readme): refresh demo GIF` so release-please
files it under Documentation.

## Checklist before committing a new GIF

- [ ] Under 30 seconds, follows the 5-beat story above.
- [ ] ≤ 3 MB after `gifsicle -O3`.
- [ ] No secrets, no real client names, no absolute `/Users/...` paths
      visible in the terminal.
- [ ] The `.tape` source (if vhs) committed alongside the GIF.
- [ ] README reference path is correct and renders on GitHub preview.
