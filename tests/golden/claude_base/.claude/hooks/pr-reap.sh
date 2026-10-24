#!/usr/bin/env bash
# coding-os hook shim — copied to .coding-os/hook-shim.sh by `cos init|update`.
#
# Every <agent>/hooks/<name>.sh in the project is a relative symlink to this
# file, so the committed adapter dirs survive a clone. It runs the same-named
# hook from this machine's coding-os install, which it finds through the `cos`
# entry point and caches in .coding-os/.core-root (machine-local, gitignored).
# No install → exit 0: nothing can enforce without the runtime.
# Spec: docs/architecture/adr/0010-consumer-distribution-version-gate.md § Amendment.
set -euo pipefail

shim="$0"
while [[ -L "$shim" ]]; do
  next="$(readlink "$shim")"
  [[ "$next" == /* ]] || next="$(dirname "$shim")/$next"
  shim="$next"
done
cache="$(dirname "$shim")/.core-root"

_core_from_cos() {
  local entry py next
  entry="$(command -v cos 2>/dev/null)" || return 0
  while [[ -L "$entry" ]]; do
    next="$(readlink "$entry")"
    [[ "$next" == /* ]] || next="$(dirname "$entry")/$next"
    entry="$next"
  done
  py="$(awk 'NR==1{sub(/^#!/,""); sub(/[[:space:]].*$/,""); print; exit}' "$entry" 2>/dev/null)"
  [[ -x "$py" ]] || return 0
  "$py" -I -c 'import os, core; print(os.path.dirname(os.path.dirname(core.__file__)))' 2>/dev/null || true
}

core=""
[[ -f "$cache" ]] && read -r core < "$cache"
if [[ ! -d "${core}/core/hooks" ]]; then
  core="$(_core_from_cos)"
  [[ -d "${core}/core/hooks" ]] && printf '%s\n' "$core" > "$cache" 2>/dev/null
fi

if [[ "${1:-}" == "--print-root" ]]; then
  printf '%s\n' "$core"
  exit 0
fi
[[ -d "${core}/core/hooks" ]] || exit 0

name="$(basename "$0")"
agent="$(basename "$(cd "$(dirname "$0")/.." && pwd)")"
for dir in "${core}/core/hooks" "${core}/adapters/${agent#.}/hooks"; do
  if [[ -f "${dir}/${name}" ]]; then
    exec bash "${dir}/${name}" "$@"
  fi
done
exit 0
