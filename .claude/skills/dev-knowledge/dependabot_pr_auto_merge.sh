#!/usr/bin/env bash
# dependabot_pr_auto_merge.sh
#
# Quick-review, approve, and squash-merge open Dependabot PRs across one or
# more xpander.ai repos. See workspace/dev-knowledge/skills/dependabot_pr_auto_merge.md for
# the full skill spec, decision matrix, and safety rails.
#
# Usage:
#   bash dependabot_pr_auto_merge.sh all
#   bash dependabot_pr_auto_merge.sh frontend mono sdk
#   bash dependabot_pr_auto_merge.sh xpander-ai/frontend
#
# Env vars:
#   DRY_RUN=1     # print decisions, do not approve/merge
#   MERGE_METHOD  # squash (default) | merge | rebase
#   AUTO_MERGE=1  # default 1 -> use --auto. Set 0 to require synchronous green CI.

set -uo pipefail

# ---- args -------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <repo|alias> [<repo|alias> ...]" >&2
  echo "  aliases: all | frontend | mono | xpander-mono | sdk | xpander-sdk" >&2
  exit 2
fi

DRY_RUN="${DRY_RUN:-0}"
MERGE_METHOD="${MERGE_METHOD:-squash}"
AUTO_MERGE="${AUTO_MERGE:-1}"

# ---- repo resolution --------------------------------------------------------
resolve_repo() {
  case "$1" in
    all)                       echo "xpander-ai/frontend xpander-ai/xpander-mono xpander-ai/xpander-sdk" ;;
    frontend)                  echo "xpander-ai/frontend" ;;
    mono|xpander-mono)         echo "xpander-ai/xpander-mono" ;;
    sdk|xpander-sdk)           echo "xpander-ai/xpander-sdk" ;;
    */*)                       echo "$1" ;;
    *) echo "" ;;
  esac
}

REPOS=()
for a in "$@"; do
  resolved="$(resolve_repo "$a")"
  if [[ -z "$resolved" ]]; then
    echo "unknown repo alias: $a" >&2
    exit 2
  fi
  for r in $resolved; do REPOS+=("$r"); done
done

# ---- gh identity check ------------------------------------------------------
GH_USER="$(gh api user --jq .login 2>/dev/null || true)"
if [[ "$GH_USER" != "xpander-fullstack-generalist" ]]; then
  echo "⚠️  gh active account is '$GH_USER' (expected 'xpander-fullstack-generalist')." >&2
  echo "   Fix per workspace/dev-knowledge/skills/MUST_READ.md §2a before running." >&2
  exit 3
fi

# ---- safe-files allowlist (regex, one alternation) --------------------------
SAFE_FILES_RE='^([^/]+/)*(package\.json|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|Pipfile|Pipfile\.lock|go\.mod|go\.sum|Cargo\.toml|Cargo\.lock|Gemfile|Gemfile\.lock|composer\.json|composer\.lock|\.github/dependabot\.yml)$'

# ---- helpers ----------------------------------------------------------------
# Parse "... from X.Y.Z to A.B.C" or "... from X.Y to A.B" out of the title.
# Echoes "<from> <to> <severity>" where severity is one of: major | minor | patch | unknown.
parse_bump() {
  local title="$1"
  local from to
  from="$(echo "$title" | sed -nE 's/.*from ([0-9]+(\.[0-9]+){0,3}).*/\1/p')"
  to="$(  echo "$title" | sed -nE 's/.*to ([0-9]+(\.[0-9]+){0,3}).*/\1/p')"
  if [[ -z "$from" || -z "$to" ]]; then
    echo "? ? unknown"
    return
  fi
  local fmaj fmin fpat tmaj tmin tpat
  IFS='.' read -r fmaj fmin fpat _ <<<"$from.0.0.0"
  IFS='.' read -r tmaj tmin tpat _ <<<"$to.0.0.0"
  fmaj="${fmaj:-0}"; fmin="${fmin:-0}"; fpat="${fpat:-0}"
  tmaj="${tmaj:-0}"; tmin="${tmin:-0}"; tpat="${tpat:-0}"
  if [[ "$fmaj" != "$tmaj" ]]; then
    echo "$from $to major"
  elif [[ "$fmin" != "$tmin" ]]; then
    # treat 0.x → 0.y as a major-equivalent bump (semver pre-1.0 convention)
    if [[ "$fmaj" == "0" ]]; then
      echo "$from $to major"
    else
      echo "$from $to minor"
    fi
  else
    echo "$from $to patch"
  fi
}

ci_status_summary() {
  # stdin: JSON array from statusCheckRollup
  # echoes "ok" or "fail:<context>,<context>..."
  jq -r '
    map(
      if .conclusion != null then .conclusion
      elif .state      != null then .state
      else "PENDING" end
    ) as $s
    | if ($s | map(select(. == "FAILURE" or . == "ERROR" or . == "CANCELLED" or . == "TIMED_OUT" or . == "ACTION_REQUIRED")) | length) > 0
      then "fail"
      else "ok" end
  '
}

# ---- per-repo processing ----------------------------------------------------
grand_total_merged=0
grand_total_skipped=0

