---
name: codex-as-eyes-when-read-breaks
description: When the Read tool's hook host is unreachable, `codex exec -i <img>` inspects images; each failed Read costs ~20 minutes.
metadata:
  type: reference
---

`PreToolUse hook did not respond before its timeout (host client may be
unreachable)` on Read/Edit/Write means the VS Code extension host is saturated,
not that the file is bad. Observed at load average 63–231 with nine `Code Helper
(Renderer)` processes pinned near 100% CPU. Every failed call burns the full
~20-minute hook timeout, so **stop retrying after the second failure** — three
retries cost an hour.

Working substitutes while it is down:
- Read text with `sed -n '1,120p' file` via Bash.
- Write/patch files with a `python3 - <<'PYEOF'` heredoc from Bash.
- **Inspect images with Codex**: `codex exec --sandbox read-only
  --skip-git-repo-check -i a.png -i b.png < prompt.txt`. The prompt must come
  from stdin — a positional prompt after variadic `-i` is swallowed as another
  image. Say plainly that the review was done through a proxy, not by you.

Subagents do not help: they dispatch through the same host and fail identically.

Related: [[dry-run-in-repo-before-trusting-units]]
