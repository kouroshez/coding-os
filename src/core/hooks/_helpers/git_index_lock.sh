#!/usr/bin/env bash
# git_index_lock.sh — sourceable: pre-emptively serialize index-taking git ops
# under multi-agent contention. When .git/index.lock is held by a concurrent
# commit, wait (bounded) for it to clear so this command doesn't fail with
# "Unable to create '.git/index.lock': File exists". A VERIFIED-stale lock
# (mtime older than a normal commit could ever take) is removed exactly once —
# never a blind delete. Fail-open: always returns 0 so it never blocks a commit.
#
# Tunables: COS_GIT_LOCK_WAIT_ITERS (default 50 * 0.2s = 10s ceiling),
#           COS_GIT_LOCK_STALE_SECS (default 20s = stale threshold).

cos_wait_for_git_index_lock() {
  local git_dir lock i=0 now mtime age
  local max="${COS_GIT_LOCK_WAIT_ITERS:-50}"
  local stale="${COS_GIT_LOCK_STALE_SECS:-20}"

  git_dir="$(git rev-parse --git-dir 2>/dev/null)" || return 0
  lock="${git_dir}/index.lock"

  while [ -e "$lock" ] && [ "$i" -lt "$max" ]; do
    now="$(date +%s)"
    # GNU stat -c first: BSD-first probing is unsafe — GNU `stat -f %m FILE`
    # exits 0 and prints filesystem info (%m parsed as a file operand), so the
    # BSD arm poisons mtime on Linux instead of falling through.
    mtime="$(stat -c %Y "$lock" 2>/dev/null || stat -f %m "$lock" 2>/dev/null || echo "$now")"
    age=$(( now - mtime ))
    if [ "$age" -ge "$stale" ]; then
      # The holder is long gone — a real commit would have finished by now.
      # Reap the stale lock once, then proceed.
      rm -f "$lock" 2>/dev/null || true
      break
    fi
    sleep 0.2
    i=$(( i + 1 ))
  done
  return 0
}
