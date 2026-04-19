#!/usr/bin/env bash
# docs-nav-fix.sh — Auto-fix navigation breadcrumbs in docs/.
#
# Adds or repairs the `> Nav: [Docs Index](path)` line in markdown files
# under docs/ that don't already have one.
#
# Rules:
#   - Files in docs/ root → > Nav: [Docs Index](./00-index.md)
#   - Files in docs/<dir>/ → > Nav: [Docs Index](../00-index.md)
#   - Files in docs/<dir>/<subdir>/ → > Nav: [Docs Index](../../00-index.md)
#   - Skipped: tasks.md, questions.md, changes.log, archive/, products-assets/
#   - Skipped: files that already have a `> Nav:` line
#
# Usage:
#   bash docs-nav-fix.sh           # apply fixes
#   bash docs-nav-fix.sh --check   # report only, don't modify

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_lib.sh"

DOCS_DIR="${DOCS_DIR:-docs}"
CHECK_ONLY=0

case "${1:-}" in
  --check) CHECK_ONLY=1 ;;
  --help|-h)
    echo "Usage: $0 [--check]"
    echo "Auto-add missing > Nav: breadcrumbs in $DOCS_DIR/*.md"
    exit 0
    ;;
esac

if [ ! -d "$DOCS_DIR" ]; then
  warn "$DOCS_DIR/ not found — nothing to fix"
  exit 0
fi

FIXED=0
SKIPPED=0
NEEDS_FIX=0

while IFS= read -r file; do
  base=$(basename "$file")
  rel_path="${file#$DOCS_DIR/}"
  # Skip log-like files and the root index (it IS the index, doesn't link to itself)
  case "$base" in
    tasks.md|questions.md|changes.log) SKIPPED=$((SKIPPED + 1)); continue ;;
  esac
  # Root docs/00-index.md is the master index — no breadcrumb needed
  if [ "$rel_path" = "00-index.md" ]; then
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  # Skip if already has Nav line
  if grep -q "^> Nav:" "$file"; then
    SKIPPED=$((SKIPPED + 1))
    continue
  fi

  # Compute relative depth from docs/ root
  rel="${file#$DOCS_DIR/}"
  depth=$(awk -F'/' '{print NF - 1}' <<< "$rel")
  case "$depth" in
    0) prefix="./" ;;
    1) prefix="../" ;;
    2) prefix="../../" ;;
    3) prefix="../../../" ;;
    *) prefix="../../../../" ;;
  esac
  nav_line="> Nav: [Docs Index](${prefix}00-index.md)"

  NEEDS_FIX=$((NEEDS_FIX + 1))

  if [ $CHECK_ONLY -eq 1 ]; then
    info "would add to $rel: $nav_line"
    continue
  fi

  # Insert nav line after the H1 (the first line starting with `# `)
  python3 - "$file" "$nav_line" <<'PY'
import sys
path, nav_line = sys.argv[1], sys.argv[2]
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
out = []
inserted = False
for i, line in enumerate(lines):
    out.append(line)
    if not inserted and line.startswith('# '):
        # Insert after the H1 + a blank line
        if i + 1 < len(lines) and lines[i + 1].strip() == "":
            out.append("\n")
            out.append(nav_line + "\n")
        else:
            out.append("\n")
            out.append(nav_line + "\n")
            out.append("\n")
        inserted = True
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(out)
PY
  ok "fixed $rel"
  FIXED=$((FIXED + 1))
done < <(find "$DOCS_DIR" -type f -name "*.md" \
  -not -path "*/governance/archive/*" \
  -not -path "*/products-assets/*" | sort)

echo ""
if [ $CHECK_ONLY -eq 1 ]; then
  if [ $NEEDS_FIX -eq 0 ]; then
    ok "All files have Nav breadcrumbs ($SKIPPED skipped)"
    exit 0
  else
    warn "$NEEDS_FIX file(s) need Nav breadcrumbs (run without --check to fix)"
    exit 1
  fi
else
  ok "Fixed $FIXED file(s), skipped $SKIPPED"
fi
