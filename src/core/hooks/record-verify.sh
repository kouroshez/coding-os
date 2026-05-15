#!/usr/bin/env bash
# Record a per-suite verification result to $COS_STATE_DIR/.last-verify.json
# Usage: record-verify.sh <suite-name> <PASS|FAIL>
# Example: record-verify.sh test-backend PASS
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

SUITE="${1:?Usage: record-verify.sh <suite-name> <PASS|FAIL>}"
STATUS="${2:?Usage: record-verify.sh <suite-name> <PASS|FAIL>}"
VERIFY_FILE="${COS_STATE_DIR}/.last-verify.json"
TIMESTAMP=$(date +%s)

# Also write the legacy flat file for backward compatibility
echo "$STATUS" > "${COS_STATE_DIR}/.last-verify"

# Create or update the JSON file using Python (guaranteed available)
python3 -c "
import json, sys, os

suite = sys.argv[1]
status = sys.argv[2]
ts = int(sys.argv[3])
path = sys.argv[4]

data = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}

data[suite] = {'status': status, 'ts': ts}

with open(path, 'w') as f:
    json.dump(data, f, indent=2)
" "$SUITE" "$STATUS" "$TIMESTAMP" "$VERIFY_FILE"
