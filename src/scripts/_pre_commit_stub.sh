#!/usr/bin/env bash
# cos pre-commit stub — installed into .git/hooks/pre-commit by `cos init|update`.
# Runs the hook body from this machine's coding-os install (found through the
# tracked .coding-os/hook-shim.sh), so a fix to the body reaches this repo
# without a reinstall. Spec: docs/architecture/adr/0010-consumer-distribution-version-gate.md
set -euo pipefail

shim="$(git rev-parse --show-toplevel)/.coding-os/hook-shim.sh"
root="$(bash "$shim" --print-root 2>/dev/null || true)"
body="${root}/scripts/_pre_commit_body.sh"
if [[ ! -f "$body" ]]; then
  echo "cos pre-commit: BLOCKED — no coding-os install found; install coding-os so \`cos\` is on PATH, then run \`cos update\`." >&2
  exit 1
fi
exec bash "$body" "$@"
