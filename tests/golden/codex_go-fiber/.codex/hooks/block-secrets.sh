#!/usr/bin/env bash
# PreToolUse hook: Block commits/writes containing hardcoded secrets or sensitive files.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Fail-closed: a secret-scanning gate that cannot read its input must DENY,
# not silently allow (observability-eye I8). cos_json_field falls back to
# python3 when only jq is missing, so the gate keeps working.
cos_require_parser block-secrets

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)

# For Bash tool: block git add of sensitive files
if [[ "$TOOL" == "Bash" ]]; then
  cos_log_hook block-secrets fire "tool=Bash"
  COMMAND=$(printf '%s' "$INPUT" | cos_json_field tool_input.command)

  # Block git add of .env files (but allow .env.example, .env.template)
  if echo "$COMMAND" | grep -qE 'git add.*\.env($|\s)' || echo "$COMMAND" | grep -qE 'git add\s+\.env$'; then
    cos_log_hook block-secrets block "tool=Bash rule=env-file"
    echo "BLOCKED: .env files must not be committed to git. Use .env.example for structure." >&2
    exit 2
  fi

  # Block git add of credential/key files
  if echo "$COMMAND" | grep -qE 'git add.*(credentials\.json|service-account\.json|\.pem\b|id_rsa|\.key\b)'; then
    cos_log_hook block-secrets block "tool=Bash rule=credential-file"
    echo "BLOCKED: Credential/key files must not be committed. Store secrets in environment variables." >&2
    exit 2
  fi

  # Block git commit --no-verify (skip hooks) — only match actual git commit commands.
  # Strip quoted -m message values first so a "--no-verify" mentioned inside a commit
  # message is not a false match (it blocked legitimate docs commits otherwise).
  COMMAND_NOQUOTES=$(printf '%s' "$COMMAND" | sed -E "s/\"[^\"]*\"//g; s/'[^']*'//g")
  if echo "$COMMAND_NOQUOTES" | grep -qE '^git commit\b.*--no-verify'; then
    cos_log_hook block-secrets block "tool=Bash rule=no-verify"
    echo "BLOCKED: --no-verify skips safety hooks. Fix the underlying issue instead." >&2
    exit 2
  fi
fi

