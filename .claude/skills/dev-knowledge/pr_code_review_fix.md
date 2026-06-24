# AI Agent Skill: PR Code Review — Fix & Resolve Comments

## Goal

When a PR has been reviewed and the user asks to **"fix code review comments"** / **"address review feedback"** / **"resolve review threads"**, systematically:

1. Pull every open review comment (human + bot: CodeRabbit, Copilot, Sonar, etc.) on the PR
2. Triage each comment (apply / push back / out of scope)
3. Implement the fixes on the PR's branch
4. Validate locally (lint, type-check, tests, pre-commit)
5. Commit and push to the same branch
6. Reply to each thread and resolve it
7. Report back to the user with a concise summary

---

## When to Use

Trigger on any of:

- "Fix the code review comments on PR #123"
- "Address the review feedback"
- "Resolve the open review threads on my PR"
- "CodeRabbit / Copilot / reviewer left comments — handle them"
- "Post-review cleanup on <PR url>"

---

## Mandatory Pre-flight

Before touching any code:

1. **Read `workspace/dev-knowledge/skills/MUST_READ.md`** — branch / commit / identity rules.
2. **Read `workspace/dev-knowledge/skills/known_repos.md`** — confirm repo path and integration branch.
3. **Verify `gh` CLI identity** — run `gh auth status 2>&1 | grep -E 'Logged in|Active account'`. Active account **must** be `xpander-fullstack-generalist` (git commit identity and `gh` auth are independent). See `MUST_READ.md` §2 for the fix path if it's wrong.
4. **Read `AGENTS.md` / `CLAUDE.md`** in the target repo (root + relevant subdirs).
5. Get the PR identifier from the user. Required:
   - PR URL (preferred) **or** PR number + repo (e.g. `xpander-ai/xpander-mono#456`)
   - If missing, ask via `xpask_for_information`.

> This is **continuing work on an existing PR** — per `MUST_READ.md` §7, **do NOT** reset to the integration branch. Check out the PR's branch directly.

---

## Step-by-Step Workflow

### 1. Identify the PR and its branch

```bash
# Set once per session
export PR="<pr-number>"
export REPO="xpander-ai/<repo>"   # e.g. xpander-ai/xpander-mono

gh pr view "$PR" --repo "$REPO" --json number,title,state,isDraft,headRefName,baseRefName,author,url
```

- Confirm the PR is open and not merged.
- Note `headRefName` (branch to check out) and `baseRefName` (diff base).

### 2. Check out the PR's branch locally — **and pull latest, always**

> ⚠️ **MANDATORY: Always pull the latest of the PR branch before editing.**
> The user, another agent (you-from-a-previous-session, a parallel agent, or a teammate), or CI bots may have pushed commits since your last interaction. Editing a stale local copy will produce merge conflicts on push, lost work, or a force-push that overwrites someone else's commits. **No exceptions** — even if you "just worked on this branch a minute ago".

```bash
cd /agent/data/dev/<repo>
git fetch origin                              # MANDATORY — pull all refs from remote
git status                                    # ensure clean; if dirty, ASK user before stashing/discarding
gh pr checkout "$PR" --repo "$REPO"           # switches to the PR's head branch
git pull --ff-only origin "$(git branch --show-current)"   # MANDATORY — fast-forward to remote head

# Verify you're on the latest commit before doing anything else:
git log --oneline -1
git rev-parse HEAD
git status -sb                                # should show: ## <branch>...origin/<branch>  (no "behind")
```

If `git pull --ff-only` fails (you have local commits that diverged from remote):

1. **STOP.** Do not edit, do not force-push.
2. Inspect: `git log --oneline origin/<branch>..HEAD` (your local-only commits) and `git log --oneline HEAD..origin/<branch>` (remote-only commits).
3. Rebase onto remote: `git pull --rebase origin <branch>` and resolve any conflicts before continuing.
4. Only then proceed to step 3 (pull review comments).

> Never run `git checkout develop` here — the PR branch is already the right place.
> Never skip `git fetch` + `git pull --ff-only`, even if it "feels redundant". You can't tell from local state alone whether the remote moved.

### 3. Pull all review comments and threads

Use the GitHub API directly so we get the **resolved/unresolved** state and the **review-thread IDs** (needed to resolve threads later). The `gh pr view --comments` output is incomplete for this purpose.

