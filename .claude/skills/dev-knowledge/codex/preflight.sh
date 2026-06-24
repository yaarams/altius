#!/usr/bin/env bash
# preflight.sh — codex_runner self-heal.
#
# Workspace pods can be scaled down or restored from backup, in which case
# anything outside `/agent/data/` (and even some bits inside it) may be missing
# when this skill is invoked next. This script makes `codex-run.sh` idempotent
# and self-healing:
#
#   1. Codex CLI installed (npm-global at /agent/data/.persist/npm).
#   2. `jq` available (apt user-cache or fallback to local download).
#   3. Codex auth.json populated from CODEX_OPENAI_API_KEY.
#   4. Sandbox capability probed; result cached at $CACHE_DIR/sandbox_mode.
#
# Designed to be sourced (`source preflight.sh`) so it can export the chosen
# sandbox mode + tool paths back to the caller without spawning a subshell.
# Safe to run on every wrapper invocation — fast path is a single stat.
#
# Exit codes (when run, not sourced):
#   0  ready, env exported
#   2  bad env (missing CODEX_OPENAI_API_KEY, no network for first install, etc.)

set -euo pipefail

# Persistent install location — survives pod restarts as long as /agent/data is mounted.
PERSIST_ROOT="${CODEX_PERSIST_ROOT:-/agent/data/.persist}"
NPM_PREFIX="$PERSIST_ROOT/npm"
NPM_BIN="$NPM_PREFIX/bin"
LOCAL_BIN="$PERSIST_ROOT/bin"
CACHE_DIR="${CODEX_CACHE_DIR:-/agent/data/.home/.codex/.preflight}"
STATE_FILE="$CACHE_DIR/state.json"
SANDBOX_FILE="$CACHE_DIR/sandbox_mode"

# Pinned codex CLI version. Bump deliberately; never trust `@latest` in self-heal.
CODEX_PINNED_VERSION="${CODEX_PINNED_VERSION:-0.128.0}"
CODEX_NPM_PKG="@openai/codex@${CODEX_PINNED_VERSION}"

mkdir -p "$CACHE_DIR" "$LOCAL_BIN"
export PATH="$NPM_BIN:$LOCAL_BIN:$PATH"

# Auto-source the secrets file when CODEX_OPENAI_API_KEY isn't already set.
# Wrapper sources the same file before sourcing us; when preflight is run
# standalone (smoke tests, debugging) we still want it to work.
if [[ -z "${CODEX_OPENAI_API_KEY:-}" ]]; then
  CODEX_ENV_FILE="${CODEX_ENV_FILE:-workspace/dev-knowledge/memory/secrets/codex.env}"
  if [[ -r "$CODEX_ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$CODEX_ENV_FILE"
    set +a
  fi
fi

# ----------------------------- helpers --------------------------------------
log() { printf '[preflight] %s\n' "$*" >&2; }

has() { command -v "$1" >/dev/null 2>&1; }

fresh() {
  # File exists AND is newer than the wrapper itself (i.e. cache valid).
  local f="$1" mtime_max="${2:-86400}"  # default TTL 24h
  [[ -s "$f" ]] || return 1
  local age now mtime
  now="$(date +%s)"
  mtime="$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0)"
  age=$((now - mtime))
  (( age < mtime_max ))
}

ensure_node() {
  has node && return 0
  log "FATAL: node not on PATH and we cannot bootstrap it from here."
  log "This image normally ships node 22; if it is gone the workspace is fundamentally broken."
  return 2
}

ensure_npm_prefix() {
  if ! npm config get prefix 2>/dev/null | grep -qx "$NPM_PREFIX"; then
    npm config set prefix "$NPM_PREFIX" --location=user >/dev/null
  fi
}

ensure_codex() {
  if has codex && codex --version 2>/dev/null | grep -q "$CODEX_PINNED_VERSION"; then
    return 0
  fi
  log "installing $CODEX_NPM_PKG into $NPM_PREFIX"
  ensure_npm_prefix
  # --no-fund / --no-audit keep output quiet; --silent prevents noisy progress.
  npm install --global --no-fund --no-audit --silent "$CODEX_NPM_PKG" >&2
  has codex || { log "FATAL: codex CLI install reported success but binary not on PATH"; return 2; }
}

ensure_jq() {
  has jq && return 0
  log "jq missing — attempting apt user install"
  if has apt-get && [[ -w /var/cache/apt ]]; then
    apt-get install -y --no-install-recommends jq >&2 && return 0
  fi
  # Fallback: download static binary into $LOCAL_BIN. Network must be available.
  log "falling back to static jq download"
  local arch url
  arch="$(uname -m)"
  case "$arch" in
    x86_64) url="https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-linux-amd64" ;;
    aarch64|arm64) url="https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-linux-arm64" ;;
    *) log "unsupported arch for jq fallback: $arch"; return 2 ;;
  esac
  if has curl; then
    curl -fsSL "$url" -o "$LOCAL_BIN/jq"
  elif has wget; then
    wget -qO "$LOCAL_BIN/jq" "$url"
  else
    log "FATAL: neither curl nor wget available to fetch jq fallback"
    return 2
  fi
  chmod +x "$LOCAL_BIN/jq"
  has jq || { log "jq still missing after fallback"; return 2; }
}

