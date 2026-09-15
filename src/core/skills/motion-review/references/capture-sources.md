# Capture Sources — five ways in, one output

The engine takes a local video file. Everything below produces one. Every command and every
observed behaviour here was executed, not inferred.

## 1. iOS simulator

```bash
xcrun simctl io booted recordVideo --codec h264 --force run.mp4 &
# …drive the app…
pkill -INT -f "simctl.*recordVideo"   # see the warning below
```

Produces **h264 in MP4**, at device resolution (1206×2622 on an iPhone 17 simulator), at a
variable frame rate. `simctl` prints `Wrote video to: <path>` on stderr — parse that rather
than assuming the path.

> **Own your recorder's PID.** `mcp__ios-simulator__stop_recording` is a `pkill` with no scope:
> it kills *every* simctl recording on the machine, including one a concurrent session started.
> Launch the recorder yourself, keep the PID, and `kill -INT` that PID.

## 2. Android emulator

```bash
adb shell screenrecord --time-limit 30 --verbose /sdcard/run.mp4
adb pull /sdcard/run.mp4 run.mp4
```

Produces **h264 in MP4**. `--time-limit` defaults to **180 s but is not a hard cap** — 400 was
accepted. `--verbose` prints the frame count it actually recorded, which is the fastest way to
catch the static-screen case below. `--bugreport` overlays timestamps, the only cheap pacing
evidence available on this path.

## 3. A web page

```python
ctx = browser.new_context(record_video_dir="vid", record_video_size={"width": 900, "height": 600})
page = ctx.new_page(); page.goto(url)
# …drive the page…
path = page.video.path(); ctx.close()
```

Produces **VP8 in WebM**, not MP4 — ffmpeg reads it either way. Unlike the simulators this is
**clock-driven**: a measured capture gave 71 frames in 2.84 s (~25 fps) regardless of motion.

> Playwright records with its **own bundled ffmpeg**, not the system one. If it is absent the
> run dies with `Executable doesn't exist at …/ms-playwright/ffmpeg-…`. Fix:
> `python -m playwright install ffmpeg` (~1 MB). `scripts/doctor.py` checks for it.

## 4. A file the user hands you

Nothing to do — pass the path. `ffprobe` read every container produced above without extra
flags.

## 5. A video the agent found

```bash
yt-dlp --no-warnings --skip-download --print "%(title)s | %(duration)s s" "<url>"   # look first
yt-dlp -f "bv*[height<=720]+ba/b[height<=720]/b" -o run.%(ext)s "<url>"             # then fetch
```

Check duration before downloading. For a long video, decide on a section first — the engine
will otherwise spend its budget across the whole thing.

---

## The trap that costs the most time

**Simulator recorders are change-driven, not clock-driven.** They emit a frame only when the
screen changes. A static screen recorded for six seconds produces a **one-frame file** —
Android says so out loud: `Encoder stopping; recorded 1 frames in 6 seconds`.

Consequences:

- A naive `-vf fps=2` extraction over such a file yields **zero frames and no error**. The
  engine fails loudly with the frame count instead.
- **The video timeline is not wall-clock.** Three idle seconds produced 0.067 s of video in a
  measured capture. Two recordings will not align side by side, and no pacing claim can rest
  on a simulator recording's duration.
- **A recording without interaction is worthless by construction**, which is why driving and
  recording should be one operation where the platform allows it — see
  [driving-ladder.md](driving-ladder.md).

## Traps that make an honest-looking capture lie

| Trap | Tell | Cost |
|---|---|---|
| Stale bundle — the dev server stopped watching files | the bundle delta reports almost nothing rebuilt | a convincing 10 s recording of pre-edit UI; far more persuasive than one stale screenshot |
| Wrong theme | — | a recording is one theme at a time, so it does **not** reduce the both-themes obligation; it adds a second artifact to forget |
| Dev-client overlays, demo status bars | visible in every frame | they persist across the whole recording rather than being cropped once |
| A concurrent session reloading the app | an unexplained reload mid-recording | the flow you recorded is not the flow you drove |
| Leaked simulator clients | many stale processes on one device | a longer drive means more exposure to whatever instability the platform already has |
| An inspector/debugger attached during the run | the app crashes mid-flow | on some dev runtimes a second debugger client is fatal; detach before recording |

Locale, seeded data and theme spoil a recording exactly as much as a still. The recording adds
no protection against any of them.
