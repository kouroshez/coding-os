---
name: headless-chrome-beats-the-playwright-extension
description: "For rendering HTML to a pixel-exact PNG, drive Chrome from the CLI — the Playwright MCP extension drops its relay mid-task."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6ff99fd1-cc12-4d3e-b39b-ac862d08b140
  modified: 2026-08-21T00:43:28.240Z
---

The Playwright MCP browser extension disconnects repeatedly during longer sessions ("Extension disconnected", then a new `mcpRelayUrl` each reconnect). It reconnects onto the *extension's own* connect page, so a `browser_take_screenshot` issued right after silently captures `Welcome — "claude-code" connected` instead of the target, and viewport size resets.

For deterministic rendering, skip it:

```bash
(python3 -m http.server 8899 --bind 127.0.0.1 &)
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=1 --window-size=1280,640 \
  --screenshot=out.png --virtual-time-budget=3000 http://127.0.0.1:8899/page.html
```

**Why:** this is the reliable path to a social card, an OG image, a diagram, or any pixel-exact deliverable — HTML/CSS gives crisp text that image models cannot, and headless Chrome renders it identically every run.

**How to apply:** reserve the extension for pages needing the user's logged-in session. Anything you author yourself, render via the CLI. When a screenshot must come from the extension, re-check the returned page URL before trusting the file. Related: [[browser-file-upload-blocked-via-cdp]], [[verify-generated-images-by-reading-them-back]].
