#!/usr/bin/env bash
# install.sh — GUI-first install path for coding-os (ADR-0007).
#
# Boots the Hub on http://127.0.0.1:9188 from a machine with no prior
# `cos` CLI. Preflights prerequisites (mirrors `cos doctor --bootstrap`
# semantics: bash/git/uv/python), installs the package as a uv tool,
# then starts the Hub bound to localhost.
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/<org>/coding-os/main/install.sh | bash
# From a checkout:
#   bash install.sh
#
# Flags / env:
#   COS_HUB_PORT   Hub port (default 9188).
#   COS_HUB_TOKEN  When set, exported into the Hub so every mutating
#                  /api/* request requires `Authorization: Bearer <token>`
#                  (TASK-363). Unset = open-localhost (the default trust
#                  posture for a single-user machine).
#   COS_REPO_URL   Git URL to clone when run outside a checkout.
set -euo pipefail

REPO_URL="${COS_REPO_URL:-https://github.com/kouroshez/coding-os.git}"
HUB_PORT="${COS_HUB_PORT:-9188}"
HUB_HOST="127.0.0.1"

# Bump together, and only after re-computing the digest against the new URL:
#   curl -fsSL https://astral.sh/uv/<version>/install.sh | shasum -a 256
UV_INSTALLER_VERSION="0.9.10"
UV_INSTALLER_SHA256="578d164a618b6b2825017d6dab73b00925e3895b47f22b25434b3fee2ec9f849"

log() { printf '  %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# macOS ships shasum, most Linux images ship sha256sum; support both.
_sha256() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}'
  else return 1
  fi
}

# --- Preflight: mirror cos doctor --bootstrap (no project required) ---
preflight() {
  log "Preflight (bash/git/uv/python)..."

  local bash_major="${BASH_VERSINFO[0]:-0}"
  [ "$bash_major" -ge 4 ] || die "bash >= 4 required (found ${BASH_VERSION:-unknown})."

  command -v git >/dev/null 2>&1 || die "git not found on PATH — install git first."

  if ! command -v uv >/dev/null 2>&1; then
    log "uv not found — installing uv ${UV_INSTALLER_VERSION} ..."
    # Download-verify-run, never `curl | sh`: piping means the bytes that get
    # executed are never the bytes anyone checked. The URL is version-pinned
    # (immutable) and the digest is verified before a single line runs, so a
    # compromised CDN response fails closed instead of executing as root-ish.
    _uv_installer="$(mktemp)"
    trap 'rm -f "$_uv_installer"' RETURN
    curl -fsSL "https://astral.sh/uv/${UV_INSTALLER_VERSION}/install.sh" -o "$_uv_installer" \
      || die "could not download the uv installer — check network access to astral.sh"
    _uv_actual="$(_sha256 "$_uv_installer")" \
      || die "no sha256 tool found (need shasum or sha256sum) — install uv manually: https://astral.sh/uv"
    [ "$_uv_actual" = "$UV_INSTALLER_SHA256" ] \
      || die "uv installer digest mismatch — expected $UV_INSTALLER_SHA256, got $_uv_actual. Refusing to run it."
    sh "$_uv_installer"
    # uv installs to ~/.local/bin or ~/.cargo/bin; surface it for this run.
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv install failed — install manually: https://astral.sh/uv"
  fi

  # uv provides a managed Python, so we do not hard-require a system one;
  # warn only, matching the bootstrap doctor's non-fatal python check.
  command -v python3 >/dev/null 2>&1 || log "WARN: system python3 not found — uv will provide one."
}

# --- Locate or fetch the repo, then install the cos CLI ---------------
ensure_repo() {
  if [ -f "pyproject.toml" ] && grep -q '^name = "coding-os"' pyproject.toml 2>/dev/null; then
    REPO_DIR="$(pwd)"
    log "Using checkout at ${REPO_DIR}"
    return
  fi
  REPO_DIR="${HOME}/.coding-os-src"
  if [ -d "${REPO_DIR}/.git" ]; then
    log "Updating existing checkout at ${REPO_DIR}"
    git -C "${REPO_DIR}" pull --ff-only
  else
    log "Cloning ${REPO_URL} -> ${REPO_DIR}"
    git clone --depth 1 "${REPO_URL}" "${REPO_DIR}"
  fi
}

install_cli() {
  log "Installing the cos CLI (uv tool install)..."
  uv tool install --editable "${REPO_DIR}"
  export PATH="$HOME/.local/bin:$PATH"
  command -v cos >/dev/null 2>&1 || die "cos not on PATH after install — run: uv tool update-shell"
}

# --- Boot the Hub, bound to localhost ---------------------------------
boot_hub() {
  log "Verifying prerequisites via cos doctor --bootstrap..."
  cos doctor --bootstrap || die "Preflight checks failed — see output above."

  log "Starting the Hub on http://${HUB_HOST}:${HUB_PORT} ..."
  if [ -n "${COS_HUB_TOKEN:-}" ]; then
    log "Auth: COS_HUB_TOKEN set — mutating /api/* will require a bearer token."
    COS_HUB_TOKEN="${COS_HUB_TOKEN}" cos hub start --port "${HUB_PORT}"
  else
    cos hub start --port "${HUB_PORT}"
  fi
}

main() {
  printf 'coding-os — GUI-first install\n'
  preflight
  ensure_repo
  install_cli
  boot_hub
  printf '\nOpen http://%s:%s in your browser to reach the onboarding wizard.\n' "${HUB_HOST}" "${HUB_PORT}"
  # This installer clones and installs --editable, so a pull IS the upgrade;
  # `cos update` only re-links a project against the core already on disk.
  printf 'Upgrade later:  git -C %s pull   (then run cos update in each project)\n' "${REPO_DIR}"
}

main "$@"
