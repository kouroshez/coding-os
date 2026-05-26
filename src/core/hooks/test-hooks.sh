#!/usr/bin/env bash
# Comprehensive hook test suite — tests all hooks with expected results (agent-agnostic)
set -uo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

PASS=0
FAIL=0
TOTAL=0

HOOKS_DIR="$(dirname "$0")"

run_test() {
  local name="$1"
  local hook="$2"
  local input="$3"
  local expect_exit="$4"  # 0 = allow, 2 = block

  TOTAL=$((TOTAL + 1))
  local output
  output=$(echo "$input" | bash "$hook" 2>&1)
  local actual_exit=$?

  if [[ $actual_exit -eq $expect_exit ]]; then
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name (expected exit=$expect_exit, got exit=$actual_exit)"
    echo "        output: $output"
    FAIL=$((FAIL + 1))
  fi
}

echo "========================================"
echo "  HOOK TEST SUITE — $(date +%Y-%m-%d)"
echo "========================================"
echo ""

# ---- block-secrets.sh ----
echo "--- block-secrets.sh ---"
H="${HOOKS_DIR}/block-secrets.sh"

run_test "Block git add .env" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git add backend/.env"}}' 2

run_test "Allow git add .env.example" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git add .env.example"}}' 0

run_test "Block git commit --no-verify" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m fix"}}' 2

run_test "Block git add credentials.json" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git add credentials.json"}}' 2

run_test "Block live Stripe key in code" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/settings.py","new_string":"key = sk_live_51O2jKSDJFKSDJFKSDJFKSDJFabc"}}' 2

run_test "Block AWS access key" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/settings.py","new_string":"AKIAIOSFODNN7EXAMPLE"}}' 2

run_test "Block private key" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/key.py","new_string":"-----BEGIN RSA PRIVATE KEY-----"}}' 2

run_test "Allow secrets in .md docs" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"docs/security.md","new_string":"sk_live_example"}}' 0

run_test "Allow secrets in test files" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/tests/test_pay.py","new_string":"sk_live_example"}}' 0

run_test "Allow normal code" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","new_string":"def get_products():"}}' 0

echo ""

# ---- block-dangerous-commands.sh ----
echo "--- block-dangerous-commands.sh ---"
H="${HOOKS_DIR}/block-dangerous-commands.sh"

run_test "Block force push main" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' 2

run_test "Block git push -f main" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git push -f origin main"}}' 2

run_test "Block git reset --hard" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git reset --hard HEAD~3"}}' 2

run_test "Block git clean -f" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git clean -fd"}}' 2

run_test "Block DROP TABLE" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"psql -c DROP TABLE users"}}' 2

run_test "Block rm -rf root dirs" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"rm -rf backend"}}' 2

run_test "Block production migrate" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"python manage.py migrate --settings=config.settings.production"}}' 2

run_test "Allow normal git push" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"git push origin feature-branch"}}' 0

run_test "Allow normal ls" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' 0

run_test "Allow dev migrate" "$H" \
  '{"tool_name":"Bash","tool_input":{"command":"python manage.py migrate"}}' 0

echo ""

# ---- block-protected-files.sh ----
echo "--- block-protected-files.sh ---"
H="${HOOKS_DIR}/block-protected-files.sh"

run_test "Block changes.log edit" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"changes.log","old_string":"x","new_string":"y"}}' 2

run_test "Allow normal file edit" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

echo ""

# ---- block-bad-patterns.sh ----
echo "--- block-bad-patterns.sh ---"
H="${HOOKS_DIR}/block-bad-patterns.sh"

run_test "Block print() in backend app" "$H" \
  '{"tool_name":"Write","tool_input":{"file_path":"backend/apps/catalog/services.py","content":"    print(result)"}}' 2

run_test "Block .save() in views" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/views.py","new_string":"    product.save()"}}' 2

run_test "Block .delete() in views" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/views.py","new_string":"    product.delete()"}}' 2

run_test "Block ORM in views" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/views.py","new_string":"Product.objects.filter(active=True)"}}' 2

run_test "Block bare ValueError in services" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","new_string":"raise ValueError(\"bad\")"}}' 2

run_test "Block bare TODO" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","new_string":"# TODO fix this later"}}' 2

run_test "Allow TODO with task ref" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","new_string":"# TODO: TASK-123 fix this later"}}' 0

run_test "Block console.log in frontend" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"frontend/src/components/cart.tsx","new_string":"console.log(data)"}}' 2

run_test "Block any type in TypeScript" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"frontend/src/lib/api.ts","new_string":"const data: any = fetch()"}}' 2

run_test "Block backend secrets in frontend" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"frontend/src/lib/api.ts","new_string":"process.env.STRIPE_SECRET"}}' 2

