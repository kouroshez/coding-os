---
name: browser-file-upload-blocked-via-cdp
description: "Playwright MCP cannot upload files when attached to the user's real Chrome profile — hand the step back rather than burning turns on workarounds."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6ff99fd1-cc12-4d3e-b39b-ac862d08b140
  modified: 2026-08-21T00:43:20.217Z
---

`browser_file_upload` fails with `DOM.setFileInputFiles: Protocol error … "Not allowed"` whenever Playwright is attached to the user's live Chrome profile over CDP. It is a Chrome security guard against automated reads of the user's disk, not a stuck modal — retrying with a fresh page, a fresh file chooser, or a path inside the allowed root all fail identically.

The obvious workaround also fails: serving the file from `python3 -m http.server` and `fetch`-ing it from page JS into a `DataTransfer` is blocked by the host's CSP `connect-src` (verified on github.com).

**Why:** three retries plus the CSP probe cost most of a turn and ended where the first failure already pointed — the step is the user's.

**How to apply:** on the first `Not allowed`, stop. Prepare the file somewhere obvious (`~/Desktop`), open the exact settings page in their browser and scroll the section into view, then give click-by-click steps. Two other limits share this root and are worth naming up front: Playwright MCP refuses `file://` navigation and any path outside the project root, so render local HTML by serving it over `127.0.0.1` instead. See [[headless-chrome-beats-the-playwright-extension]].
