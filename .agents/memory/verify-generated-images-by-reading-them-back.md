---
name: verify-generated-images-by-reading-them-back
description: "Never hand over an image you have not opened — `sips -c` crops rather than scales, and shipped a decapitated screenshot."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6ff99fd1-cc12-4d3e-b39b-ac862d08b140
  modified: 2026-08-21T00:43:41.742Z
---

I resized a 1600×790 screenshot to a 1280×640 social card with `sips -c 640 1280` and delivered it without looking. `-c` **crops** to that box; it does not scale. The result cut 160px off each side and 75px off top and bottom: the tab bar was sliced in half, words were cut mid-string at both edges, and the largest text on the card was an empty-state `$0.0000`. The operator's reaction was "این چه عکس افتضاحیه؟!".

Use `sips -Z <max>` or PIL to scale. But the resize flag is the small half of the lesson.

**Why:** dimensions were correct — 1280×640, under the size cap, valid PNG — so every check short of opening the file passed. Image defects are invisible to metadata, exactly as Rule 26 says of code: reading is not verification.

**How to apply:** `Read` every image before sending it, and state the specific defects you see rather than declaring it done. Four iterations each fixed a flaw only visible on inspection — a hard-cut edge, a leftover UI toolbar, a mask applied in the wrong direction. Two composition rules earned here: crop screenshots so no text is cut mid-word, and prefer a source whose own background matches the canvas (the graph view dissolved seamlessly where a panel screenshot always showed a seam). Related: [[generated-hero-banners-miss-the-readme-bar]], [[headless-chrome-beats-the-playwright-extension]].