for REPO in "${REPOS[@]}"; do
  echo
  echo "📦 $REPO"
  echo "  fetching open dependabot PRs..."

  PRS_JSON="$(gh pr list --repo "$REPO" \
      --author 'app/dependabot' --state open \
      --json number,title,url,headRefName,isDraft,mergeable,mergeStateStatus,author,files,statusCheckRollup \
      --limit 100 2>/dev/null || echo '[]')"

  count="$(echo "$PRS_JSON" | jq 'length')"
  if [[ "$count" -eq 0 ]]; then
    echo "  (no open dependabot PRs)"
    continue
  fi

  merged=()
  skipped=()

  for i in $(seq 0 $((count - 1))); do
    pr="$(echo "$PRS_JSON" | jq ".[$i]")"
    num="$(echo "$pr"   | jq -r '.number')"
    title="$(echo "$pr" | jq -r '.title')"
    url="$(echo "$pr"   | jq -r '.url')"
    author="$(echo "$pr" | jq -r '.author.login')"
    is_draft="$(echo "$pr" | jq -r '.isDraft')"
    mergeable="$(echo "$pr" | jq -r '.mergeable')"
    merge_state="$(echo "$pr" | jq -r '.mergeStateStatus')"
    files="$(echo "$pr" | jq -r '.files[].path')"
    rollup_json="$(echo "$pr" | jq '.statusCheckRollup')"

    reason=""

    # 1. author check
    if [[ "$author" != "dependabot[bot]" && "$author" != "app/dependabot" ]]; then
      reason="author is '$author', not dependabot[bot]"
    fi

    # 2. draft
    if [[ -z "$reason" && "$is_draft" == "true" ]]; then
      reason="PR is in draft"
    fi

    # 3. files allowlist
    if [[ -z "$reason" ]]; then
      while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        if ! [[ "$f" =~ $SAFE_FILES_RE ]]; then
          reason="unexpected files changed: $f"
          break
        fi
      done <<<"$files"
    fi

    # 4. version bump severity
    if [[ -z "$reason" ]]; then
      read -r from to severity <<<"$(parse_bump "$title")"
      if [[ "$severity" == "major" ]]; then
        reason="major version bump ($from → $to)"
      elif [[ "$severity" == "unknown" ]]; then
        reason="could not parse version bump from title"
      fi
    else
      from="?"; to="?"; severity="?"
    fi

    # 5. CI rollup
    if [[ -z "$reason" ]]; then
      ci="$(echo "$rollup_json" | ci_status_summary)"
      if [[ "$ci" != "ok" ]]; then
        reason="CI has failing/cancelled checks"
      fi
    fi

    # 6. mergeable
    if [[ -z "$reason" ]]; then
      case "$merge_state" in
        CLEAN|HAS_HOOKS|UNSTABLE|BEHIND) : ;;
        BLOCKED) : ;;  # blocked usually means "required reviews not met" — our approve will fix
        DIRTY|CONFLICTING) reason="merge conflicts (mergeStateStatus=$merge_state)" ;;
        *)                 : ;;
      esac
    fi
    if [[ -z "$reason" && "$mergeable" == "CONFLICTING" ]]; then
      reason="merge conflicts"
    fi

    # ---- decision
    if [[ -n "$reason" ]]; then
      skipped+=("#$num $title — $reason")
      printf '  ⚠️  skip  #%s  %s  — %s\n' "$num" "$title" "$reason"
      continue
    fi

    # ---- approve + merge
    printf '  ✅ ok    #%s  %s  (%s → %s, %s)\n' "$num" "$title" "$from" "$to" "$severity"
    if [[ "$DRY_RUN" == "1" ]]; then
      merged+=("#$num $title (DRY_RUN)")
      continue
    fi

    if ! gh pr review "$num" --repo "$REPO" --approve \
         --body 'Automated dependabot quick-review: patch/minor bump, manifest-only diff, CI green. LGTM 🤖' >/dev/null 2>&1; then
      skipped+=("#$num $title — approve failed")
      echo "     ❌ approve failed for #$num"
      continue
    fi

    merge_args=( "--$MERGE_METHOD" --delete-branch )
    [[ "$AUTO_MERGE" == "1" ]] && merge_args+=( --auto )

    if ! gh pr merge "$num" --repo "$REPO" "${merge_args[@]}" >/dev/null 2>&1; then
      # retry without --auto in case branch protection rejects it
      if [[ "$AUTO_MERGE" == "1" ]]; then
        if gh pr merge "$num" --repo "$REPO" "--$MERGE_METHOD" --delete-branch >/dev/null 2>&1; then
          merged+=("#$num $title (synchronous merge)")
          continue
        fi
      fi
      skipped+=("#$num $title — merge failed")
      echo "     ❌ merge failed for #$num ($url)"
      continue
    fi

    merged+=("#$num $title")
  done

  # ---- per-repo summary
  echo
  echo "  Summary for $REPO:"
  echo "    ✅ approved + merged: ${#merged[@]}"
  for m in "${merged[@]}";  do echo "       - $m"; done
  echo "    ⚠️  skipped:           ${#skipped[@]}"
  for s in "${skipped[@]}"; do echo "       - $s"; done

  grand_total_merged=$((grand_total_merged + ${#merged[@]}))
  grand_total_skipped=$((grand_total_skipped + ${#skipped[@]}))
done

echo
echo "=========================================="
echo "GRAND TOTAL across ${#REPOS[@]} repo(s):"
echo "  ✅ approved + merged: $grand_total_merged"
echo "  ⚠️  skipped:           $grand_total_skipped"
echo "=========================================="
