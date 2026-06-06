#!/usr/bin/env bash
# PostToolUse Write|Edit hook: nudge about test file after code changes.
#
# Goal: prevent shipping untested code. This is a soft reminder only —
# many edits legitimately don't need tests (renaming, docstring, trivial
# typo fix). Blocking would be noisy. A one-line nudge is cheap and
# catches the "I forgot to update the test" case that's the common one.
#
# Heuristic: after Edit/Write on a code file that is NOT itself a test,
# look for a sibling test file. Two search patterns:
#   Python:      test_<basename>.py  or  <basename>_test.py
#   JS/TS:       <basename>.test.ts(x)  or  <basename>.spec.ts(x)
# If no test file exists, suggest a path. If one exists, print it.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

# Only nudge on code files that could have tests.
case "$FILE_PATH" in
  *.py|*.ts|*.tsx|*.js|*.jsx) ;;
  *) exit 0 ;;
esac

# Skip test files, migrations, caches, internal state.
BASENAME_FILE=$(basename "$FILE_PATH")
case "$BASENAME_FILE" in
  test_*|*_test.*|*.test.*|*.spec.*|conftest.py) exit 0 ;;
esac
case "$FILE_PATH" in
  */tests/*|*/__pycache__/*|*/migrations/*|*/node_modules/*) exit 0 ;;
  */.venv/*|*/.coding-os/*|*/.claude/*|*/.codex/*) exit 0 ;;
esac

BASE="${BASENAME_FILE%.*}"
EXT="${BASENAME_FILE##*.}"
DIR=$(dirname "$FILE_PATH")

# Walk up from DIR to find the nearest project root (has pyproject.toml,
# package.json, or .coding-os.yaml). Fall back to cwd.
ROOT="$DIR"
while [[ "$ROOT" != "/" ]]; do
  if [[ -f "$ROOT/pyproject.toml" ]] || [[ -f "$ROOT/package.json" ]] || [[ -f "$ROOT/.coding-os.yaml" ]]; then
    break
  fi
  ROOT=$(dirname "$ROOT")
done
[[ "$ROOT" == "/" ]] && ROOT="$PWD"

# Debounce: remind at most once per file per session. The find
# scan below sweeps up to ~6k files under ROOT; repeating it on every edit of
# the same file is the dominant per-edit cost of this hook. The marker dir is
# cleared each SessionStart (session-context.sh).
_TFR_DIR="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os/claude}}/.test-first-reminded"
mkdir -p "$_TFR_DIR" 2>/dev/null || true
_TFR_KEY=$(printf '%s' "$FILE_PATH" | tr -c 'A-Za-z0-9' '_' | cut -c1-80)
[[ -f "$_TFR_DIR/$_TFR_KEY" ]] && exit 0
touch "$_TFR_DIR/$_TFR_KEY" 2>/dev/null || true

# Candidate test filenames by extension.
CANDIDATES=()
case "$EXT" in
  py)
    CANDIDATES+=("test_${BASE}.py" "${BASE}_test.py") ;;
  ts|tsx|js|jsx)
    CANDIDATES+=("${BASE}.test.${EXT}" "${BASE}.spec.${EXT}") ;;
esac

FOUND=""
for name in "${CANDIDATES[@]}"; do
  # find up to 2 matches anywhere under ROOT (shallow limit)
  match=$(find "$ROOT" -maxdepth 6 -name "$name" -not -path "*/node_modules/*" -not -path "*/.venv/*" 2>/dev/null | head -1)
  if [[ -n "$match" ]]; then
    FOUND="$match"
    break
  fi
done

echo ""
if [[ -n "$FOUND" ]]; then
  REL="${FOUND#$ROOT/}"
  echo "  🧪 [test] Code edited. Related test file:"
  echo "     → $REL"
  echo "     Keep it in sync — run the suite before \`cos task-done\`."
else
  # Suggest a canonical location.
  case "$EXT" in
    py)
      SUGGEST="$(dirname "$FILE_PATH")/test_${BASE}.py"
      ;;
    *)
      SUGGEST="$(dirname "$FILE_PATH")/${BASE}.test.${EXT}"
      ;;
  esac
  REL_SUGGEST="${SUGGEST#$ROOT/}"
  echo "  🧪 [test] Code edited but no companion test file found."
  echo "     Suggested: $REL_SUGGEST"
  echo "     Reminder only — skip if this edit genuinely doesn't need a test."
fi

exit 0
