#!/usr/bin/env bash
# bootstrap.sh — idempotent auto-fix for the architecture_drawing skill.
#
# Fixes both well-known failure modes in the agent sandbox:
#   1. mmdc (Mermaid CLI) not on PATH → npm install it (persists via NPM PVC).
#   2. /etc/fonts/ + /usr/share/fonts/ wiped after pod restart → the persist-apt
#      wrapper in agent_sandbox/entrypoint.sh only saves /usr/bin + /usr/lib,
#      so apt-installed font configs/files vanish across boots even though
#      dpkg thinks the packages are present. We work around that by:
#        a) re-running `apt-get install fontconfig fonts-dejavu-core` (fast
#           no-op when already there, full reinstall when wiped),
#        b) snapshotting /etc/fonts and /usr/share/fonts into the PVC under
#           $PERSIST_DIR/apt/dirs/, so a follow-up restore on next boot can
#           rehydrate them even if apt restore itself fails.
#
# Safe to run on every shell start — a healthy system finishes in <100ms.
#
# Exit codes:
#   0  everything OK (or fixed)
#   1  unrecoverable (no apt, no npm, no network, etc.) — message printed.

set -euo pipefail

PERSIST_DIR="${PERSIST_DIR:-/agent/data/.persist}"
FONT_PVC_DIR="${PERSIST_DIR}/apt/dirs"
LOG_PREFIX="[arch-drawing-bootstrap]"

log() { echo "${LOG_PREFIX} $*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
if [[ $EUID -ne 0 ]] && have sudo; then SUDO="sudo"; fi

# ----------------------------------------------------------------------------
# 1. mmdc
# ----------------------------------------------------------------------------
ensure_mmdc() {
  if have mmdc; then return 0; fi
  log "installing @mermaid-js/mermaid-cli…"
  if ! have npm; then
    log "ERROR: npm not found — cannot install mmdc"; return 1
  fi
  npm install -g @mermaid-js/mermaid-cli >&2
  have mmdc || { log "ERROR: npm install succeeded but mmdc still not on PATH"; return 1; }
}

# ----------------------------------------------------------------------------
# 2. fontconfig + fonts
# ----------------------------------------------------------------------------
fonts_healthy() {
  [[ -f /etc/fonts/fonts.conf ]] && [[ "$(fc-list 2>/dev/null | wc -l)" -ge 1 ]]
}

restore_fonts_from_pvc() {
  # Best-effort: rehydrate /etc/fonts and /usr/share/fonts from snapshots
  # taken on a previous boot. Returns 0 if rehydration succeeded.
  [[ -d "${FONT_PVC_DIR}/etc_fonts" ]] || return 1
  [[ -d "${FONT_PVC_DIR}/share_fonts" ]] || return 1
  log "rehydrating /etc/fonts + /usr/share/fonts from PVC snapshot…"
  $SUDO mkdir -p /etc/fonts /usr/share/fonts
  $SUDO rsync -a "${FONT_PVC_DIR}/etc_fonts/"   /etc/fonts/   2>/dev/null || true
  $SUDO rsync -a "${FONT_PVC_DIR}/share_fonts/" /usr/share/fonts/ 2>/dev/null || true
  $SUDO fc-cache -f >&2 2>/dev/null || true
  fonts_healthy
}

apt_install_fonts() {
  if ! have apt-get; then
    log "ERROR: apt-get not available — cannot install fontconfig"; return 1
  fi
  log "installing fontconfig + fonts-dejavu-core via apt…"
  $SUDO apt-get update -qq >&2 || true
  # --reinstall makes this resilient to the dpkg-says-yes-but-files-gone case.
  $SUDO apt-get install -y -qq --no-install-recommends --reinstall \
      fontconfig fonts-dejavu-core >&2
  $SUDO fc-cache -f >&2 2>/dev/null || true
  fonts_healthy
}

snapshot_fonts_to_pvc() {
  # Copy current font dirs to PVC so the next cold boot can restore them
  # without needing apt repos. Cheap (~3 MB) and idempotent.
  fonts_healthy || return 0
  mkdir -p "${FONT_PVC_DIR}"
  if have rsync; then
    rsync -a --delete /etc/fonts/        "${FONT_PVC_DIR}/etc_fonts/"   2>/dev/null || true
    rsync -a --delete /usr/share/fonts/  "${FONT_PVC_DIR}/share_fonts/" 2>/dev/null || true
  else
    rm -rf "${FONT_PVC_DIR}/etc_fonts" "${FONT_PVC_DIR}/share_fonts"
    cp -a /etc/fonts "${FONT_PVC_DIR}/etc_fonts" 2>/dev/null || true
    cp -a /usr/share/fonts "${FONT_PVC_DIR}/share_fonts" 2>/dev/null || true
  fi
}

ensure_fonts() {
  if fonts_healthy; then return 0; fi
  # Try the cheap path first (PVC rehydrate) before hitting apt repos.
  if restore_fonts_from_pvc; then return 0; fi
  apt_install_fonts || return 1
}

# ----------------------------------------------------------------------------
# 3. Puppeteer config (sandbox-safe Chromium flags)
# ----------------------------------------------------------------------------
ensure_puppeteer_cfg() {
  local skill_dir cfg
  skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cfg="${skill_dir}/puppeteer.json"
  if [[ ! -f "$cfg" ]]; then
    cat > "$cfg" <<'JSON'
{ "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"] }
JSON
    log "wrote $cfg"
  fi
}

# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
main() {
  local rc=0
  ensure_mmdc           || rc=1
  ensure_fonts          || rc=1
  ensure_puppeteer_cfg  || rc=1
  # Snapshot at the end (not at the start) so a successful auto-fix immediately
  # writes a good copy back to the PVC for the next boot.
  snapshot_fonts_to_pvc || true
  if [[ $rc -eq 0 ]]; then
    log "OK: mmdc=$(mmdc --version 2>/dev/null) fonts=$(fc-list 2>/dev/null | wc -l)"
  else
    log "FAILED — see messages above"
  fi
  return $rc
}

main "$@"