ensure_auth() {
  [[ -n "${CODEX_OPENAI_API_KEY:-}" ]] || {
    log "CODEX_OPENAI_API_KEY missing — set it in workspace/dev-knowledge/memory/secrets/codex.env"
    return 2
  }
  export HOME="${HOME:-/agent/data/.home}"
  local auth="$HOME/.codex/auth.json"
  if [[ -s "$auth" ]] && jq -e --arg k "$CODEX_OPENAI_API_KEY" \
       '.OPENAI_API_KEY == $k' "$auth" >/dev/null 2>&1; then
    return 0
  fi
  log "refreshing codex auth.json"
  printf '%s' "$CODEX_OPENAI_API_KEY" | codex login --with-api-key >/dev/null
}

# Probe whether bwrap can actually create namespaces in this kernel.
# Codex 0.128 enforces bwrap on Linux for read-only / workspace-write modes;
# if the kernel disallows unprivileged user namespaces, every shell command the
# model issues fails with `bwrap: No permissions to create a new namespace`.
# In that case we fall back to `--dangerously-bypass-approvals-and-sandbox`
# and rely on the wrapper's own perimeter (env redaction, --cd, --ignore-rules,
# --ignore-user-config, --ephemeral, post-run audit, HEAD-moved check,
# cross-repo dirty-tree check, plus the strengthened system_prompt). This is
# the documented use case for the bypass flag: "Intended solely for running
# in environments that are externally sandboxed." The xpander workspace IS
# that external sandbox.
probe_sandbox() {
  if fresh "$SANDBOX_FILE" 3600; then
    SANDBOX_MODE="$(cat "$SANDBOX_FILE")"
    return 0
  fi
  # Use codex's own sandbox helper to test — it embeds the same bwrap binary
  # codex exec uses, so a green probe means real runs will work.
  if codex sandbox linux -- /bin/sh -lc 'true' >/dev/null 2>&1; then
    SANDBOX_MODE="native"
  else
    SANDBOX_MODE="bypass"
  fi
  echo "$SANDBOX_MODE" > "$SANDBOX_FILE"
  log "sandbox probe: $SANDBOX_MODE"
}

write_state() {
  local codex_v jq_v
  codex_v="$(codex --version 2>/dev/null | head -1 || echo unknown)"
  jq_v="$(jq --version 2>/dev/null || echo unknown)"
  cat > "$STATE_FILE" <<JSON
{
  "ts": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "codex_version": "$codex_v",
  "jq_version": "$jq_v",
  "sandbox_mode": "$SANDBOX_MODE",
  "npm_prefix": "$NPM_PREFIX",
  "home": "${HOME:-/agent/data/.home}"
}
JSON
}

# ----------------------------- run ------------------------------------------
ensure_node
ensure_codex
ensure_jq
ensure_auth
probe_sandbox
write_state

export CODEX_PREFLIGHT_OK=1
export CODEX_SANDBOX_MODE="$SANDBOX_MODE"
export PATH

if [[ "${BASH_SOURCE[0]:-}" == "${0}" ]]; then
  # Run, not sourced — print state for the caller to consume.
  cat "$STATE_FILE"
fi
