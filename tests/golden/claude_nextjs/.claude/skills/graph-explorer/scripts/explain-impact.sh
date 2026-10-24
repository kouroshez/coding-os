#!/usr/bin/env bash
# Pretty-print cos_graph_impact output for human review.
# Reads JSON from stdin (the raw envelope from cos_graph_impact) and
# renders it as a tier-grouped checklist suitable for a human reviewer
# or a PR description.
#
# Usage:
#   cos_graph_impact <uid> | bash explain-impact.sh
#
# Falls back to readable output even if jq is missing.
set -euo pipefail

# Safety: ensure core POSIX tools resolvable even when caller PATH is restricted.
export PATH="/usr/bin:/bin:/usr/local/bin:${PATH:-}"

if ! command -v jq >/dev/null 2>&1; then
  echo "[explain-impact] jq not installed — emitting raw JSON" >&2
  cat
  exit 0
fi

INPUT="$(cat)"

# Envelope check
if ! echo "$INPUT" | jq -e '.ok' >/dev/null 2>&1; then
  err_cat=$(echo "$INPUT" | jq -r '.error.category // "unknown"')
  err_msg=$(echo "$INPUT" | jq -r '.error.message // "no message"')
  echo "FAIL: cos_graph_impact returned $err_cat — $err_msg" >&2
  exit 1
fi

ROOT=$(echo "$INPUT" | jq -r '.data.root_uid // .data.uid // "(unknown)"')
TOTAL=$(echo "$INPUT" | jq -r '.data.edges | length // 0')

cat <<EOF
# Impact analysis — $ROOT
Total edges: $TOTAL

EOF

# Group by tier. Tiers (per graph-explorer SKILL.md): strong / weak / context.
for tier in strong weak context; do
  count=$(echo "$INPUT" | jq -r --arg t "$tier" '[.data.edges[] | select((.tier // "context") == $t)] | length')
  if [ "$count" -eq 0 ]; then
    continue
  fi
  cat <<EOF
## $tier tier ($count)

EOF
  echo "$INPUT" | jq -r --arg t "$tier" '
    .data.edges[]
    | select((.tier // "context") == $t)
    | "- \(.kind) — `\(.target_uid)` (conf=\(.confidence // "?"))\(if .file_path then " — \(.file_path):\(.start_line // "?")" else "" end)"'
  echo
done

# Optional: rename-plan hint if many sites
if [ "$TOTAL" -gt 10 ]; then
  cat <<'EOF'
> **Heads-up:** > 10 affected sites. Consider running `cos_graph_rename_plan`
> for a sequenced edit checklist before opening any `Edit`.
EOF
fi