#### 3a. Inline review comments (the most important set)

```bash
gh api "repos/$REPO/pulls/$PR/comments" --paginate \
  --jq '.[] | {id, user: .user.login, path, line: (.line // .original_line), side, in_reply_to_id, body, html_url}' \
  > workspace/tmp/pr_${PR}_inline_comments.json
```

#### 3b. Review-level summary comments

```bash
gh api "repos/$REPO/pulls/$PR/reviews" --paginate \
  --jq '.[] | {id, user: .user.login, state, submitted_at, body}' \
  > workspace/tmp/pr_${PR}_reviews.json
```

#### 3c. Issue-style PR comments (general thread)

```bash
gh api "repos/$REPO/issues/$PR/comments" --paginate \
  --jq '.[] | {id, user: .user.login, created_at, body}' \
  > workspace/tmp/pr_${PR}_issue_comments.json
```

#### 3d. Review threads with resolution state (GraphQL — required for resolving)

```bash
gh api graphql -f query='
  query($owner:String!, $repo:String!, $pr:Int!) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$pr) {
        reviewThreads(first:100) {
          nodes {
            id
            isResolved
            isOutdated
            path
            line
            comments(first:50) {
              nodes { id databaseId author { login } body createdAt url }
            }
          }
        }
      }
    }
  }' \
  -F owner="${REPO%/*}" -F repo="${REPO#*/}" -F pr="$PR" \
  > workspace/tmp/pr_${PR}_threads.json
```

The `nodes[].id` is the **thread node ID** — pass it to the resolve mutation in step 7.

### 4. Triage each comment

Build a working list (`workspace/tmp/pr_${PR}_triage.md`) with one row per **unresolved** thread:

| # | File:Line | Author | Severity | Decision | Notes |
|---|---|---|---|---|---|
| 1 | `src/foo.ts:42` | coderabbitai | nitpick | apply | rename var |
| 2 | `api/auth.py:88` | reviewer-x | major | apply | add null check |
| 3 | `README.md:12` | copilot | suggestion | reject | out of scope |

Decision values:

- **apply** — implement exactly what's asked
- **apply-with-tweak** — fix the underlying issue but in a different/better way
- **reject** — explicitly disagree; will reply with reasoning
- **defer** — valid but out of scope for this PR; create follow-up ticket
- **already-fixed** — addressed by another change; just resolve

> When ambiguous, **prefer applying the change**. Bot suggestions (CodeRabbit, Copilot) are usually safe nitpicks; skim quickly, apply the obviously correct ones.

### 5. Implement the fixes

- Group changes by file to minimize diff churn.
- Follow the repo's conventions (`AGENTS.md`, existing patterns).
- Re-read the surrounding code before each edit — don't blind-apply a suggestion that no longer fits the current code.
- Keep changes **strictly scoped** to review feedback. Do not refactor unrelated code in the same commit.

### 6. Validate locally (MANDATORY)

Discover and run repo tooling — never skip this:

```bash
# Pre-commit (if .pre-commit-config.yaml exists)
pre-commit run --files <changed-files>

# Repo-specific checks — examples; consult AGENTS.md / package.json / Makefile
pnpm lint && pnpm typecheck && pnpm test    # frontend / monorepo packages
ruff check . && pytest -q                    # python services / xpander-sdk
cargo check && cargo test                    # rust crates
```

If validation fails:

- Fix what you can.
- For environment-specific failures (missing system libs, no network), document them in the PR comment and continue — they'll run in CI.

### 7. Commit, push, reply, resolve

#### 7a. Commit

One commit per logical group is fine; a single squash commit is also acceptable. Use the **same ticket** as the PR (extract from branch name `{type}/{base}/{TICKET}` or PR title).

```bash
git add -A
git commit -m "chore(TICKET-ID): address review feedback"
# or fix(...) / feat(...) matching the type of changes
git push origin HEAD
```

Identity (verify before commit):

```bash
git config user.name   # xpander-fullstack-generalist
git config user.email  # ai_employee_2@xpander.ai
```

**No `Co-authored-by` trailers — ever** (per `MUST_READ.md`).

#### 7b. Reply to each thread

