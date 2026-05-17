#!/usr/bin/env bash
# Cynefin + dimension-count classifier helper for the Complexity Gate.
# Interactive: walks the agent through Q1 (Cynefin domain) + Q2 (dimensions)
# and emits a single-line classification suitable for write-state.sh.
#
# Usage:
#   bash classify.sh                # interactive, asks both questions
#   bash classify.sh --q1 COMPLICATED --q2 3   # non-interactive shortcut
#   bash classify.sh --print-only --q1 COMPLEX --q2 5  # echo without writing
#
# Output: emits the classification line (e.g. "COMPLICATED 3") to stdout
# and, by default, writes it to $COS_AGENT_DIR/.thinking_os-gate via
# write-state.sh (the canonical gate-marker script).
set -euo pipefail

# Safety: ensure core POSIX tools resolvable even when caller PATH is restricted.
export PATH="/usr/bin:/bin:/usr/local/bin:${PATH:-}"

# ── Argument parsing ────────────────────────────────────────────────
Q1=""
Q2=""
PRINT_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --q1) Q1="$2"; shift 2 ;;
    --q2) Q2="$2"; shift 2 ;;
    --print-only) PRINT_ONLY=1; shift ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ── Non-interactive safety: refuse to prompt when stdin isn't a TTY ──
# An agent calling this script in batch mode must pass --q1/--q2;
# otherwise we'd silently hang on `read` or accept empty input.
if [ -z "$Q1" ] || [ -z "$Q2" ]; then
  if [ ! -t 0 ]; then
    echo "[classify] non-interactive context detected — pass --q1 <CLEAR|COMPLICATED|COMPLEX|CHAOTIC|CONFUSION> --q2 <N>" >&2
    exit 2
  fi
fi

# ── Interactive prompts (only if not provided) ──────────────────────
if [ -z "$Q1" ]; then
  cat >&2 <<'EOF'

Q1 — Problem nature (Cynefin)
  1) CLEAR        — known solution, just do it
  2) COMPLICATED  — known type, details need analysis
  3) COMPLEX      — unknown answer until tested
  4) CHAOTIC      — broken NOW, act first
  5) CONFUSION    — can't classify; decompose first

EOF
  read -r -p "Choose 1-5: " choice
  case "$choice" in
    1) Q1=CLEAR ;;
    2) Q1=COMPLICATED ;;
    3) Q1=COMPLEX ;;
    4) Q1=CHAOTIC ;;
    5) Q1=CONFUSION ;;
    *) echo "Invalid choice: $choice" >&2; exit 2 ;;
  esac
fi

# Validate
case "$Q1" in
  CLEAR|COMPLICATED|COMPLEX|CHAOTIC|CONFUSION) ;;
  *) echo "Invalid Q1: $Q1 (must be one of CLEAR|COMPLICATED|COMPLEX|CHAOTIC|CONFUSION)" >&2; exit 2 ;;
esac

if [ -z "$Q2" ]; then
  cat >&2 <<'EOF'

Q2 — Dimensions involved
  1     — single pass, no Zoom needed
  2-4   — standard Zoom cycle
  5+    — full Zoom with Dimension Map
  8+    — break into separate problems (consider CONFUSION)

EOF
  read -r -p "Dimensions (integer): " Q2
fi

# Validate integer
if ! [[ "$Q2" =~ ^[0-9]+$ ]]; then
  echo "Invalid Q2: $Q2 (must be a non-negative integer)" >&2
  exit 2
fi

# ── Emit + persist ──────────────────────────────────────────────────
CLASSIFICATION="$Q1 $Q2"
echo "$CLASSIFICATION"

if [ "$PRINT_ONLY" -eq 1 ]; then
  exit 0
fi

# Compute target state file path. Prefer cos-env.sh contract; fall back
# to .coding-os/<agent>/.thinking_os-gate.
AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-unknown}}"
GATE_FILE="$AGENT_DIR/.thinking_os-gate"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
WRITE_STATE="$REPO_ROOT/src/core/hooks/write-state.sh"
[[ ! -f "$WRITE_STATE" ]] && WRITE_STATE="$REPO_ROOT/core/hooks/write-state.sh"
[[ ! -f "$WRITE_STATE" ]] && WRITE_STATE="$REPO_ROOT/.claude/hooks/write-state.sh"

if [ -x "$WRITE_STATE" ] || [ -f "$WRITE_STATE" ]; then
  bash "$WRITE_STATE" "$GATE_FILE" "$CLASSIFICATION" >/dev/null 2>&1 || {
    echo "[classify] write-state.sh failed; gate not recorded" >&2
    exit 1
  }
  echo "[classify] gate recorded at $GATE_FILE" >&2
else
  echo "[classify] write-state.sh not found at $WRITE_STATE — gate NOT recorded" >&2
  exit 1
fi
