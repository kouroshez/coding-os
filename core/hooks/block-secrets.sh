#!/usr/bin/env bash
# PreToolUse hook: Block commits/writes containing hardcoded secrets or sensitive files.
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

# For Bash tool: block git add of sensitive files
if [[ "$TOOL" == "Bash" ]]; then
  cos_log_hook block-secrets fire "tool=Bash"
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

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

  # Block git commit --no-verify (skip hooks) — only match actual git commit commands
  if echo "$COMMAND" | grep -qE '^git commit\b.*--no-verify'; then
    cos_log_hook block-secrets block "tool=Bash rule=no-verify"
    echo "BLOCKED: --no-verify skips safety hooks. Fix the underlying issue instead." >&2
    exit 2
  fi
fi

# For Write/Edit tool: block writing secrets patterns
if [[ "$TOOL" == "Write" || "$TOOL" == "Edit" ]]; then
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty')

  # Skip .env.example, test files, mock files, and docs
  if [[ "$FILE_PATH" == *.env.example* ]] || [[ "$FILE_PATH" == *test* ]] || [[ "$FILE_PATH" == *mock* ]] || [[ "$FILE_PATH" == *.md ]]; then
    exit 0
  fi

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

  # Block Django SECRET_KEY hardcoded
  if echo "$CONTENT" | grep -qE "SECRET_KEY\s*=\s*['\"]django-insecure-"; then
    # Allow in development settings only
    if [[ "$FILE_PATH" != *development* ]] && [[ "$FILE_PATH" != *local* ]]; then
      echo "BLOCKED: Insecure Django SECRET_KEY detected outside development settings. Use environment variables." >&2
      exit 2
    fi
  fi

  # Block Postmark server token hardcoded
  if echo "$CONTENT" | grep -qE 'POSTMARK_SERVER_TOKEN\s*=\s*["\047][a-f0-9-]{36}["\047]'; then
    echo "BLOCKED: Postmark server token detected. Use environment variables." >&2
    exit 2
  fi
fi

exit 0
