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
    -not -path "*/products-assets/*" \
    -not -path "*/code-os-core-docs/*" \
    -not -path "*/tasks/*" | sort)
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

  # Check 1: front-matter header on first non-empty line.
  # Required keys: domain · layer · ssot · updated. Extra middle keys
  # (e.g. `source:outcome_history#183` on breakthrough files) are tolerated.
  first_line=$(head -1 "$file")
  if ! echo "$first_line" | grep -qE '^<!-- domain:[A-Z_]+ \| layer:[a-z]+ \| ssot:(true|ref|false)( \| [a-z_]+:[^ ]+)* \| updated:[0-9-]+ -->'; then
    err "$rel: missing or malformed front-matter header on line 1"
    ERRORS=$((ERRORS + 1))
  fi

  # Check 2: opening block — accept long form (Purpose:/Read when:) or short
  # form blockquote (`> P:` / `> R:`). TASK-158 adopted both. Skip task
  # index, changelog, README.
  base=$(basename "$file")
  if [[ "$base" != "tasks.md" && "$base" != "questions.md" && "$base" != "changes.log" ]]; then
    if ! grep -qE "^(Purpose:|>\s*P:)" "$file"; then
      [ "$QUIET" -eq 0 ] && warn "$rel: missing Purpose line in opening block (expected 'Purpose:' or '> P:')"
      WARNINGS=$((WARNINGS + 1))
    fi
    if ! grep -qE "^(Read when:|>\s*R:)" "$file"; then
      [ "$QUIET" -eq 0 ] && warn "$rel: missing Read-when line in opening block (expected 'Read when:' or '> R:')"
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
  # Resolve foundation-map's absolute path so we can skip it from being
  # scanned against itself — its own REF definitions otherwise get
  # flagged as "unknown usages" by the loop below.
  fm_abs=$(cd "$(dirname "$DOCS_DIR/foundation-map.md")" && pwd)/foundation-map.md
  known_refs=$(grep -oE '`REF:[A-Z0-9_-]+`' "$DOCS_DIR/foundation-map.md" | sort -u)
  for file in "${TARGETS[@]}"; do
    [ -f "$file" ] || continue
    # Skip foundation-map.md itself — its body contains every REF code by
    # definition. Compare absolute paths so `./docs/foundation-map.md` and
    # `docs/foundation-map.md` both match.
    file_abs=$(cd "$(dirname "$file")" && pwd)/$(basename "$file")
    [ "$file_abs" = "$fm_abs" ] && continue
    used_refs=$(grep -oE '`REF:[A-Z0-9_-]+`' "$file" 2>/dev/null | sort -u || true)
    for ref in $used_refs; do
      if ! printf '%s\n' "$known_refs" | grep -Fqx "$ref"; then
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