run_test "Allow normal service code" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","new_string":"def create_product(data): return Product.objects.create(**data)"}}' 0

run_test "Allow test files" "$H" \
  '{"tool_name":"Write","tool_input":{"file_path":"backend/apps/catalog/tests/test_services.py","content":"print(result)"}}' 0

run_test "Block RunPython without reverse" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/migrations/0002_data.py","new_string":"RunPython(forward_func)"}}' 2

run_test "Allow RunPython with reverse" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/migrations/0002_data.py","new_string":"RunPython(forward_func, reverse_code=reverse_func)"}}' 0

echo ""

# ---- verify-changed-file.sh ----
echo "--- verify-changed-file.sh ---"
H="${HOOKS_DIR}/verify-changed-file.sh"

run_test "Fires for docs file" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"docs/roadmap.md"}}' 0

run_test "Fires for backend .py" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py"}}' 0

run_test "Fires for frontend .tsx" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"frontend/src/app/page.tsx"}}' 0

run_test "Silent for non-code" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"README.md"}}' 0

echo ""

# ---- session-context.sh ----
echo "--- session-context.sh ---"
H="${HOOKS_DIR}/session-context.sh"

run_test "Compact shows recovery" "$H" \
  '{"source":"compact"}' 0

run_test "Resume shows recovery" "$H" \
  '{"source":"resume"}' 0

run_test "Startup shows tasks" "$H" \
  '{"source":"startup"}' 0

echo ""

# ---- session-end.sh ----
echo "--- session-end.sh ---"
H="${HOOKS_DIR}/session-end.sh"

# session-end.sh is a Stop hook — test it doesn't hang and exits cleanly
# Use a subshell with background + timeout to detect hangs
_test_no_hang() {
  local name="$1"
  TOTAL=$((TOTAL + 1))
  echo '{"stop_reason":"end_session"}' | bash "$H" 2>/dev/null &
  local pid=$!
  local waited=0
  while kill -0 $pid 2>/dev/null && [ $waited -lt 5 ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if kill -0 $pid 2>/dev/null; then
    kill $pid 2>/dev/null
    echo "  FAIL  $name (hung for 5s)"
    FAIL=$((FAIL + 1))
  else
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  fi
}

_test_no_hang "Runs without hanging (piped stdin)"

echo ""

# ══════════════════════════════════════════════════════════════
# GATE SYSTEM TESTS
# These tests verify the Thinking OS enforcement hooks.
# They require temporary state files, created and cleaned up here.
# ══════════════════════════════════════════════════════════════

# Setup: create session state for gate tests
GATE_TEST_SESSION="ses-test-$(date +%s)"
ORIG_SESSION=""
if [[ -f "${COS_SESSION_FILE}" ]]; then
  ORIG_SESSION=$(cat "${COS_SESSION_FILE}")
fi
echo "$GATE_TEST_SESSION" > "${COS_SESSION_FILE}"

# Backup existing state files.
# .task-mode is included so classify-task-mode's per-turn marker can't
# silently skip enforce-{task-start,skill,zoom} tests when the dev's
# previous turn was tagged query/adhoc/chore/system.
for f in "${COS_AGENT_DIR}/.thinking_os-gate" "${COS_AGENT_DIR}/.task-current" "${COS_AGENT_DIR}/.active-skill" "${COS_AGENT_DIR}/.zoom-checkpoint" "${COS_AGENT_DIR}/.task-mode"; do
  [[ -f "$f" ]] && cp "$f" "${f}.bak" 2>/dev/null || true
done
# Clear .task-mode for the test run — enforce-* hooks treat
# query|adhoc|chore|system as "skip enforcement", which would mask
# block-vs-allow assertions further down the suite.
rm -f "${COS_AGENT_DIR}/.task-mode"

# Helper to write state with session prefix
write_test_state() {
  echo "$GATE_TEST_SESSION $2" > "$1"
}

# Helper to remove state
clear_test_state() {
  rm -f "$1"
}

# ---- thinking_os-gate.sh ----
echo "--- thinking_os-gate.sh ---"
H="${HOOKS_DIR}/thinking_os-gate.sh"

# No gate file → should block .py file
clear_test_state "${COS_AGENT_DIR}/.thinking_os-gate"
run_test "Block .py without gate" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 2

# Valid gate → should allow
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "CLEAR 1"
run_test "Allow .py with CLEAR gate" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

# Non-code file → should always allow (no gate needed)
clear_test_state "${COS_AGENT_DIR}/.thinking_os-gate"
run_test "Allow .md without gate" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"docs/roadmap.md","old_string":"x","new_string":"y"}}' 0