# For Write/Edit tool: block writing secrets patterns
if [[ "$TOOL" == "Write" || "$TOOL" == "Edit" ]]; then
  FILE_PATH=$(printf '%s' "$INPUT" | cos_json_field tool_input.file_path)
  CONTENT=$(printf '%s' "$INPUT" | cos_json_field tool_input.new_string tool_input.content)
  FILE_BASENAME="$(basename "$FILE_PATH" 2>/dev/null || echo "")"

  # Skip docs + genuine test/mock files. Match path SEGMENTS / basenames, not
  # bare substrings — `*test*` used to skip ANY path containing "test"
  # (latest/, contest/), silently disabling secret scanning there.
  case "$FILE_PATH" in
    *.env.example*|*.md|*.markdown) exit 0 ;;
    */tests/*|*/test/*|*/__tests__/*|*/__mocks__/*|*/mocks/*|*/fixtures/*) exit 0 ;;
  esac
  case "$FILE_BASENAME" in
    test_*|*_test.*|*.test.*|*.spec.*|mock_*|*_mock.*|conftest.py) exit 0 ;;
  esac

  # Block live Stripe keys (sk_live_, pk_live_ with real-length values)
  if echo "$CONTENT" | grep -qE 'sk_live_[a-zA-Z0-9]{20,}'; then
    echo "BLOCKED: Live Stripe secret key detected. Use environment variables (os.environ['STRIPE_SECRET_KEY']) instead." >&2
    exit 2
  fi

  # Block test Stripe keys hardcoded in non-test files
  if [[ "$FILE_PATH" != *test* ]] && [[ "$FILE_PATH" != *fixture* ]] && [[ "$FILE_PATH" != *.env* ]]; then
    if echo "$CONTENT" | grep -qE 'sk_test_[a-zA-Z0-9]{20,}'; then
      echo "BLOCKED: Stripe test key should be in .env, not hardcoded. Use environment variables." >&2
      exit 2
    fi
  fi

  # Block private keys
  if echo "$CONTENT" | grep -qE 'BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY'; then
    echo "BLOCKED: Private key detected in file content. Store keys in environment variables or secret manager." >&2
    exit 2
  fi

  # Block AWS credentials
  if echo "$CONTENT" | grep -qE 'AKIA[0-9A-Z]{16}'; then
    echo "BLOCKED: AWS access key ID detected. Use environment variables or IAM roles." >&2
    exit 2
  fi

  # Block generic high-entropy secrets (API keys, tokens) in Python/TS config files
  if [[ "$FILE_PATH" == *settings* ]] || [[ "$FILE_PATH" == *config* ]] || [[ "$FILE_PATH" == *.env* ]]; then
    if echo "$CONTENT" | grep -qE "(SECRET_KEY|API_KEY|AUTH_TOKEN|PRIVATE_KEY)\s*=\s*['\"][a-zA-Z0-9+/=]{32,}['\"]"; then
      echo "BLOCKED: Hardcoded secret detected in config. Use os.environ.get() or environment variables." >&2
      exit 2
    fi
  fi

  # Block Django SECRET_KEY hardcoded.
  # Tighten allowlist: match the file BASENAME, not the whole path, so a path
  # containing "development" elsewhere (e.g. /var/development-team/app/settings.py)
  # doesn't open a hole.
  if echo "$CONTENT" | grep -qE "SECRET_KEY\s*=\s*['\"]django-insecure-"; then
    if [[ "$FILE_BASENAME" != *development* ]] && [[ "$FILE_BASENAME" != *local* ]]; then
      echo "BLOCKED: Insecure Django SECRET_KEY detected outside development settings. Use environment variables." >&2
      exit 2
    fi
  fi

  # Block Postmark server token hardcoded
  if echo "$CONTENT" | grep -qE 'POSTMARK_SERVER_TOKEN\s*=\s*["\047][a-f0-9-]{36}["\047]'; then
    echo "BLOCKED: Postmark server token detected. Use environment variables." >&2
    exit 2
  fi

  # Block GitHub Personal Access Tokens (classic + fine-grained) and OAuth tokens.
  # Format: ghp_/gho_/ghu_/ghs_/ghr_ + 36+ alnum.
  if echo "$CONTENT" | grep -qE 'gh[pousr]_[A-Za-z0-9]{36,}'; then
    echo "BLOCKED: GitHub token detected (ghp_/gho_/ghu_/ghs_/ghr_). Use \$GITHUB_TOKEN env var or gh auth login." >&2
    exit 2
  fi

  # Block OpenAI / Anthropic API keys. The discriminator is the SPECIFIC prefix
  # (sk-ant-api##- / sk-proj- / classic sk-+40 contiguous alnum) — kebab-case
  # slugs like `sk-product-identifier-x` lack it and no longer false-fire. The
  # ant/proj bodies still allow base64url `-`/`_` so real keys are caught.
  if echo "$CONTENT" | grep -qE 'sk-ant-(api|admin)[0-9]{2}-[A-Za-z0-9_-]{80,}|sk-proj-[A-Za-z0-9_-]{40,}|sk-[A-Za-z0-9]{40,}'; then
    echo "BLOCKED: OpenAI/Anthropic API key detected. Use environment variables (OPENAI_API_KEY, ANTHROPIC_API_KEY)." >&2
    exit 2
  fi

  # Block Slack tokens (xoxb-/xoxa-/xoxp-/xoxr-/xoxs-).
  if echo "$CONTENT" | grep -qE 'xox[abprs]-[A-Za-z0-9-]{10,}'; then
    echo "BLOCKED: Slack token detected. Use environment variables." >&2
    exit 2
  fi

  # Block Google API keys (AIza...).
  if echo "$CONTENT" | grep -qE 'AIza[A-Za-z0-9_\-]{35}'; then
    echo "BLOCKED: Google API key detected. Use environment variables." >&2
    exit 2
  fi

  # Block JWT tokens hardcoded in source (header.payload.signature, base64url).
  # Skip docs/examples — already filtered above. Require 3 segments with ≥10 chars each.
  if echo "$CONTENT" | grep -qE 'eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}'; then
    echo "BLOCKED: JWT token detected hardcoded in source. Issue tokens at runtime; do not commit." >&2
    exit 2
  fi

  # Block basic-auth credentials embedded in URLs (http(s)://user:password@host).
  # Only block when the password segment has real entropy (≥6 chars, not just "user:pass" placeholder).
  if echo "$CONTENT" | grep -qE 'https?://[A-Za-z0-9._-]+:[^@[:space:]/"\047]{6,}@[A-Za-z0-9.-]+'; then
    if ! echo "$CONTENT" | grep -qE 'https?://(user|username|admin|root|test|example|foo):(password|pass|secret|test|example|foo|changeme)@'; then
      echo "BLOCKED: Basic-auth credentials embedded in URL. Use env vars or a secret manager, never inline in URLs." >&2
      exit 2
    fi
  fi
fi

exit 0
