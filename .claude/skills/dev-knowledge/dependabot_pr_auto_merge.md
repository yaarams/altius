# Skill: Dependabot PR — Quick Review, Approve & Merge

## Goal

When the user asks to handle Dependabot PRs on one or more xpander.ai repos, this skill:

1. Lists every **open** Dependabot PR on the target repo(s).
2. Performs a **quick automated review** of each PR (author, files touched, version-bump severity, CI status, mergeable state).
3. **Approves and merges** safe PRs (patch + minor bumps, lockfile-only changes, all checks green/pending).
4. **Skips and surfaces** anything risky (major version bumps, failing CI, files outside the dependency manifest set, conflicts).
5. Reports a concise per-repo summary back to the user.

This skill is for fast routine maintenance, not deep review. Anything non-trivial is escalated, never force-merged.

---

## When to Use

Trigger on any of:

- "Handle dependabot PRs on `<repo>`"
- "Review and merge dependabot PRs"
- "Quick review, approve, merge dependabot PRs"
- "Check all repos for dependabot PRs"
- Generic: "merge the dependabot stuff" (ask for repo scope if ambiguous)

---

## Mandatory Pre-flight

1. Read `workspace/dev-knowledge/skills/MUST_READ.md` — identity, branch, commit rules.
2. Read `workspace/dev-knowledge/skills/known_repos.md` — confirm target repo paths and integration branch.
3. Verify `gh` CLI identity:
   ```bash
   gh auth status 2>&1 | grep -E 'Logged in|Active account'
   gh api user --jq .login   # must print: xpander-fullstack-generalist
   ```
   If wrong, fix per `MUST_READ.md` §2a before proceeding.
4. Confirm scope from the user. Accept any of:
   - `all` → frontend + xpander-mono + xpander-sdk
   - `frontend`, `mono`/`xpander-mono`, `sdk`/`xpander-sdk`
   - One or more explicit `<owner>/<repo>` slugs.
5. **Create a Notion audit record** in the Product & Engineering board (see §Notion Audit Record) — one page per skill run, set `📍Priority = Now` while running. Move to `Validation` once all approve+merge calls are issued.

---

## Notion Audit Record (MANDATORY)

Every skill run creates **one** Notion page on the Product & Engineering board. **The page is an audit record / journal entry**, not a to-do task. Its purpose is to document what dependabot PRs existed at run time, what was decided, and what actions the agent took — so the team can later look up exactly what happened.

It is **not** a backlog task and must **not** describe "work the agent still needs to do". Everything actionable is performed during the same run; the page just records the outcome.

