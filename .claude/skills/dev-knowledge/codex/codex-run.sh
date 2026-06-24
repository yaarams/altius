#!/usr/bin/env bash
# codex-run.sh — wrapper that invokes OpenAI Codex CLI as a sandboxed sub-agent.
#
# Owned by the codex_runner skill. Codex must NEVER be invoked directly — only
# through this wrapper. The wrapper is the policy enforcer (Codex's own kernel
# sandbox cannot fully engage in this container because bwrap/userns are
# unavailable; we rely on logical sandboxing + a pre/post-flight audit).
#
# Usage:
#   bin/codex-run.sh <REPO> <MODE> <PROMPT_FILE> [MODEL]
#
#   REPO         one of: frontend | xpander-mono | xpander-sdk | docs
#   MODE         one of: read | write
#   PROMPT_FILE  path to a prompt file (audited; never inline)
#   MODEL        optional. one of: gpt-5-codex | gpt-5 | o4-mini | o3
#                default: $CODEX_DEFAULT_MODEL or gpt-5-codex
#
# Env (must be set by the parent agent, never by Codex):
#   CODEX_OPENAI_API_KEY   required. Forwarded as OPENAI_API_KEY into Codex.
#   CODEX_DEFAULT_MODEL    optional. Overrides the gpt-5-codex default.
#   CODEX_NETWORK          optional. 1=enable outbound network in workspace-write
#                          mode (default 0/off). User-approved at the env-file level.
#   CODEX_MAX_TOKENS       optional. Soft output-token cap; SIGTERM Codex when exceeded.
#
# Env file autoload:
#   The wrapper sources workspace/dev-knowledge/memory/secrets/codex.env (chmod 600) at
#   start if present, so the operator does not have to export vars manually.
#
# Exit codes:
#   0   success, audit clean
#   2   bad args / missing prereqs
#   99  guardrail violation (protected paths touched, HEAD moved, etc.)
#   *   passthrough from `codex exec`

set -euo pipefail

# ----------------------------- env autoload ---------------------------------
# Pick up CODEX_OPENAI_API_KEY / CODEX_DEFAULT_MODEL / CODEX_NETWORK without
# requiring the operator to export them every shell. Permissions on the file
# stay 600; the wrapper never echoes the contents.
CODEX_ENV_FILE="${CODEX_ENV_FILE:-workspace/dev-knowledge/memory/secrets/codex.env}"
if [[ -r "$CODEX_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$CODEX_ENV_FILE"
  set +a
fi

# ----------------------------- preflight (self-heal) ------------------------
# Workspace pods may scale down or restore from backup; codex CLI / jq / auth
# can disappear between runs. The preflight installs anything missing into
# /agent/data/.persist (which IS the persistent volume), refreshes auth.json
# from CODEX_OPENAI_API_KEY, and probes whether bwrap can actually create
# user namespaces. It exports CODEX_SANDBOX_MODE = native | bypass.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/preflight.sh"

# ----------------------------- args -----------------------------------------
if [[ $# -lt 3 || $# -gt 4 ]]; then
  echo "usage: $0 <REPO> <MODE> <PROMPT_FILE> [MODEL]" >&2
  exit 2
fi

REPO="$1"
MODE="$2"
PROMPT_FILE="$3"
MODEL="${4:-${CODEX_DEFAULT_MODEL:-gpt-5-codex}}"

# ----------------------------- allowlists -----------------------------------
case "$REPO" in
  frontend|xpander-mono|xpander-sdk|docs) ;;
  *) echo "REPO not allowlisted: $REPO" >&2; exit 2 ;;
esac

case "$MODE" in
  read)  SANDBOX=read-only       ;;
  write) SANDBOX=workspace-write ;;
  *) echo "MODE must be read|write (got: $MODE)" >&2; exit 2 ;;
esac

