#!/usr/bin/env bash
# search-enforce-inventory.sh — PreToolUse Bash (Phase O)
#
# PURPOSE
#   When the agent is about to run a bulk text replace (sed -i, xargs sed,
#   xargs python), extract the OLD pattern, store it in session state, and
#   emit a reminder to run ground-truth inventory grep before proceeding.
#
#   Does NOT run grep itself — full-repo grep exceeds PreToolUse timeout on
#   large codebases. Instead, surfaces the exact inventory command for the
#   agent to run. The companion PostToolUse hook (search-verify-remaining.sh)
#   runs a bounded verify grep after the replace.
#
# NON-BLOCKING — always exits 0.
#
# PATTERN EXTRACTION ORDER
#   1. grep -r*F "PATTERN" / 'PATTERN' (skill File-layer protocol)
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
if ! printf '%s' "$CMD" | command grep -qE 'sed[[:space:]]+-i|xargs[[:space:]]+-0[[:space:]]+(sed|python)'; then
    cos_log_hook search-enforce-inventory skip-not-replace 2>/dev/null || true
    exit 0
fi

# Extract OLD pattern — chr() avoids single-quote conflict in bash -c string
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
for pat in patterns:
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

# Store pattern for PostToolUse verify hook (no grep here — timeout risk)
STATE_DIR="${COS_AGENT_DIR:-.coding-os/claude}"
mkdir -p "$STATE_DIR" 2>/dev/null || true
SESSION_ID="$(cat "$COS_SESSION_FILE" 2>/dev/null || echo "unknown")"
printf '%s\t%s\n' "$SESSION_ID" "$OLD" > "${STATE_DIR}/.search-inventory" 2>/dev/null || true

cos_log_hook search-enforce-inventory "pattern=${OLD} stored" 2>/dev/null || true

cat >&2 <<MSG
🔎 Bulk replace detected — pattern: \`${OLD}\`
   If you have not run inventory yet:
     grep -rnF "${OLD}" . --exclude-dir=.git --exclude-dir=node_modules | wc -l
   That count is your ground truth — must reach 0 before declaring done.
MSG

exit 0
