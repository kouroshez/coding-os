#!/usr/bin/env bash
# docs-lint.sh — Lint markdown files in docs/ for SSOT contract compliance.
#
# Checks every `docs/**/*.md` file for:
#   1. Front-matter HTML comment header (<!-- domain:... | layer:... | ssot:... | updated:... -->)
#   2. Opening block (Purpose, Read when, Skip when, Read next) — for non-index files
#   3. No unresolved {{...}} placeholders
#   4. REF codes referenced in Read First sections exist in _meta/foundation-map.md
#
# Exit: 0 = clean, 1 = errors found
#
# Usage:
#   bash docs-lint.sh                    # lint all docs/
#   bash docs-lint.sh docs/prd/01.md     # lint a single file
#   bash docs-lint.sh --quiet            # only show errors

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_lib.sh"

DOCS_DIR="${DOCS_DIR:-docs}"
QUIET=0
CHANGED=0
TARGETS=()

# Canonical taxonomy enums — SSOT mirror of docs/governance/docs-system.md.
# Frontmatter domain/layer are validated against these; unknown values are
# flagged (warn by default; error+gate under COS_DOCS_LINT_STRICT=1). The
# XXX / STACK_DOMAIN domain values are template fill-in placeholders, kept
# valid so skeleton templates don't trip the check.
DOMAIN_ENUM="ALL CORE META ADAPTERS DOCS OPS INFRA SECURITY PRODUCT BACKEND FRONTEND AI MOBILE API ARCH XXX STACK_DOMAIN"
LAYER_ENUM="index policy playbook spec adr reference runbook postmortem task engineering architecture template plan contract checklist"
STRICT="${COS_DOCS_LINT_STRICT:-0}"

for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --changed) CHANGED=1 ;;
    --help|-h)
      echo "Usage: $0 [--quiet] [--changed] [file...]"
      echo "Lint markdown files in $DOCS_DIR/ for SSOT contract compliance."
      echo "  --changed  lint only docs/*.md changed vs \$COS_DOCS_LINT_BASE (default HEAD)"
      exit 0
      ;;
    *) TARGETS+=("$arg") ;;
  esac
done

# --changed: lint only docs/*.md changed vs the base (CI runs this strict on the
# PR diff; locally it defaults to the working tree). Same exclusions as the
# default-all scan. New/changed docs gate (strict in CI); legacy stays advisory.
if [ "$CHANGED" -eq 1 ] && [ ${#TARGETS[@]} -eq 0 ]; then
  base="${COS_DOCS_LINT_BASE:-HEAD}"
  while IFS= read -r f; do
    [ -n "$f" ] && [ -f "$f" ] && TARGETS+=("$f")
  done < <(git diff --name-only --diff-filter=ACMR "$base" -- "$DOCS_DIR" 2>/dev/null \
    | grep -E '\.md$' \
    | grep -vE '/(governance/archive|products-assets|code-os-core-docs|tasks)/' \
    | grep -vF 'docs/governance/_templates/task-detail.md' || true)
  if [ ${#TARGETS[@]} -eq 0 ]; then
    [ "$QUIET" -eq 0 ] && ok "docs-lint --changed: no changed docs/*.md to lint" >&2
    exit 0
  fi
fi

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
    -not -path "*/_templates/task-detail.md" \
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
  else
    # Check 1b: domain + layer must be in the canonical enums.
    # Warn by default; error + gate under COS_DOCS_LINT_STRICT=1.
    dom=$(echo "$first_line" | sed -E 's/^<!-- domain:([A-Z_]+) .*/\1/')
    lay=$(echo "$first_line" | sed -E 's/^.* \| layer:([a-z]+)( \||$).*/\1/')
    case " $DOMAIN_ENUM " in
      *" $dom "*) ;;
      *) if [ "$STRICT" = "1" ]; then err "$rel: domain '$dom' not in canonical enum"; ERRORS=$((ERRORS + 1));
         else [ "$QUIET" -eq 0 ] && warn "$rel: domain '$dom' not in canonical enum"; WARNINGS=$((WARNINGS + 1)); fi ;;
    esac
    case " $LAYER_ENUM " in
      *" $lay "*) ;;
      *) if [ "$STRICT" = "1" ]; then err "$rel: layer '$lay' not in canonical enum"; ERRORS=$((ERRORS + 1));
         else [ "$QUIET" -eq 0 ] && warn "$rel: layer '$lay' not in canonical enum"; WARNINGS=$((WARNINGS + 1)); fi ;;
    esac
  fi

  # Check 2: opening block — accept long form (Purpose:/Read when:) or short
  # form blockquote (`> P:` / `> R:`). Skip task
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
    # D1-F4 (TASK-128): nav breadcrumb keeps docs discoverable (`> Nav: ...`).
    if ! grep -qE "^>[[:space:]]*Nav:" "$file"; then
      [ "$QUIET" -eq 0 ] && warn "$rel: missing '> Nav:' breadcrumb"
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