# Test file → should skip enforcement
run_test "Allow test file without gate" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/tests/test_services.py","old_string":"x","new_string":"y"}}' 0

# Invalid classification → should block
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "INVALID 1"
run_test "Block invalid classification" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 2

# Wrong session → should block
echo "ses-wrong-session CLEAR 1" > "${COS_AGENT_DIR}/.thinking_os-gate"
run_test "Block wrong session gate" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 2

echo ""

# ---- enforce-task-start.sh ----
echo "--- enforce-task-start.sh ---"
H="${HOOKS_DIR}/enforce-task-start.sh"

# CLEAR 1 → should allow without task
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "CLEAR 1"
clear_test_state "${COS_AGENT_DIR}/.task-current"
run_test "Allow CLEAR 1 without task" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

# COMPLICATED without task → should block
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "COMPLICATED 3"
clear_test_state "${COS_AGENT_DIR}/.task-current"
run_test "Block COMPLICATED without task" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 2

# COMPLICATED with task → should allow
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "COMPLICATED 3"
write_test_state "${COS_AGENT_DIR}/.task-current" "TASK-999"
run_test "Allow COMPLICATED with task" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

# State dir files → always skip
clear_test_state "${COS_AGENT_DIR}/.task-current"
run_test "Allow state dir files without task" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"'"${COS_STATE_DIR}"'/hooks/test.sh","old_string":"x","new_string":"y"}}' 0

echo ""

# ---- enforce-skill.sh ----
echo "--- enforce-skill.sh ---"
H="${HOOKS_DIR}/enforce-skill.sh"

# CLEAR 1 → should allow without skill (new fast-path)
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "CLEAR 1"
clear_test_state "${COS_AGENT_DIR}/.active-skill"
run_test "Allow CLEAR 1 without skill (fast-path)" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

# No gate, no skill → should block
clear_test_state "${COS_AGENT_DIR}/.thinking_os-gate"
clear_test_state "${COS_AGENT_DIR}/.active-skill"
run_test "Block .py without skill or gate" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 2

# COMPLICATED without skill → should block
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "COMPLICATED 3"
clear_test_state "${COS_AGENT_DIR}/.active-skill"
run_test "Block COMPLICATED .py without skill" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 2

# COMPLICATED with matching skill → should allow
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "COMPLICATED 3"
write_test_state "${COS_AGENT_DIR}/.active-skill" "python-django"
run_test "Allow .py with python-django skill" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

# Frontend file with wrong skill → should block
write_test_state "${COS_AGENT_DIR}/.active-skill" "python-django"
run_test "Block .tsx with python-django skill" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"frontend/src/app/page.tsx","old_string":"x","new_string":"y"}}' 2

# Frontend file with correct skill → should allow
write_test_state "${COS_AGENT_DIR}/.active-skill" "nextjs-react"
run_test "Allow .tsx with nextjs-react skill" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"frontend/src/app/page.tsx","old_string":"x","new_string":"y"}}' 0

echo ""

# ---- enforce-zoom.sh ----
echo "--- enforce-zoom.sh ---"
H="${HOOKS_DIR}/enforce-zoom.sh"

# CLEAR → should skip zoom check entirely
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "CLEAR 1"
clear_test_state "${COS_AGENT_DIR}/.zoom-checkpoint"
run_test "Allow CLEAR without zoom" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

# COMPLICATED without zoom → should block
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "COMPLICATED 3"
clear_test_state "${COS_AGENT_DIR}/.zoom-checkpoint"
run_test "Block COMPLICATED without zoom" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 2

# COMPLICATED with zoom → should allow
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "COMPLICATED 3"
write_test_state "${COS_AGENT_DIR}/.zoom-checkpoint" "PROBLEM_FRAMED"
run_test "Allow COMPLICATED with zoom" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

# CHAOTIC → should skip zoom check
write_test_state "${COS_AGENT_DIR}/.thinking_os-gate" "CHAOTIC 2"
clear_test_state "${COS_AGENT_DIR}/.zoom-checkpoint"
run_test "Allow CHAOTIC without zoom" "$H" \
  '{"tool_name":"Edit","tool_input":{"file_path":"backend/apps/catalog/services.py","old_string":"x","new_string":"y"}}' 0

echo ""

# ---- auto-trace-rotate.sh — size-based log rotation ----
# Verifies the copytruncate path added on top of the original trace-only
# rotation. Sandboxes the work under .coding-os/test-rot/ so real logs are
# untouched.  Each assertion increments PASS/FAIL/TOTAL directly because
# the rotation hook always exits 0 — run_test() only inspects exit code.
echo "--- auto-trace-rotate.sh (log rotation) ---"
H="${HOOKS_DIR}/auto-trace-rotate.sh"
ROT_SANDBOX="${COS_AGENT_DIR%/*}/test-rot/.coding-os"
mkdir -p "$ROT_SANDBOX" "$ROT_SANDBOX/claude"