# Allowlist covers Codex-tuned + general-purpose families currently in catalog.
# Expand here when a new model is approved; never silently accept.
case "$MODEL" in
  gpt-5-codex|gpt-5.1-codex|gpt-5.2-codex|gpt-5.3-codex) ;;
  gpt-5|gpt-5-mini|gpt-5-nano|gpt-5-pro) ;;
  gpt-5.1|gpt-5.2|gpt-5.2-pro) ;;
  gpt-5.4|gpt-5.4-mini|gpt-5.4-nano|gpt-5.4-pro) ;;
  gpt-5.5|gpt-5.5-pro) ;;
  o3|o3-mini|o3-pro|o4-mini) ;;
  *) echo "MODEL not allowlisted: $MODEL" >&2; exit 2 ;;
esac

# ----------------------------- preconditions --------------------------------
DEV_ROOT="${DEV_ROOT:-/agent/data/dev}"
REPO_DIR="$DEV_ROOT/$REPO"

[[ -d "$REPO_DIR/.git" ]] || { echo "$REPO_DIR is not a git repo" >&2; exit 2; }
[[ -r "$PROMPT_FILE" ]]  || { echo "prompt file not readable: $PROMPT_FILE" >&2; exit 2; }
[[ -n "${CODEX_OPENAI_API_KEY:-}" ]] || {
  echo "CODEX_OPENAI_API_KEY must be set in env or workspace/dev-knowledge/memory/secrets/codex.env" >&2
  exit 2; }

# Network toggle (write mode only — read mode never has writable_roots anyway).
NETWORK_ACCESS="false"
if [[ "${CODEX_NETWORK:-0}" == "1" ]]; then
  NETWORK_ACCESS="true"
fi

# Preflight has already installed/upgraded codex + jq and refreshed auth.json.
# These checks are now defensive belt-and-suspenders.
command -v codex >/dev/null || { echo "codex CLI not on PATH after preflight" >&2; exit 2; }
command -v jq    >/dev/null || { echo "jq missing after preflight"            >&2; exit 2; }
export HOME="${HOME:-/agent/data/.home}"
[[ -s "$HOME/.codex/auth.json" ]] || {
  echo "codex auth.json missing after preflight" >&2; exit 2; }

# ----------------------------- log dir --------------------------------------
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="workspace/tmp/codex-runs/$TS"
mkdir -p "$LOG_DIR"
touch "$LOG_DIR/.start"   # marker for `find -newer`

# Pre-flight HEAD snapshot (for post-run HEAD-moved audit).
PRE_HEAD="$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo none)"
echo "$PRE_HEAD" > "$LOG_DIR/pre_head.txt"

# Snapshot HOME paths we audit afterwards. We watch the SENSITIVE codex
# files individually (not the whole ~/.codex tree, because codex writes
# transient plugin caches, shell snapshots, log/, etc. on every run that
# are harmless housekeeping).
HOME_DIR="${HOME:-/agent/data/.home}"
PROTECTED_HOME_PATHS=(
  "$HOME_DIR/.config/gh"
  "$HOME_DIR/.gitconfig"
  "$HOME_DIR/.git-credentials"
  "$HOME_DIR/.netrc"
)
PROTECTED_CODEX_FILES=(
  "$HOME_DIR/.codex/auth.json"
  "$HOME_DIR/.codex/config.toml"
  "$HOME_DIR/.codex/AGENTS.md"
)
PROTECTED_CODEX_DIRS=(
  "$HOME_DIR/.codex/sessions"
)

# Capture the metadata that drove this run. Useful for audit + cost rollups.
cat > "$LOG_DIR/meta.json" <<META
{
  "ts": "$TS",
  "repo": "$REPO",
  "mode": "$MODE",
  "model": "$MODEL",
  "prompt_file": "$PROMPT_FILE",
  "pre_head": "$PRE_HEAD",
  "sandbox": "$SANDBOX",
  "sandbox_mode": "${CODEX_SANDBOX_MODE:-native}",
  "approval": "never",
  "max_tokens": "${CODEX_MAX_TOKENS:-}",
  "network_access": "$NETWORK_ACCESS"
}
META
cp -- "$PROMPT_FILE" "$LOG_DIR/prompt.md"

