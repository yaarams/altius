#!/usr/bin/env bash
# render_diagram.sh — render a Mermaid diagram to an image via mmdc.
#
# Usage:
#   render_diagram.sh -i <input.mmd|->  -o <output.png|svg|pdf>
#                     [-t <theme>] [-b <background>] [-w <width>] [-H <height>]
#                     [-s <scale>] [-c <mermaid-config.json>]
#
# Examples:
#   render_diagram.sh -i diagram.mmd -o diagram.png
#   echo "flowchart LR; A-->B" | render_diagram.sh -i - -o out.svg -t dark
#
# Defaults: theme=default, background=white, scale=2 (retina), format inferred from -o.
set -euo pipefail

THEME="default"
BACKGROUND="white"
WIDTH=""
HEIGHT=""
SCALE="2"
CONFIG=""
INPUT=""
OUTPUT=""

while getopts "i:o:t:b:w:H:s:c:h" opt; do
  case "$opt" in
    i) INPUT="$OPTARG" ;;
    o) OUTPUT="$OPTARG" ;;
    t) THEME="$OPTARG" ;;
    b) BACKGROUND="$OPTARG" ;;
    w) WIDTH="$OPTARG" ;;
    H) HEIGHT="$OPTARG" ;;
    s) SCALE="$OPTARG" ;;
    c) CONFIG="$OPTARG" ;;
    h|*) sed -n '2,15p' "$0"; exit 0 ;;
  esac
done

if [[ -z "$INPUT" || -z "$OUTPUT" ]]; then
  echo "error: -i <input> and -o <output> are required" >&2
  exit 2
fi

SKILL_DIR_PRE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Self-heal: delegate to bootstrap.sh which handles mmdc, fontconfig, fonts,
# puppeteer config, and PVC snapshot/restore in an idempotent way.
if [[ -x "${SKILL_DIR_PRE}/bootstrap.sh" ]]; then
  "${SKILL_DIR_PRE}/bootstrap.sh" >&2 || {
    echo "warn: bootstrap.sh reported errors; attempting render anyway…" >&2
  }
elif ! command -v mmdc >/dev/null 2>&1; then
  echo "error: mmdc not found and bootstrap.sh missing. Install with: npm install -g @mermaid-js/mermaid-cli" >&2
  exit 127
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUPPETEER_CFG="${SKILL_DIR}/puppeteer.json"

# Always use --no-sandbox (workspace runs as a sandboxed container itself).
if [[ ! -f "$PUPPETEER_CFG" ]]; then
  cat > "$PUPPETEER_CFG" <<'JSON'
{ "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"] }
JSON
fi

# Stage stdin input to a temp .mmd file when -i is '-'.
TMPDIR_RUN="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_RUN"' EXIT
if [[ "$INPUT" == "-" ]]; then
  INPUT="${TMPDIR_RUN}/diagram.mmd"
  cat > "$INPUT"
fi

mkdir -p "$(dirname "$OUTPUT")"

ARGS=(-i "$INPUT" -o "$OUTPUT" -t "$THEME" -b "$BACKGROUND" -s "$SCALE" -p "$PUPPETEER_CFG")
[[ -n "$WIDTH"  ]] && ARGS+=(-w "$WIDTH")
[[ -n "$HEIGHT" ]] && ARGS+=(-H "$HEIGHT")
[[ -n "$CONFIG" ]] && ARGS+=(-c "$CONFIG")

mmdc "${ARGS[@]}" >&2
echo "$OUTPUT"
