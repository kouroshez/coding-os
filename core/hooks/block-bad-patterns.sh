#!/usr/bin/env bash
# PreToolUse hook: Block known anti-patterns in code being written.
# Source: docs/engineering/backend-rules.md, docs/engineering/frontend-rules.md
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.new_string // .tool_input.content // empty')

# Skip non-code files and migration files
if [[ "$FILE_PATH" != *.py ]] && [[ "$FILE_PATH" != *.ts ]] && [[ "$FILE_PATH" != *.tsx ]] && [[ "$FILE_PATH" != *.js ]]; then
  exit 0
fi
if [[ "$FILE_PATH" == *__pycache__* ]] || [[ "$FILE_PATH" == *node_modules* ]]; then
  exit 0
fi

# Migration-specific rules (before skipping migrations for general rules)
if [[ "$FILE_PATH" == *migrations* ]] && [[ "$FILE_PATH" == *.py ]]; then
  # Block RunPython without reverse_code
  # Source: backend-rules.md § Migration Rules
  if echo "$CONTENT" | grep -qE 'RunPython\(' && ! echo "$CONTENT" | grep -qE 'reverse_code'; then
    echo "BLOCKED: RunPython migration must include reverse_code for rollback safety. See docs/engineering/backend-rules.md § Migration Rules." >&2
    exit 2
  fi
  # Migrations pass all other checks
  exit 0
fi

# === UNIVERSAL RULES ===

# Block bare TODOs without task reference (must be TODO: TASK-### or TODO(TASK-###))
# Source: backend-rules.md § Comments, frontend-rules.md § Comments
# Skip: test files may have legitimate TODOs
if [[ "$FILE_PATH" != *test* ]] && [[ "$FILE_PATH" != *spec* ]]; then
  # Check if TODO exists but TASK-### does NOT exist in the same content
  if echo "$CONTENT" | grep -qiE '(//|#)\s*TODO' && ! echo "$CONTENT" | grep -qE 'TASK-[0-9]{3}'; then
    echo "BLOCKED: Bare TODO without task reference. Use 'TODO: TASK-### description' format. See docs/engineering/backend-rules.md § Comments." >&2
    exit 2
  fi
fi

# === BACKEND RULES ===
if [[ "$FILE_PATH" == *.py ]]; then

  # Skip test files for backend-specific rules (tests may legitimately use print, pass, etc.)
  if [[ "$FILE_PATH" == *test* ]]; then
    exit 0
  fi

  # Block except-pass where pass is the ONLY handler (no logging, no re-raise)
  # Source: backend-rules.md § Error Handling Policy
  if echo "$CONTENT" | grep -qE 'except' && echo "$CONTENT" | grep -qE '^\s*pass\s*$'; then
    # Only block if there's no logging in the same content (indicating bare except:pass)
    if ! echo "$CONTENT" | grep -qE 'logger\.|logging\.|raise '; then
      echo "BLOCKED: Bare 'except: pass' swallows errors silently. Log the error or re-raise. See docs/engineering/backend-rules.md § Error Handling Policy." >&2
      exit 2
    fi
  fi

  # Block print() in production backend code (use logger instead)
  # Source: backend-rules.md § Observability
  if [[ "$FILE_PATH" == *backend/apps/* ]]; then
    if echo "$CONTENT" | grep -qE '^\s*print\('; then
      echo "BLOCKED: Use 'import logging; logger = logging.getLogger(__name__); logger.info(...)' instead of print() in backend code. See docs/engineering/backend-rules.md." >&2
      exit 2
    fi
  fi

  # Block .save()/.delete() in views (views should be thin, use services)
  # Source: backend-rules.md § Core Rules
  if [[ "$FILE_PATH" == *views* ]] || [[ "$FILE_PATH" == *viewsets* ]]; then
    if echo "$CONTENT" | grep -qE '\.(save|delete)\(\)'; then
      echo "BLOCKED: Views must be thin — do not call .save() or .delete() in views. Move business logic to a service function. See docs/engineering/backend-rules.md § Core Rules." >&2
      exit 2
    fi
  fi

  # Block ORM queries in views (use selectors instead)
  # Source: backend-rules.md § Core Rules
  if [[ "$FILE_PATH" == *views* ]] || [[ "$FILE_PATH" == *viewsets* ]]; then
    if echo "$CONTENT" | grep -qE '\.objects\.(filter|get|exclude|annotate|aggregate|create|update|bulk)'; then
      echo "BLOCKED: Do not query ORM directly in views. Use a selector function from selectors.py. See docs/engineering/backend-rules.md § Core Rules." >&2
      exit 2
    fi
  fi

  # Block bare raise ValueError/Exception in service layer (use typed domain exceptions)
  # Source: backend-rules.md § Error Handling Policy
  if [[ "$FILE_PATH" == *services* ]]; then
    if echo "$CONTENT" | grep -qE 'raise\s+(ValueError|Exception|RuntimeError)\('; then
      echo "BLOCKED: Do not raise bare ValueError/Exception in services. Define a typed exception in apps/<domain>/exceptions.py inheriting APIException. See docs/engineering/backend-rules.md § Error Handling Policy." >&2
      exit 2
    fi
  fi

fi

# === FRONTEND RULES ===
if [[ "$FILE_PATH" == *.ts ]] || [[ "$FILE_PATH" == *.tsx ]] || [[ "$FILE_PATH" == *.js ]]; then

  # Skip test/spec files
  if [[ "$FILE_PATH" == *test* ]] || [[ "$FILE_PATH" == *spec* ]] || [[ "$FILE_PATH" == *__tests__* ]]; then
    exit 0
  fi

  # Block console.log in production frontend code (allow console.error/warn)
  # Source: frontend-rules.md § Code Style
  if [[ "$FILE_PATH" == *frontend/src/* ]]; then
    if echo "$CONTENT" | grep -qE 'console\.log\('; then
      echo "BLOCKED: Remove console.log() from production code. Use console.error() for real errors only. See docs/engineering/frontend-rules.md." >&2
      exit 2
    fi
  fi

  # Block 'any' type in TypeScript (use proper types)
  # Source: frontend-rules.md § Non-Negotiables
  if [[ "$FILE_PATH" == *.ts ]] || [[ "$FILE_PATH" == *.tsx ]]; then
    if echo "$CONTENT" | grep -qE ':\s*any\b|<any>|as\s+any\b'; then
      echo "BLOCKED: Do not use 'any' type. Define a proper TypeScript type or interface. See docs/engineering/frontend-rules.md § Non-Negotiables." >&2
      exit 2
    fi
  fi

  # Block non-NEXT_PUBLIC_ env vars in frontend client code (backend secret leak)
  # Source: frontend-rules.md § Mandatory Engineering Rules
  if [[ "$FILE_PATH" == *frontend/* ]]; then
    if echo "$CONTENT" | grep -qE 'process\.env\.(STRIPE_SECRET|DATABASE_URL|DJANGO_SECRET|POSTMARK_SERVER_TOKEN|SECRET_KEY)'; then
      echo "BLOCKED: Backend secret detected in frontend code. Only NEXT_PUBLIC_* variables are safe for the browser. See docs/engineering/frontend-rules.md § Mandatory Engineering Rules." >&2
      exit 2
    fi
  fi
fi

exit 0
