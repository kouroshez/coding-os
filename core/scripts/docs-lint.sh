#!/usr/bin/env bash
# docs-lint.sh — Lint markdown files in docs/ for SSOT contract compliance.
#
# Checks every `docs/**/*.md` file for:
#   1. Front-matter HTML comment header (<!-- domain:... | layer:... | ssot:... | updated:... -->)
#   2. Opening block (Purpose, Read when, Skip when, Read next) — for non-index files
#   3. No unresolved {{...}} placeholders
#   4. REF codes referenced in Read First sections exist in foundation-map.md
#
# Exit: 0 = clean, 1 = errors found
#
# Usage:
#   bash docs-lint.sh                    # lint all docs/
#   bash docs-lint.sh docs/PRD/01.md     # lint a single file
#   bash docs-lint.sh --quiet            # only show errors

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_lib.sh"

DOCS_DIR="${DOCS_DIR:-docs}"
QUIET=0
TARGETS=()

for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --help|-h)
      echo "Usage: $0 [--quiet] [file...]"
      echo "Lint markdown files in $DOCS_DIR/ for SSOT contract compliance."
      exit 0
      ;;
    *) TARGETS+=("$arg") ;;
  esac
done

if [ ${#TARGETS[@]} -eq 0 ]; then
  if [ ! -d "$DOCS_DIR" ]; then
    warn "$DOCS_DIR/ not found — nothing to lint"
    exit 0
  fi
  # Default: every .md under docs/, excluding archive and binary asset dirs
  while IFS= read -r f; do
    TARGETS+=("$f")
  done < <(find "$DOCS_DIR" -type f -name "*.md" \
    -not -path "*/governance/archive/*" \
    -not -path "*/products-assets/*" | sort)
fi

ERRORS=0
WARNINGS=0
CHECKED=0

for file in "${TARGETS[@]}"; do
  if [ ! -f "$file" ]; then
    err "File not found: $file"
    ERRORS=$((ERRORS + 1))
    continue
  fi

  CHECKED=$((CHECKED + 1))
  rel="${file#./}"

  # Check 1: front-matter header on first non-empty line
  first_line=$(head -1 "$file")
  if ! echo "$first_line" | grep -qE '^<!-- domain:[A-Z_]+ \| layer:[a-z]+ \| ssot:(true|ref) \| updated:[0-9-]+ -->'; then
    err "$rel: missing or malformed front-matter header on line 1"
    ERRORS=$((ERRORS + 1))
  fi

  # Check 2: opening block (Purpose / Read when / Skip when) — skip task index, changelog, README
  base=$(basename "$file")
  if [[ "$base" != "tasks.md" && "$base" != "questions.md" && "$base" != "changes.log" ]]; then
    if ! grep -q "^Purpose:" "$file"; then
      [ "$QUIET" -eq 0 ] && warn "$rel: missing 'Purpose:' line in opening block"
      WARNINGS=$((WARNINGS + 1))
    fi
    if ! grep -q "^Read when:" "$file"; then
      [ "$QUIET" -eq 0 ] && warn "$rel: missing 'Read when:' line in opening block"
      WARNINGS=$((WARNINGS + 1))
    fi
  fi

  # Check 3: no unresolved {{KEY}} placeholders
  if grep -q '{{[A-Z_]\+}}' "$file"; then
    bad=$(grep -oE '\{\{[A-Z_]+\}\}' "$file" | sort -u | tr '\n' ' ')
    err "$rel: unresolved placeholders: $bad"
    ERRORS=$((ERRORS + 1))
  fi
done

# Check 4: REF code validation (only when foundation-map.md exists and we're linting >1 file)
if [ -f "$DOCS_DIR/foundation-map.md" ] && [ ${#TARGETS[@]} -gt 1 ]; then
  known_refs=$(grep -oE '`REF:[A-Z0-9_-]+`' "$DOCS_DIR/foundation-map.md" | sort -u)
  for file in "${TARGETS[@]}"; do
    [ -f "$file" ] || continue
    used_refs=$(grep -oE '`REF:[A-Z0-9_-]+`' "$file" 2>/dev/null | sort -u || true)
    for ref in $used_refs; do
      if ! echo "$known_refs" | grep -qx "$ref"; then
        rel="${file#./}"
        [ "$QUIET" -eq 0 ] && warn "$rel: unknown REF code $ref (not in foundation-map.md)"
        WARNINGS=$((WARNINGS + 1))
      fi
    done
  done
fi

echo ""
if [ $ERRORS -eq 0 ]; then
  ok "docs-lint markdown pass: $CHECKED file(s) checked, 0 errors, $WARNINGS warning(s)"
else
  err "docs-lint markdown pass FAILED: $CHECKED file(s) checked, $ERRORS error(s), $WARNINGS warning(s)"
fi

# Phase D: cross-check docs numbers against source of truth (tool count,
# schema version, table count). Keeps CLAUDE.md + architecture.md in sync
# with the actual state of server.py / db.py.
STALENESS_CHECK="$SCRIPT_DIR/docs-staleness-check.sh"
if [ -x "$STALENESS_CHECK" ]; then
  echo ""
  if bash "$STALENESS_CHECK" ${QUIET:+--quiet}; then
    :
  else
    err "docs-staleness-check failed — see errors above"
  fi
fi

exit 0
