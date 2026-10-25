---
name: playwright-extension-tab-is-hidden
description: "The Playwright MCP extension drives a background tab of the user's own Brave: it is visibilityState=hidden and shares their socket pool."
metadata:
  type: reference
  verified: 2026-10-25
---

The Playwright MCP here runs with `"extension": true` (`~/.playwright-mcp/config.json`), so it attaches to a tab in the user's real Brave profile rather than launching its own browser. Two consequences surfaced while debugging the Hub:

- **The tab is `document.visibilityState === 'hidden'`.** `requestAnimationFrame` is paused there, so `locator.click()` waits forever on Playwright's "visible, enabled and stable" check and times out at 30 s. Click with `page.evaluate(() => el.click())`, and set inputs through the native value setter plus an `input` event.
- **It shares the user's HTTP/1.1 connection pool (6 per origin).** Hub tabs the user has open count against the same pool, so a navigation stall seen in Playwright can be caused by tabs outside it. Count with `lsof -nP -iTCP:9188 -sTCP:ESTABLISHED` before blaming the server, and time the server separately with `curl`.

Related: [[headless-chrome-beats-the-playwright-extension]], [[browser-file-upload-blocked-via-cdp]].
