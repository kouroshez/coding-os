#!/usr/bin/env bash
# Record a per-suite verification result to $COS_STATE_DIR/.last-verify.json
# Usage: record-verify.sh <suite-name> <PASS|FAIL>
# Example: record-verify.sh test-board_os PASS
#
# v2 (TASK-328): entries carry {git_head, dirty_digest, agent, session_tail}
# so freshness is commit-keyed, not time-only. Tree state comes from
# `verify_suites_cli tree-state` (single source — no bash/python drift); when
# it is unavailable the entry is written without the keys and is treated as
# stale by every v2 reader (fail-open, never blocks the recording itself).
# JSON write is serialized via Python fcntl.flock — flock(1) does not exist
# on stock macOS.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

SUITE="${1:?Usage: record-verify.sh <suite-name> <PASS|FAIL>}"
STATUS="${2:?Usage: record-verify.sh <suite-name> <PASS|FAIL>}"
VERIFY_FILE="${COS_STATE_DIR}/.last-verify.json"
TIMESTAMP=$(date +%s)

# Also write the legacy flat file for backward compatibility
echo "$STATUS" > "${COS_STATE_DIR}/.last-verify"

PROJECT_ROOT="${COS_PROJECT_ROOT:-$(pwd)}"
if command -v uv >/dev/null 2>&1; then
  PYRUN=(uv run --quiet python)
else
  PYRUN=(python3)
fi
TREE_JSON=$(cd "$PROJECT_ROOT" && "${PYRUN[@]}" -m core.board_os.verify_suites_cli tree-state 2>/dev/null) || TREE_JSON='{}'
[[ -n "$TREE_JSON" ]] || TREE_JSON='{}'

AGENT="${COS_AGENT:-}"
SESSION_TAIL="${COS_PANEL_ID:-}"
SESSION_TAIL="${SESSION_TAIL: -8}"

python3 -c "
import fcntl, json, os, sys

suite, status, ts, path, tree_json, agent, session_tail = sys.argv[1:8]
entry = {'status': status, 'ts': int(ts)}
try:
    tree = json.loads(tree_json)
except json.JSONDecodeError:
    tree = {}
if tree.get('git_head'):
    entry['git_head'] = tree['git_head']
    entry['dirty_digest'] = tree.get('dirty_digest', '')
if agent:
    entry['agent'] = agent
if session_tail:
    entry['session_tail'] = session_tail

with open(path + '.lock', 'w') as lk:
    fcntl.flock(lk, fcntl.LOCK_EX)
    data = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    data[suite] = entry
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
" "$SUITE" "$STATUS" "$TIMESTAMP" "$VERIFY_FILE" "$TREE_JSON" "$AGENT" "$SESSION_TAIL"
