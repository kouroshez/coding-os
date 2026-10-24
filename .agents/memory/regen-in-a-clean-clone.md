---
name: regen-in-a-clean-clone
description: "Golden capture and manifest regen bake in every file in the working tree, including another session's uncommitted hook; run them in a clone with only your diff applied."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 9ce9753f-dae9-468c-ae58-824973da3161
  modified: 2026-10-24T19:31:55.208Z
---

`make golden-capture` / `make manifest-regen` scaffold from the working tree, so an
untracked hook another session left in `src/core/hooks/` (wal-guard.sh, 2026-10-24)
lands in every golden section and the manifest. Committing that bakes someone
else's unfinished work into CI fixtures; skipping the capture leaves your own
hook edits stale in golden (they capture hook *content*, and the first failing
assertion is the "extra files" one, which hides the content drift).

**Why:** golden parity failed only on the foreign file, so the stale content of
four of my own hook commits went unnoticed until a clean-clone capture rewrote 149 files.

**How to apply:** `git clone --no-hardlinks . $SCRATCH/c`, `git diff -- <your
paths> | git -C $SCRATCH/c apply`, copy your new files in, run the regen there,
run `test_golden_parity.py` there (it must be green), then copy `tests/golden/`
(`rsync -a --delete`) and `src/core/scaffold_manifest.json` back. Never stash
another session's WIP to make room. See [[rules-edits-need-golden-capture]].