# Check 4: REF code validation (only when _meta/foundation-map.md exists and we're linting >1 file)
if [ -f "$DOCS_DIR/_meta/foundation-map.md" ] && [ ${#TARGETS[@]} -gt 1 ]; then
  # Resolve _meta/foundation-map.md absolute path so we can skip it from being
  # scanned against itself — its own REF definitions otherwise get
  # flagged as "unknown usages" by the loop below.
  fm_abs=$(cd "$(dirname "$DOCS_DIR/_meta/foundation-map.md")" && pwd)/foundation-map.md
  known_refs=$(grep -oE '`REF:[A-Z0-9_-]+`' "$DOCS_DIR/_meta/foundation-map.md" | sort -u)
  for file in "${TARGETS[@]}"; do
    [ -f "$file" ] || continue
    # Skip foundation-map.md itself — its body contains every REF code by
    # definition. Compare absolute paths so `./docs/_meta/foundation-map.md` and
    # `docs/_meta/foundation-map.md` both match.
    file_abs=$(cd "$(dirname "$file")" && pwd)/$(basename "$file")
    [ "$file_abs" = "$fm_abs" ] && continue
    used_refs=$(grep -oE '`REF:[A-Z0-9_-]+`' "$file" 2>/dev/null | sort -u || true)
    for ref in $used_refs; do
      if ! printf '%s\n' "$known_refs" | grep -Fqx "$ref"; then
        rel="${file#./}"
        [ "$QUIET" -eq 0 ] && warn "$rel: unknown REF code $ref (not in _meta/foundation-map.md)"
        WARNINGS=$((WARNINGS + 1))
      fi
    done
  done
fi

# Check 5: risk-register expiry + tracking discipline. Each active
# `- `RISK-NNN`` line must carry review-by:YYYY-MM-DD + tracking:<ref>; a
# past-due review-by is flagged for re-triage. YYYY-MM-DD sorts chronologically
# as a string, so the date compare needs no parsing. Non-fatal (accumulates into
# ERRORS, gated only under STRICT — `err` would exit on the first hit), so every
# offending risk is reported in one pass. Empty register passes.
RISK_REGISTER="$DOCS_DIR/governance/risk-register.md"
if [ -f "$RISK_REGISTER" ]; then
  today=$(date +%Y-%m-%d)
  while IFS= read -r line; do
    rid=$(echo "$line" | grep -oE 'RISK-[0-9]+' | head -1)
    if ! echo "$line" | grep -qE 'review-by:[[:space:]]*[0-9]{4}-[0-9]{2}-[0-9]{2}'; then
      echo "ERROR: risk-register.md: $rid missing 'review-by:YYYY-MM-DD'" >&2
      ERRORS=$((ERRORS + 1))
      continue
    fi
    if ! echo "$line" | grep -qE 'tracking:[[:space:]]*[^[:space:]]'; then
      echo "ERROR: risk-register.md: $rid missing 'tracking:<task|issue>'" >&2
      ERRORS=$((ERRORS + 1))
      continue
    fi
    review_by=$(echo "$line" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | head -1)
    if [[ "$review_by" < "$today" ]]; then
      echo "ERROR: risk-register.md: $rid review-by $review_by is past-due — re-triage or close" >&2
      ERRORS=$((ERRORS + 1))
    fi
  done < <(grep -E '^- `RISK-[0-9]+`' "$RISK_REGISTER" 2>/dev/null || true)
fi

echo ""
if [ $ERRORS -eq 0 ]; then
  ok "docs-lint markdown pass: $CHECKED file(s) checked, 0 errors, $WARNINGS warning(s)" >&2
else
  err "docs-lint markdown pass FAILED: $CHECKED file(s) checked, $ERRORS error(s), $WARNINGS warning(s)"
fi

# Cross-check docs numbers against source of truth (tool count,
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

# Advisory by default (exit 0) — preserves today's non-gating behaviour so the
# pre-existing no-frontmatter backlog doesn't break the build. Flip to
# gating once that backlog clears: COS_DOCS_LINT_STRICT=1 → exit 1 on errors.
if [ "$STRICT" = "1" ] && [ "$ERRORS" -gt 0 ]; then
  exit 1
fi
exit 0