run_check() {
  local name="$1" ok="$2"
  TOTAL=$((TOTAL + 1))
  if [[ "$ok" == "1" ]]; then
    echo "  PASS  $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $name"
    FAIL=$((FAIL + 1))
  fi
}

# Case 1: file >= threshold → archive created + origin truncated.
printf 'AAAAAAAAAA' > "$ROT_SANDBOX/.mcp.log"
COS_STATE_DIR="$ROT_SANDBOX" COS_AGENT_DIR="$ROT_SANDBOX/claude" \
  COS_LOG_ROTATE_SIZE_BYTES=5 COS_LOG_ROTATE_KEEP=3 \
  bash "$H" </dev/null >/dev/null 2>&1
archive_present=0
[[ -n "$(ls "$ROT_SANDBOX"/.mcp.log.*.gz 2>/dev/null)" ]] && archive_present=1
origin_size=$(stat -f%z "$ROT_SANDBOX/.mcp.log" 2>/dev/null || stat -c%s "$ROT_SANDBOX/.mcp.log" 2>/dev/null || echo 99)
[[ "$archive_present" == "1" && "$origin_size" == "0" ]] && pass=1 || pass=0
run_check "Rotate when file ≥ threshold (archive + truncate)" "$pass"

# Case 2: file < threshold → no archive added, origin untouched.
rm -f "$ROT_SANDBOX"/.cos.log.*.gz
printf 'tiny' > "$ROT_SANDBOX/.cos.log"
size_before=$(stat -f%z "$ROT_SANDBOX/.cos.log" 2>/dev/null || stat -c%s "$ROT_SANDBOX/.cos.log" 2>/dev/null || echo 0)
COS_STATE_DIR="$ROT_SANDBOX" COS_AGENT_DIR="$ROT_SANDBOX/claude" \
  COS_LOG_ROTATE_SIZE_BYTES=1073741824 COS_LOG_ROTATE_KEEP=3 \
  bash "$H" </dev/null >/dev/null 2>&1
size_after=$(stat -f%z "$ROT_SANDBOX/.cos.log" 2>/dev/null || stat -c%s "$ROT_SANDBOX/.cos.log" 2>/dev/null || echo 0)
new_archives=$(ls "$ROT_SANDBOX"/.cos.log.*.gz 2>/dev/null | wc -l | tr -d ' ')
[[ "$size_before" == "$size_after" && "$new_archives" == "0" ]] && pass=1 || pass=0
run_check "Skip rotation when file < threshold" "$pass"

# Case 3: keep-N trims older archives — seed 5 rotations, expect 3 archives.
rm -f "$ROT_SANDBOX"/.hooks.log.*.gz
for i in 1 2 3 4 5; do
  printf 'round-%s' "$i" > "$ROT_SANDBOX/.hooks.log"
  COS_STATE_DIR="$ROT_SANDBOX" COS_AGENT_DIR="$ROT_SANDBOX/claude" \
    COS_LOG_ROTATE_SIZE_BYTES=1 COS_LOG_ROTATE_KEEP=3 \
    bash "$H" </dev/null >/dev/null 2>&1
  sleep 1
done
kept=$(ls "$ROT_SANDBOX"/.hooks.log.*.gz 2>/dev/null | wc -l | tr -d ' ')
[[ "$kept" == "3" ]] && pass=1 || pass=0
run_check "Keep COS_LOG_ROTATE_KEEP newest archives, trim older" "$pass"

# Sandbox cleanup.
rm -rf "${COS_AGENT_DIR%/*}/test-rot"

echo ""

# ── Cleanup gate test state ─────────────────────────────────────
# Restore original state files
for f in "${COS_AGENT_DIR}/.thinking_os-gate" "${COS_AGENT_DIR}/.task-current" "${COS_AGENT_DIR}/.active-skill" "${COS_AGENT_DIR}/.zoom-checkpoint" "${COS_AGENT_DIR}/.task-mode"; do
  rm -f "$f"
  [[ -f "${f}.bak" ]] && mv "${f}.bak" "$f" || true
done

# Restore original session ID
if [[ -n "$ORIG_SESSION" ]]; then
  echo "$ORIG_SESSION" > "${COS_SESSION_FILE}"
fi

# ---- SUMMARY ----
echo "========================================"
echo "  RESULTS: $PASS/$TOTAL passed, $FAIL failed"
echo "========================================"

if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
