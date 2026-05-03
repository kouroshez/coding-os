#!/usr/bin/env bash
# search-enforce-inventory.sh — PreToolUse Bash (Phase O)
#
# PURPOSE
#   When the agent is about to run a bulk text replace (sed -i, xargs sed,
#   python replace), extract the OLD pattern, run a ground-truth inventory
#   grep BEFORE the edit, and store count + pattern in session state so the
#   companion verify hook can compare after.
#
#   Surfaces: "Ground truth: N matches in X files" before the agent edits —
#   so it knows exactly how many sites to update and cannot declare done early.
#
# NON-BLOCKING — always exits 0.
#
# PATTERN EXTRACTION ORDER
#   1. grep -r*F "PATTERN" / 'PATTERN' (from File-layer protocol in search skill)
#   2. OLD="PATTERN" / OLD='PATTERN' env assignment
#   3. sed 's|OLD|NEW|g' / 's/OLD/NEW/g' expression
#   Falls through to no-op when none match or pattern < 2 chars.

set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
cos_log_hook search-enforce-inventory entry 2>/dev/null || true

PAYLOAD="$(cat 2>/dev/null || true)"
[[ -z "$PAYLOAD" ]] && exit 0

CMD="$(printf '%s' "$PAYLOAD" | python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read() or "{}")
    print(d.get("tool_input", {}).get("command", ""))
except Exception:
    pass
' 2>/dev/null || true)"
[[ -z "$CMD" ]] && exit 0

# Only fire on bulk replace operations (sed -i, xargs sed, xargs python)
if ! printf '%s' "$CMD" | grep -qE 'sed[[:space:]]+-i|xargs[[:space:]]+-0[[:space:]]+(sed|python)'; then
    cos_log_hook search-enforce-inventory skip-not-replace 2>/dev/null || true
    exit 0
fi

# Extract OLD pattern — try multiple forms, using chr() to avoid single-quote
# conflict inside bash single-quoted -c string
OLD="$(printf '%s' "$CMD" | python3 -c '
import sys, re
cmd = sys.stdin.read()
dq = chr(34)
sq = chr(39)

patterns = [
    # 1a. grep flags "PATTERN"
    r"grep\s+\S+(?:\s+-\S+)*\s+" + dq + r"([^" + dq + r"]{2,80})" + dq,
    # 1b. grep flags '"'"'PATTERN'"'"'
    r"grep\s+\S+(?:\s+-\S+)*\s+" + sq + r"([^" + sq + r"]{2,80})" + sq,
    # 2a. OLD="PATTERN"
    r"OLD=" + dq + r"([^" + dq + r"]{2,80})" + dq,
    # 2b. OLD='"'"'PATTERN'"'"'
    r"OLD=" + sq + r"([^" + sq + r"]{2,80})" + sq,
    # 3. sed '"'"'s|OLD|NEW|'"'"' or '"'"'s/OLD/NEW/'"'"'
    r"sed\s+\S+\s+[" + dq + sq + r"]s([|/,!])([^|/,!\n]{2,80})\1",
]
for i, pat in enumerate(patterns):
    m = re.search(pat, cmd)
    if m:
        grps = m.groups()
        print(grps[-1].strip())
        break
' 2>/dev/null || true)"

if [[ -z "$OLD" || "${#OLD}" -lt 2 ]]; then
    cos_log_hook search-enforce-inventory skip-no-pattern 2>/dev/null || true
    exit 0
fi

# Ground-truth inventory grep
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT" || exit 0

EXCL="--exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist
  --exclude-dir=build --exclude-dir=__pycache__ --exclude-dir=.next
  --exclude-dir=vendor"

COUNT="$(grep -rnF "$OLD" . $EXCL 2>/dev/null | wc -l | tr -d ' ' || echo "?")"
FILES="$(grep -rlF "$OLD" . $EXCL 2>/dev/null | wc -l | tr -d ' ' || echo "?")"

# Store ground truth for verify hook
STATE_DIR="${COS_AGENT_DIR:-.coding-os/claude}"
mkdir -p "$STATE_DIR" 2>/dev/null || true
SESSION_ID="$(cat "$COS_SESSION_FILE" 2>/dev/null || echo "unknown")"
printf '%s\t%s\t%s\n' "$SESSION_ID" "$OLD" "$COUNT" > "${STATE_DIR}/.search-inventory" 2>/dev/null || true

cos_log_hook search-enforce-inventory "pattern=${OLD} ground_truth=${COUNT}" 2>/dev/null || true

cat >&2 <<MSG
🔎 Search inventory — \`${OLD}\`
   Ground truth: ${COUNT} matches across ${FILES} file(s)
   Target: reach 0 before declaring done.
MSG

exit 0