Reply on the **specific inline comment** so the conversation stays threaded:

```bash
# Reply to a specific inline comment by its comment ID (in_reply_to)
gh api "repos/$REPO/pulls/$PR/comments" \
  -F body="Done in <SHA>. <one-line note>" \
  -F in_reply_to=<COMMENT_ID> \
  --method POST
```

Reply tone:

- **apply** → `"Done in <short-sha>."` (optionally one-line context)
- **apply-with-tweak** → `"Done in <short-sha> — went with <approach> instead because <reason>."`
- **reject** → `"Keeping as-is: <reason>."`
- **defer** → `"Tracked in <TICKET-ID>; out of scope here."`
- **already-fixed** → `"Already addressed by <ref>; resolving."`

#### 7c. Resolve the thread

Use the GraphQL `resolveReviewThread` mutation with the **thread node ID** from step 3d:

```bash
gh api graphql -f query='
  mutation($threadId:ID!) {
    resolveReviewThread(input:{threadId:$threadId}) {
      thread { id isResolved }
    }
  }' -F threadId="<THREAD_NODE_ID>"
```

Loop over all threads marked **apply / apply-with-tweak / already-fixed / defer** in the triage table.
Threads marked **reject** stay unresolved unless the user explicitly says otherwise — leave them for the reviewer to close.

### 8. Final report to the user

Return a concise markdown summary:

```markdown
## Review feedback on PR #<n> — handled

- **Applied (X):** <bullet list, file:line + one-liner>
- **Applied with tweak (Y):** <bullet list>
- **Rejected (Z):** <bullet list with reasons — left unresolved>
- **Deferred (W):** <ticket refs>

**Commits:** <sha1>, <sha2>
**Validation:** lint ✓ / type ✓ / tests ✓ (or: failed locally — env-specific, will run in CI)
**Threads resolved:** N / M
```

---

## Common Pitfalls

| Pitfall | Correct approach |
|---|---|
| Resetting to `develop`/`main` before fixing comments | Continuing work — checkout the PR branch directly (`gh pr checkout`) |
| Editing without pulling latest of the PR branch | **Always** `git fetch origin` + `git pull --ff-only` before any edit. Another agent, the user, or CI may have pushed since you last looked. Skipping this causes conflicts on push or silent overwrites. |
| Using `gh pr view --comments` only | It misses inline comments and resolution state — use the API endpoints in step 3 |
| Replying with a top-level PR comment instead of threading | Use `in_reply_to=<comment_id>` so each thread stays coherent |
| Resolving threads without replying | Always reply first so reviewers know what changed |
| Auto-applying every bot nitpick blindly | Skim; reject with a brief reason when the suggestion is wrong or stylistic-only against repo conventions |
| Mixing unrelated refactors into the review-fix commit | Keep the diff strictly scoped to feedback; open a separate PR for tangents |
| Forgetting to push before replying "Done in <sha>" | Push first, then reply with the actual pushed SHA |
| Skipping pre-commit / lint | Always run repo tooling before pushing — CI will fail otherwise |
| Co-author trailer on the commit | Forbidden — strip it |

---

## Quick Reference — API Endpoints

| Purpose | Endpoint |
|---|---|
| List inline review comments | `GET /repos/{owner}/{repo}/pulls/{pr}/comments` |
| List reviews (summaries) | `GET /repos/{owner}/{repo}/pulls/{pr}/reviews` |
| List issue-style PR comments | `GET /repos/{owner}/{repo}/issues/{pr}/comments` |
| Reply to inline comment | `POST /repos/{owner}/{repo}/pulls/{pr}/comments` with `in_reply_to` |
| Resolve thread (GraphQL) | `mutation resolveReviewThread(input:{threadId})` |
| List threads with resolved state (GraphQL) | `repository.pullRequest.reviewThreads` |

---

## Related Skills

- `workspace/dev-knowledge/skills/MUST_READ.md` — branch/commit/identity rules
- `workspace/dev-knowledge/skills/pr_title_description.md` — PR title/description conventions (referenced if a follow-up PR is opened for deferred items)
- `workspace/dev-knowledge/skills/known_repos.md` — repo paths and integration branches
- `workspace/dev-knowledge/skills/planning_workflow.md` — for non-trivial multi-comment reviews, persist a plan