# ----------------------------- env redaction --------------------------------
# Strip everything that lets Codex talk to xpander, GitHub, AWS, or git/identity
# files. Codex sees ONLY OPENAI_API_KEY (sourced from the dedicated secret).
export HOME="$HOME_DIR"
unset XPANDER_API_KEY XPANDER_AGENT_ID XPANDER_AGENT_TOKEN \
      GH_TOKEN GITHUB_TOKEN GH_HOST \
      AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN \
      GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL

# Force `git` invoked by Codex to fail at commit time (no identity available).
export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null

export OPENAI_API_KEY="$CODEX_OPENAI_API_KEY"

# ----------------------------- run codex ------------------------------------
# Build flag set. In `native` mode the kernel sandbox is functional and we
# pass `-s read-only|workspace-write` as before. In `bypass` mode (kernel
# disallows user namespaces) we add `--dangerously-bypass-approvals-and-sandbox`
# — the workspace IS the external sandbox, and the wrapper's perimeter
# (env redaction, --cd, --ignore-rules, --ignore-user-config, --ephemeral,
# post-run audit, HEAD-moved check, cross-repo dirty-tree check, plus the
# strengthened system_prompt) is the actual policy boundary.
CODEX_FLAGS=(
  --cd "$REPO_DIR"
  --model "$MODEL"
  --ignore-user-config
  --ignore-rules
  --ephemeral
  --json
  --output-last-message "$LOG_DIR/last_message.txt"
  -c approval_policy=\"never\"
  -c sandbox_workspace_write.network_access="$NETWORK_ACCESS"
  -c sandbox_workspace_write.writable_roots='[]'
  -c sandbox_workspace_write.exclude_slash_tmp=true
  -c shell_environment_policy.exclude='["XPANDER_*","GH_*","GITHUB_*","AWS_*","AGENT_*","GIT_*_NAME","GIT_*_EMAIL"]'
)
if [[ "${CODEX_SANDBOX_MODE:-native}" == "bypass" ]]; then
  CODEX_FLAGS+=( --dangerously-bypass-approvals-and-sandbox )
  echo "[codex-run] bwrap unavailable in this kernel — running in bypass mode (workspace is the external sandbox)" >&2
else
  CODEX_FLAGS+=( --sandbox "$SANDBOX" )
fi

set +e
codex exec "${CODEX_FLAGS[@]}" - < "$PROMPT_FILE" \
  | tee "$LOG_DIR/events.jsonl"
CODEX_EXIT=${PIPESTATUS[0]}
set -e

# Detect bwrap-namespace-error events even on a 'successful' codex exit.
# Without this guard, codex 0.128 may complete the turn while every shell
# tool call inside it failed with `bwrap: No permissions to create a new
# namespace`, leading the model to fabricate output instead of inspecting
# the repo. Treat that as a hard failure and force a re-probe of the cache.
if [[ -s "$LOG_DIR/events.jsonl" ]] && \
   grep -q 'bwrap: No permissions to create a new namespace' "$LOG_DIR/events.jsonl"; then
  echo "GUARDRAIL: bwrap namespace failures detected mid-run — invalidating sandbox cache" >&2
  rm -f "${SANDBOX_FILE:-/agent/data/.home/.codex/.preflight/sandbox_mode}"
  CODEX_EXIT=99
fi

# ----------------------------- usage capture --------------------------------
# Distil per-turn usage from the JSONL event stream and append to the ledger.
LEDGER="workspace/dev-knowledge/memory/codex-runs/_ledger.jsonl"
mkdir -p "$(dirname "$LEDGER")"

