---
name: git-path-ops-ignore-untracked
description: "Path-scoped git ops skip untracked files in both directions — a repo-scanning test goes green on a blind spot, and `git commit <dir>` silently omits new files."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6fa96ac8-74bf-4312-9d92-4b169467cec9
  modified: 2026-08-23T18:22:16.046Z
---

`git ls-files` and `git commit <path>` both ignore untracked files, which bites twice in the same task:

- A test that enumerates the repo via `git ls-files` **cannot see a file you just created**. TASK-1019's `now_iso` parity gate passed green while `clock.py` was uncommitted, then failed the moment it was committed — the first green was a blind spot, not a pass.
- `git commit tests/golden/` staged only *modified tracked* files; eight newly rendered `timestamp-discipline.md` golden files were silently left out, which CI would have caught as parity drift.

**Why:** both commands operate on the index, and an untracked file is not in the index. Nothing errors — the file is simply absent from the result set, which reads exactly like "there was nothing to do."

**How to apply:** after a regen or any step that creates files, run `git status --short` and look for `??` lines *before* trusting a green scan-based test or a path-scoped commit. `git add <dir>` first, then commit. Re-run a repo-scanning gate once more after the commit that adds its new inputs. Sibling of [[fix-the-twin-of-every-guard-you-fix]]; the same "green means untested" shape as [[run-the-feature-not-just-its-tests]].