| Field | Value |
|---|---|
| **Database** | [🏗️ Product and engineering board](https://www.notion.so/xpander/22029ef830b380769cead5f0af55b9ec) |
| **Data source ID** | `22029ef8-30b3-80e1-b744-000bcde48853` |
| **Title** | `<Repo(s)> Dependabot run — <YYYY-MM-DD> (audit)` |
| **Type** | `Improvement` |
| **📍Priority while running** | `Now` |
| **📍Priority when done** | `Validation` (user moves to `Done` after verifying merges) |
| **Assignee** | The user who requested the run (use the `id` from the task's user details) |

Page body MUST include, in this order:
1. **Header block** — repo(s), run date, operator (the agent), requested by (the user), and a one-line statement that this page is an audit record.
2. **Summary table** — counts: auto-merged, skipped (per reason category), total open at run time.
3. **Auto-merged section** — table of every merged PR with: number+link, package, from→to version, final title, and the reason it was eligible (e.g. "patch/minor, manifest-only, only `validate-title` was failing").
4. **Skipped section** — grouped by reason (major bump, conflicts, unexpected files, real CI failures); each row links the PR.
5. **Status flow** — short note: `Now` while running → `Validation` after merges queued → user closes as `Done`.

Flow:
1. **At start of run** — after listing and classifying PRs but before approving/merging, create the page with `📍Priority = Now` and the full audit body filled in.
2. **After all approve+merge calls are issued** — update `📍Priority = Validation`. Do NOT set `Done`; the user closes after verifying merges landed on GitHub.

One page per run. Never one page per PR. Never reuse a previous run's page.

### Notion property quirks (verified 2026-04-28)

- The status property is literally named **`📍Priority`** (pin emoji is part of the property name). Pass it exactly as `"📍Priority"` in `properties` — any other spelling is silently ignored.
- Valid status values: `🕔 Ideas`, `Backlog`, `P2`, `P1`, **`Now`**, **`Validation`**, `Done`. The skill uses `Now` while running and `Validation` when done.
- `Type` does **not** include `chore`. Use **`Improvement`** for routine maintenance like dependabot runs.
- Always fetch the database first to get the data source URI (`collection://...`). The data source ID for this board is `22029ef8-30b3-80e1-b744-000bcde48853`; the database ID in the URL (`22029ef830b380769cead5f0af55b9ec`) is **not** the same thing.
- `Assignee` accepts a bare user UUID string in `properties`. The requestor's `id` is in the task's user details payload.

---

## Validate-Title Failures — Rename + Merge Workflow

A frequent skip reason on `xpander-ai/frontend` is the `validate-title` workflow rejecting Dependabot's default `deps: bump X from A to B` because the repo enforces conventional commits.

**Empirical baseline (2026-04-28 audit):** of 10 open frontend dependabot PRs, **6 of 10** were blocked solely by `validate-title`; every other check was already green. Always investigate this before classifying a frontend PR as "CI failing".

### Step A — Confirm `validate-title` is the only blocker

```bash
gh pr view "$PR" --repo "$REPO" \
  --json statusCheckRollup \
  --jq '.statusCheckRollup[] | {name, conclusion}'
```

Proceed with the rename **only if** the rollup shows:

- `validate-title` → `FAILURE`
- All other named checks → `SUCCESS` (or `PENDING`/`NEUTRAL`/`SKIPPED`)
- No other check is `FAILURE`/`ERROR`/`CANCELLED`

### Step B — Rename the PR title

```bash
gh pr edit "$PR" --repo "$REPO" \
  --title "chore(deps): bump <pkg> from <old> to <new>"
```

**Batch pattern (when multiple PRs need renaming):** `xpworkspace-bash` runs `/bin/sh` (dash, no associative arrays). Write a real bash script with `#!/usr/bin/env bash` to `workspace/tmp/rename_dependabot_prs.sh` and execute via `bash workspace/tmp/rename_dependabot_prs.sh`. Inline `declare -A` will fail with `Syntax error: "(" unexpected`.

### Step C — Approve and queue auto-merge

```bash
gh pr review "$PR" --repo "$REPO" --approve --body \
  'Automated dependabot quick-review: patch/minor bump, manifest-only diff, CI green. LGTM 🤖'
gh pr merge  "$PR" --repo "$REPO" --squash --delete-branch --auto
```

GitHub completes the merge once `validate-title` re-runs green.

### Verification

After the rename + approve + merge calls, confirm with:

```bash
gh pr view "$PR" --repo "$REPO" \
  --json title,state,mergeable,autoMergeRequest,reviewDecision \
  --jq '{title,state,mergeable,autoMergeRequest:(.autoMergeRequest!=null),reviewDecision}'
```

Expected: `state=OPEN, mergeable=MERGEABLE, autoMergeRequest=true, reviewDecision=APPROVED`.

### Rules

- Only rewrite the **title prefix** (`deps:` → `chore(deps):`). Preserve the `bump <pkg> from <old> to <new>` body verbatim — do **not** edit version numbers, package names, or anything else in the title.
- Renaming is allowed **only** when `validate-title` is the sole blocker. Never to fix typos, change scope, or restyle.
- Never rename major-version-bump titles to bypass review — majors stay skipped regardless of CI state.

---

## Repo → Slug Mapping

| Alias | GitHub slug |
|---|---|
| `frontend` | `xpander-ai/frontend` |
| `mono`, `xpander-mono` | `xpander-ai/xpander-mono` |
| `sdk`, `xpander-sdk` | `xpander-ai/xpander-sdk` |
| `all` | all three above |

Dependabot author filter on GitHub: `app/dependabot` (NOT `dependabot[bot]` for `gh pr list --author`).

---

## Quick-Review Decision Matrix

For each PR collected:

| Signal | Source | Auto-merge? |
|---|---|---|
| Author is `dependabot[bot]` | `pr.author.login` | required |
| Files changed are only manifests/locks (`package.json`, `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `requirements*.txt`, `pyproject.toml`, `poetry.lock`, `Pipfile*`, `go.mod`, `go.sum`, `Cargo.toml`, `Cargo.lock`, `Gemfile*`, `composer.*`) | `gh pr diff --name-only` | required |
| Version bump severity | parse PR title (`from X.Y.Z to A.B.C`) | **patch/minor → auto** · **major → SKIP** |
| CI status | `pr.statusCheckRollup` | all `SUCCESS` or `PENDING`/`NEUTRAL`/`SKIPPED` → ok · any `FAILURE`/`ERROR`/`CANCELLED` → SKIP |
| Mergeable | `pr.mergeable` / `mergeStateStatus` | `MERGEABLE` and not `CONFLICTING` → ok |
| Draft | `pr.isDraft` | draft → SKIP |

If **all** required boxes pass and severity is patch/minor → approve + merge. Otherwise classify as `skipped` with a one-line reason.

> **Major bumps** are NEVER auto-merged by this skill — they often have breaking API changes. Surface them to the user with the changelog link.

---

## Step-by-Step Workflow

### 1. Resolve target repos

From user input, build the list of `<owner>/<repo>` slugs (see mapping above).

### 2. List open Dependabot PRs per repo

```bash
gh pr list --repo "$REPO" \
  --author 'app/dependabot' --state open \
  --json number,title,url,headRefName,baseRefName,isDraft,mergeable,mergeStateStatus,author,files,statusCheckRollup \
  --limit 100
```

### 3. Quick review per PR

Run the helper script (see `dependabot_pr_auto_merge.sh`) which:

1. Parses the title to extract `from X to Y`. Major bump = first non-zero numeric component changed (handles `1.x → 2.x`, `0.1 → 0.2` is treated as minor for `0.x` libs but flagged).
2. Confirms `files` list is a subset of the safe manifests set.
3. Confirms CI rollup has no failures.
4. Confirms `mergeable == MERGEABLE` and `mergeStateStatus != CONFLICTING|BLOCKED|DIRTY`.

For every PR record an outcome: `ok` | `skip:<reason>`.

### 4. Approve + merge `ok` PRs

```bash
gh pr review "$PR" --repo "$REPO" --approve --body 'Automated dependabot quick-review: patch/minor bump, manifest-only diff, CI green. LGTM 🤖'
gh pr merge  "$PR" --repo "$REPO" --squash --delete-branch --auto
```

Notes:
- Use `--squash` (xpander.ai default merge style for dependency PRs).
- Use `--auto` so GitHub merges as soon as required checks finalize, even if currently `PENDING`.
- `--delete-branch` keeps the repo clean (Dependabot recreates branches as needed).

If the merge call fails because branch protection requires synchronous green checks, fall back to:
```bash
gh pr merge "$PR" --repo "$REPO" --squash --delete-branch
```
(no `--auto`) only when the rollup is fully `SUCCESS`.

### 5. Skipped PRs — leave as-is, do NOT close

For each skipped PR, capture:
- PR number, title, url
- One-line reason (e.g. `major version bump (1.x → 2.x)`, `CI failing: build-frontend`, `unexpected files changed: src/foo.ts`)

Do **not** comment on or close the PR — surface them in the final summary so the user can review manually.

### 6. Final summary

Report per repo:

```
📦 xpander-ai/frontend
  ✅ Approved + merged (auto): 6
     - #2347 @types/dagre 0.7.53 → 0.7.54
     - #2349 eslint-plugin-prettier 5.1.3 → 5.5.5
     - …
  ⚠️  Skipped (needs human review): 2
     - #2346 uuid 10.0.0 → 14.0.0  — major bump
     - #2343 eslint-plugin-import-helpers 1.3.1 → 2.0.0  — major bump
```

If nothing was merged, say so plainly. Do not pad output.

---

## Safety Rails

- **Never** push commits directly. Only `gh pr review --approve` and `gh pr merge`.
- **Never** auto-merge a PR whose `author.login` is not exactly `dependabot[bot]`.
- **Never** auto-merge a PR with files outside the manifest/lock allowlist.
- **Never** auto-merge a major version bump.
- **Never** dismiss or close a PR — only approve+merge or skip.
- If `gh` is rate-limited, stop and report. Do not retry blindly.
- Stop on first unexpected error per repo; continue to next repo.

---

## Quick One-Shot Invocation

```bash
bash workspace/dev-knowledge/skills/dependabot_pr_auto_merge.sh all
# or
bash workspace/dev-knowledge/skills/dependabot_pr_auto_merge.sh frontend mono
```

The script prints a structured summary to stdout. The agent should still produce a concise human summary in the final response.

---

## Lessons & Operational Notes

Distilled from real runs — keep this section accurate as new patterns emerge.

### `frontend` baseline distribution

- Roughly **half** of skipped frontend dependabot PRs are blocked solely by `validate-title`. Always run the Step A check before assuming code/build CI is broken.
- The other common skip reason is **major version bumps** — those go straight to manual review (often need code changes).
- `auto-merge-job` and `Vercel Preview Comments` are typically `SUCCESS` even when `validate-title` fails; do not be misled by the rolled-up `MERGEABLE_STATE != CLEAN`.

### Helper script lives in the repo

`workspace/dev-knowledge/skills/dependabot_pr_auto_merge.sh` is the canonical entry point.
The agent can run it directly; if it reports `CI has failing/cancelled checks`,
the agent should:

1. Inspect with the Step A `statusCheckRollup` query.
2. If only `validate-title` is failing on a non-major bump, follow the rename-and-merge
   workflow above.
3. Otherwise, leave skipped and surface to the user.

### Bash environment gotcha

`xpworkspace-bash` top-level shell is `/bin/sh` (dash). Any helper script that uses `declare -A`, `[[ ... ]]`, `<( ... )`, or other bashisms must:

- Be saved to disk with a `#!/usr/bin/env bash` shebang, **and**
- Be invoked explicitly via `bash <path>` (never `sh <path>`).

The rename batch script under `workspace/tmp/rename_dependabot_prs.sh` is the working template.

### Verifying the run end-to-end

Final sanity check after a run:

```bash
for pr in <renamed-prs>; do
  gh pr view "$pr" --repo "$REPO" \
    --json title,state,mergeable,autoMergeRequest,reviewDecision \
    --jq '{pr: '\"$pr\"', title, state, mergeable, autoMerge:(.autoMergeRequest!=null), review: .reviewDecision}'
done
```

If any PR is missing `autoMergeRequest=true` or `reviewDecision=APPROVED`, re-issue the corresponding `gh pr review`/`gh pr merge --auto` calls before reporting success.

---

## Out of Scope

- Resolving merge conflicts on Dependabot branches (let Dependabot rebase).
- Editing dependency code (e.g. fixing breaking changes from a major bump).
- Closing stale Dependabot PRs.
- Touching non-Dependabot PRs (use `pr_code_review_fix.md` for those).