if [[ -s "$LOG_DIR/events.jsonl" ]]; then
  jq -s '
    [.[] | select(.type=="turn.completed") | .usage] as $turns
    | {
        runs:                ($turns | length),
        input_tokens:        ($turns | map(.input_tokens // 0)        | add // 0),
        cached_input_tokens: ($turns | map(.cached_input_tokens // 0) | add // 0),
        output_tokens:       ($turns | map(.output_tokens // 0)       | add // 0)
      }
  ' "$LOG_DIR/events.jsonl" > "$LOG_DIR/usage.json"

  jq -c \
    --arg ts    "$TS" \
    --arg repo  "$REPO" \
    --arg mode  "$MODE" \
    --arg model "$MODEL" \
    --arg exit  "$CODEX_EXIT" \
    '. + {ts:$ts, repo:$repo, mode:$mode, model:$model, exit:($exit|tonumber)}' \
    "$LOG_DIR/usage.json" >> "$LEDGER"
fi

# ----------------------------- post-flight audit ----------------------------
# Even with a partial Codex sandbox, the wrapper enforces the real perimeter:
# nothing newer-than-start is allowed under workspace/, ~/.codex, or identity files.
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/agent/data/workspace}"

VIOLATIONS=()
while IFS= read -r f; do
  [[ -n "$f" ]] && VIOLATIONS+=("$f")
done < <(
  # Workspace audit: anything newer-than-start under workspace/ is a violation
  # except the wrapper's own log + ledger directories (and their contents).
  find "$WORKSPACE_ROOT" \
    -path "$WORKSPACE_ROOT/tmp/codex-runs" -prune -o \
    -path "$WORKSPACE_ROOT/memory/codex-runs" -prune -o \
    -newer "$LOG_DIR/.start" -print 2>/dev/null | head -50
  # Identity / GH / git audit: any change is a violation.
  find "${PROTECTED_HOME_PATHS[@]}" -newer "$LOG_DIR/.start" 2>/dev/null | head -50
  # Sensitive codex files: any modification post-start is a violation.
  for f in "${PROTECTED_CODEX_FILES[@]}"; do
    [[ -e "$f" && "$f" -nt "$LOG_DIR/.start" ]] && echo "$f"
  done
  # Sensitive codex dirs (e.g. sessions/): any new content is a violation.
  for d in "${PROTECTED_CODEX_DIRS[@]}"; do
    [[ -d "$d" ]] && find "$d" -newer "$LOG_DIR/.start" 2>/dev/null | head -50
  done
)

if (( ${#VIOLATIONS[@]} > 0 )); then
  {
    echo "GUARDRAIL VIOLATION: Codex modified protected paths:"
    printf '  %s\n' "${VIOLATIONS[@]}"
  } >&2
  printf '%s\n' "${VIOLATIONS[@]}" > "$LOG_DIR/violations.txt"
  exit 99
fi

# HEAD must not have moved — Codex is not allowed to commit/push/tag.
POST_HEAD="$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo none)"
echo "$POST_HEAD" > "$LOG_DIR/post_head.txt"
if [[ "$PRE_HEAD" != "$POST_HEAD" ]]; then
  echo "GUARDRAIL VIOLATION: $REPO HEAD moved $PRE_HEAD -> $POST_HEAD (Codex must not commit)" >&2
  exit 99
fi

# Cross-repo audit: only the target repo is allowed to be dirty.
git -C "$REPO_DIR" status --porcelain > "$LOG_DIR/git_status.txt" || true
for other in "$DEV_ROOT"/*/.git; do
  [[ -e "$other" ]] || continue
  od="${other%/.git}"
  [[ "$od" == "$REPO_DIR" ]] && continue
  if [[ -n "$(git -C "$od" status --porcelain 2>/dev/null)" ]]; then
    echo "GUARDRAIL VIOLATION: $od has uncommitted changes after Codex run" >&2
    exit 99
  fi
done

# ----------------------------- exit -----------------------------------------
if (( CODEX_EXIT != 0 )); then
  echo "codex exec exited $CODEX_EXIT — see $LOG_DIR/events.jsonl" >&2
  exit "$CODEX_EXIT"
fi

echo "codex-run complete. Logs: $LOG_DIR"
exit 0
