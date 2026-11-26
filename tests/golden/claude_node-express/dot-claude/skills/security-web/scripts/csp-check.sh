#!/usr/bin/env bash
# Probe an HTTP endpoint for Content-Security-Policy + other security
# headers (HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy,
# COOP, COEP, X-Frame-Options).
#
# Usage:
#   bash csp-check.sh https://example.com
#   bash csp-check.sh --strict https://example.com   # fails on missing headers
#   bash csp-check.sh --json https://example.com
#
# Exit codes:
#   0 = all required headers present (or non-strict mode)
#   1 = one or more required headers missing (only in --strict)
#   2 = curl error / bad URL

set -euo pipefail

# Safety: ensure core POSIX tools resolvable even when caller PATH is restricted.
export PATH="/usr/bin:/bin:/usr/local/bin:${PATH:-}"

STRICT=0
EMIT_JSON=0
URL=""

while [ $# -gt 0 ]; do
  case "$1" in
    --strict) STRICT=1; shift ;;
    --json) EMIT_JSON=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    -*) echo "Unknown flag: $1" >&2; exit 2 ;;
    *) URL="$1"; shift ;;
  esac
done

if [ -z "$URL" ]; then
  echo "usage: $0 [--strict] [--json] <url>" >&2
  exit 2
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not installed" >&2
  exit 2
fi

# Fetch headers only. -I = HEAD; some servers respond differently to HEAD
# vs GET so also try GET with -X GET and discard body.
HEADERS=$(curl -sS -L -D - -X GET -o /dev/null --max-time 10 "$URL" 2>&1) || {
  echo "curl failed for $URL" >&2
  exit 2
}

# Normalise: lowercase header names for grep
headers_lower=$(echo "$HEADERS" | tr 'A-Z' 'a-z')

# Required + recommended headers
declare -a REQUIRED=(
  "content-security-policy"
  "strict-transport-security"
  "x-content-type-options"
  "referrer-policy"
)
declare -a RECOMMENDED=(
  "permissions-policy"
  "cross-origin-opener-policy"
  "cross-origin-embedder-policy"
  "x-frame-options"
)

declare -a MISSING_REQ=()
declare -a MISSING_REC=()
declare -A PRESENT=()

check_header() {
  local h="$1"
  if echo "$headers_lower" | grep -qE "^${h}:"; then
    # Extract value (case-insensitive on header)
    local value
    value=$(echo "$HEADERS" | grep -iE "^${h}:" | head -1 | sed -E 's/^[^:]+:[[:space:]]*//' | tr -d '\r')
    PRESENT[$h]="$value"
    return 0
  fi
  return 1
}

for h in "${REQUIRED[@]}"; do
  if ! check_header "$h"; then
    MISSING_REQ+=("$h")
  fi
done

for h in "${RECOMMENDED[@]}"; do
  if ! check_header "$h"; then
    MISSING_REC+=("$h")
  fi
done

# Emit
if [ "$EMIT_JSON" -eq 1 ]; then
  # Build JSON manually (no jq dependency)
  printf '{\n  "url": "%s",\n  "missing_required": [' "$URL"
  first=1
  for h in "${MISSING_REQ[@]+"${MISSING_REQ[@]}"}"; do
    [ $first -eq 0 ] && printf ', '
    printf '"%s"' "$h"
    first=0
  done
  printf '],\n  "missing_recommended": ['
  first=1
  for h in "${MISSING_REC[@]+"${MISSING_REC[@]}"}"; do
    [ $first -eq 0 ] && printf ', '
    printf '"%s"' "$h"
    first=0
  done
  printf '],\n  "present": {'
  first=1
  for h in "${!PRESENT[@]}"; do
    [ $first -eq 0 ] && printf ', '
    # Naive JSON-escape: replace " with \" and \ with \\
    value="${PRESENT[$h]//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s": "%s"' "$h" "$value"
    first=0
  done
  printf '}\n}\n'
else
  echo "Security header probe — $URL"
  echo
  if [ "${#MISSING_REQ[@]}" -gt 0 ]; then
    echo "MISSING (required):"
    for h in "${MISSING_REQ[@]}"; do
      echo "  - $h"
    done
    echo
  fi
  if [ "${#MISSING_REC[@]}" -gt 0 ]; then
    echo "Missing (recommended):"
    for h in "${MISSING_REC[@]}"; do
      echo "  - $h"
    done
    echo
  fi
  if [ "${#PRESENT[@]}" -gt 0 ]; then
    echo "Present:"
    for h in "${!PRESENT[@]}"; do
      printf "  %-32s %s\n" "$h:" "${PRESENT[$h]}"
    done
  fi
fi

if [ "$STRICT" -eq 1 ] && [ "${#MISSING_REQ[@]}" -gt 0 ]; then
  exit 1
fi
exit 0
