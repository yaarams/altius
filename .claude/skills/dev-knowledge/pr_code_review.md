# AI Agent Skill: PR Code Review — Perform a Review

## Goal

When the user asks to **"review this PR"** / **"do a code review"** / **"check PR #N"**, perform a thorough, professional code review and post the results back to the PR as inline comments + a single review summary. The opposite of `pr_code_review_fix.md`: there we *receive* feedback; here we *produce* it.

Outcomes:

1. Pull the PR diff, files, CI status, and existing comments.
2. Read repo conventions (`AGENTS.md` / `CLAUDE.md`, lint/test config) so feedback matches the project's standards.
3. Evaluate the diff against the rubric (correctness, security, performance, tests, style, scope).
4. Post inline comments on the specific lines that warrant feedback.
5. Submit a single PR review with verdict (`COMMENT` / `APPROVE` / `REQUEST_CHANGES`) and an executive summary. **Always include a `Reviewed by Gilfoyle` attribution line at the bottom of the review summary body** (see `workspace/dev-knowledge/memory/agent_identity.md` → "PR Review Attribution"). The GitHub actor remains `xpander-fullstack-generalist`; Gilfoyle is named in the body, not the auth identity.
6. Report a concise summary back to the user.

---

## When to Use

Trigger on any of:

- "Review PR #123" / "Code review on <PR url>"
- "Take a look at this pull request"
- "Approve this PR if it looks good" (still produce a review; verdict depends on findings)
- "What do you think of <PR url>?"
- "Check this PR for issues / regressions / security problems"

Do **not** use this skill when the user wants the agent to *fix* feedback on its own PR — that's `pr_code_review_fix.md`.

---

## Mandatory Pre-flight

Before opening any file:

1. **Read `workspace/dev-knowledge/skills/MUST_READ.md`** — branch / commit / identity rules (the review identity must be `xpander-fullstack-generalist`).
2. **Read `workspace/dev-knowledge/skills/known_repos.md`** — confirm repo path, integration branch, and tech stack for context-aware feedback.
3. **Verify `gh` CLI identity** — `gh auth status 2>&1 | grep -E 'Logged in|Active account'`. Active account **must** be `xpander-fullstack-generalist`. If wrong, fix per `MUST_READ.md` §2a before posting any comment (otherwise the review shows up as the wrong user).
4. **Read `AGENTS.md` / `CLAUDE.md`** in the target repo (root + package-level dirs touched by the PR) — these define what "correct" looks like for this repo.
5. Get the PR identifier from the user. Required:
   - PR URL (preferred), or PR number + repo (e.g. `xpander-ai/xpander-mono#456`).
   - If missing, ask via `xpask_for_information`.

> You are reviewing **someone else's** PR. Do **not** check out the branch unless you need to run tests locally. Read-only API access is enough for most reviews.

---

## Step-by-Step Workflow

### 1. Identify the PR and gather metadata

```bash
export PR="<pr-number>"
export REPO="xpander-ai/<repo>"   # e.g. xpander-ai/xpander-mono

gh pr view "$PR" --repo "$REPO" --json \
  number,title,state,isDraft,headRefName,baseRefName,author,url,additions,deletions,changedFiles,mergeable,mergeStateStatus,labels
```

Notes:

- If `state != OPEN` → ask the user whether to still review (closed/merged PRs usually don't need it).
- If `isDraft == true` → still review, but call it out in the summary; the author may not be ready.
- Author = the **PR author**, not the agent. Reviews from the agent's own PRs are pointless — ask the user for confirmation if the author equals the agent.

### 2. Pull the diff and changed files

```bash
mkdir -p workspace/tmp/pr_${PR}_review

# Full unified diff
gh pr diff "$PR" --repo "$REPO" > workspace/tmp/pr_${PR}_review/diff.patch

# File-by-file metadata (status, additions, deletions, patch hunks)
gh api "repos/$REPO/pulls/$PR/files" --paginate \
  > workspace/tmp/pr_${PR}_review/files.json

# Commits in the PR (helps spot WIP/squash candidates and unrelated changes)
gh api "repos/$REPO/pulls/$PR/commits" --paginate \
  --jq '.[] | {sha: .sha[0:8], message: .commit.message, author: .commit.author.name}' \
  > workspace/tmp/pr_${PR}_review/commits.json
```

### 3. Pull CI status and existing reviews

```bash
# CI checks — failing CI is almost always worth flagging
gh pr checks "$PR" --repo "$REPO" > workspace/tmp/pr_${PR}_review/checks.txt

# Existing reviews and inline comments — don't repeat what others have said
gh api "repos/$REPO/pulls/$PR/reviews"  --paginate > workspace/tmp/pr_${PR}_review/reviews.json
gh api "repos/$REPO/pulls/$PR/comments" --paginate > workspace/tmp/pr_${PR}_review/inline_comments.json
gh api "repos/$REPO/issues/$PR/comments" --paginate > workspace/tmp/pr_${PR}_review/issue_comments.json
```

If another reviewer (human or bot like CodeRabbit / Copilot / Sonar) has already covered an issue, **don't restate it** — either skip it or `+1` it briefly so the author knows it's a real concern, not a one-off.

### 4. Optional: check out the branch (only if you need to run code)

Most reviews are static-analysis only. Check out only if:

- The PR touches code you genuinely need to execute (a tricky migration, a new test runner, a perf-sensitive path).
- The repo has cheap/fast `lint` + `typecheck` + `test` commands documented in `AGENTS.md`.

If you do check out: follow the "continuing work on existing PR" rules from `MUST_READ.md` §7 — `git fetch origin && gh pr checkout $PR --repo $REPO && git pull --ff-only`. Don't push anything from this branch under any circumstances during a review.

### 5. Evaluate against the review rubric

Go through the diff once per axis. Take notes per file:line in `workspace/tmp/pr_${PR}_review/findings.md`.

#### 5a. Rubric (in order — stop early if a higher tier blocks merge)

| # | Axis | What to look for | Severity if violated |
|---|---|---|---|
| 1 | **Correctness** | Off-by-ones, null/undefined handling, race conditions, error paths, wrong API contracts, missing await, swallowed exceptions, regressions in existing behaviour | **Major** (blocks merge) |
| 2 | **Security** | Auth/authorization gaps, secret leakage, injection (SQL / shell / template), unsafe deserialization, SSRF, broken access control, weak crypto, logging PII/tokens | **Major** (blocks merge) |
| 3 | **Data integrity & migrations** | Irreversible migrations, missing backfills, schema/code drift, breaking API/DB changes without versioning, missing indexes on new query patterns | **Major** (blocks merge) |
| 4 | **Tests** | New behaviour without tests, tests that don't exercise the new code path, brittle/flaky tests, snapshot churn used as test, removed tests without justification | **Major** if untested critical path; **Minor** for nice-to-haves |
| 5 | **Performance** | N+1 queries, sync work in hot paths, unbounded loops/lists/payloads, missing caching, accidental O(n²) in user-visible paths | **Major** if user-facing; **Minor** otherwise |
| 6 | **API & contract design** | Breaking changes to public types, inconsistent naming with the rest of the codebase, leaky abstractions, public surface that should be internal | **Major** for breaking; **Minor** otherwise |
| 7 | **Repo conventions** | Violates `AGENTS.md` / `CLAUDE.md` / lint / formatter / type-check rules, ignores existing patterns in neighbouring code, wrong logger / error handler / model base class | **Minor** (but cite the convention) |
| 8 | **Readability & maintainability** | Dead code, commented-out code, magic numbers, opaque names, functions doing >1 thing, oversized files, missing docstrings on public APIs | **Minor** / **Nitpick** |
| 9 | **Scope discipline** | Unrelated refactors mixed in, drive-by formatting churn, vendored deps unrelated to the ticket, secret/config files committed by accident | **Minor** unless it hides a Major change |
| 10 | **Docs & user-facing copy** | README / changelog / migration notes missing for behaviour changes, customer-facing strings with typos | **Minor** |

#### 5b. Severity → comment style

| Severity | Use when… | Comment opener |
|---|---|---|
| **Major** | Blocks merge until addressed | `**Blocking:** …` |
| **Minor** | Should fix but not blocking | `**Suggestion:** …` |
| **Nitpick** | Style / personal preference | `**Nit:** …` |
| **Question** | You want context, not a change | `**Question:** …` |
| **Praise** | Genuinely well-done piece of code (use sparingly, max 1–2 per review) | `**Nice:** …` |

Only `Major` findings should drive a `REQUEST_CHANGES` verdict. `Minor` + `Nitpick` alone → `COMMENT`. No findings worth noting → `APPROVE` with a short summary.

#### 5c. What NOT to flag

- Existing code outside the diff ("while we're here, this old function is bad") — out of scope; open a separate ticket.
- Personal style preferences that aren't in the linter / formatter / `AGENTS.md`.
- Anything already commented by another reviewer/bot — don't pile on.
- Whitespace / formatting that the formatter would auto-fix on commit.

### 6. Write inline comments

One comment per concrete finding, anchored to the exact `file` + `line` (the **right side** of the diff, i.e. the new code).

```bash
# 6a. Resolve the head SHA — required by the API
HEAD_SHA=$(gh api "repos/$REPO/pulls/$PR" --jq .head.sha)
```

Queue each finding as a JSON object first; submit them all in one review (step 7) so the author gets one notification, not N.

Example queue file `workspace/tmp/pr_${PR}_review/comments.json`:

```json
[
  {
    "path": "services/api/src/foo.py",
    "line": 42,
    "side": "RIGHT",
    "body": "**Blocking:** `user_id` is read from the JWT but never validated against the path param. A user with a valid token can mutate another user's resource. Suggest `if claims.sub != user_id: raise Forbidden()` before the DB call."
  },
  {
    "path": "services/api/src/foo.py",
    "line": 88,
    "side": "RIGHT",
    "body": "**Suggestion:** consider extracting the retry block into `utils.retry.with_backoff` — same pattern is used in `bar.py:120` and `baz.py:55`."
  }
]
```

Guidelines for body text:

- **Lead with severity** (`Blocking:` / `Suggestion:` / `Nit:` / `Question:`).
- **State the problem in one sentence**, then give a concrete fix (code snippet or one-liner). Avoid "I think maybe…" — be direct but not rude.
- **Quote the relevant rule** when citing repo conventions: `Per AGENTS.md > "Error handling": …`.
- For multi-line issues, use a small ```suggestion``` block so the author can apply it with one click.
- Keep it short. If the explanation needs >5 lines, link to a doc or open a thread for discussion.
- Never accuse intent ("you didn't think about…"). Talk about the **code**, not the **author**.

### 7. Submit the review (single batched call)

Use the `POST /reviews` endpoint with a `comments` array — this posts all inline comments **and** the summary atomically.

```bash
# Decide verdict based on findings:
#   Any Blocking → REQUEST_CHANGES
#   Only Suggestion/Nit/Question → COMMENT
#   Nothing notable → APPROVE
VERDICT="COMMENT"   # or REQUEST_CHANGES / APPROVE

# Summary body — use the template in §7a below
SUMMARY=$(cat workspace/tmp/pr_${PR}_review/summary.md)

# Build the payload (jq composes inline comments + summary)
jq -n \
  --arg commit_id "$HEAD_SHA" \
  --arg event "$VERDICT" \
  --arg body "$SUMMARY" \
  --slurpfile comments workspace/tmp/pr_${PR}_review/comments.json \
  '{commit_id:$commit_id, event:$event, body:$body, comments:$comments[0]}' \
  > workspace/tmp/pr_${PR}_review/payload.json

gh api --method POST "repos/$REPO/pulls/$PR/reviews" \
  --input workspace/tmp/pr_${PR}_review/payload.json
```

> ⚠️ GitHub rejects a `REQUEST_CHANGES` review if the PR author is the same as the reviewer. The bot account **cannot** request changes on its own PRs — fall back to `COMMENT` in that case (this should be rare since you already checked author in step 1).

#### 7a. Summary template

```markdown
## Code Review — PR #<n>

**Verdict:** <APPROVE | COMMENT | REQUEST_CHANGES>
**Scope reviewed:** <X> files, +<A> / -<D> lines
**CI:** <green | failing: <which checks>>

### Summary
<2–4 sentences: what the PR does and the overall assessment.>

### Blocking (must fix before merge)
- `path/to/file.py:42` — short title (see inline)
- …

### Suggestions (should fix)
- `path/to/file.py:88` — short title (see inline)
- …

### Nits / Questions
- …

### Out of scope (follow-up)
- <bullet list of things to track in a separate ticket>
```

Keep the summary skimmable — the inline comments carry the detail.

### 8. Final report to the user

Return a concise markdown summary to the chat:

```markdown
## Reviewed PR #<n> — <verdict>

- **Files reviewed:** <X> (+<A>/-<D>)
- **Findings:** <M> blocking, <S> suggestions, <N> nits
- **CI status:** <green/failing>
- **Review URL:** <https://github.com/.../pull/N#pullrequestreview-...>

Top concerns:
1. <one-liner>
2. <one-liner>
```

---

## Common Pitfalls

| Pitfall | Correct approach |
|---|---|
| Posting each inline comment as its own review | Batch into one review via `POST /reviews` with a `comments` array — one notification, one thread. |
| Forgetting `commit_id` (head SHA) | Required by the inline-comment API; resolve it once with `gh api repos/.../pulls/$PR --jq .head.sha`. |
| Anchoring comments to the wrong side of the diff | Use `"side": "RIGHT"` for new code (the common case). `LEFT` is for commenting on removed lines. |
| Reviewing without reading `AGENTS.md` / `CLAUDE.md` | Feedback that contradicts the repo's documented conventions wastes the author's time and ours — read these first, every time. |
| Re-stating what CodeRabbit / Copilot / another reviewer already said | Skip or briefly `+1`; don't pile on. |
| Flagging code outside the diff | Out of scope. Open a follow-up ticket instead. |
| Mixing personal style with real findings | Tag style stuff `**Nit:**` so the author can ignore safely. |
| `REQUEST_CHANGES` for nitpicks | Reserve for true blockers — correctness, security, data integrity, or untested critical paths. |
| `REQUEST_CHANGES` on your own PR | GitHub rejects this. Fall back to `COMMENT`; usually means the author check in step 1 was skipped. |
| Reviewing a draft PR without flagging that it's a draft | The author may not be done — call it out in the summary, keep findings preliminary. |
| Checking out the branch when not needed | Read-only API access is enough for static review; only check out if you actually need to run code. |
| Pushing commits during a review | Never. Reviews are read-only. If a fix is trivial and the user asks for it, switch to `pr_code_review_fix.md`. |
| Vague comments ("this could be better") | Always include a concrete fix or suggestion block. |

---

## Quick Reference — API Endpoints

| Purpose | Endpoint |
|---|---|
| PR metadata | `GET /repos/{owner}/{repo}/pulls/{pr}` |
| Unified diff | `gh pr diff {pr} --repo {owner/repo}` |
| Files in PR | `GET /repos/{owner}/{repo}/pulls/{pr}/files` |
| Commits in PR | `GET /repos/{owner}/{repo}/pulls/{pr}/commits` |
| CI status | `gh pr checks {pr} --repo {owner/repo}` |
| Existing reviews | `GET /repos/{owner}/{repo}/pulls/{pr}/reviews` |
| Existing inline comments | `GET /repos/{owner}/{repo}/pulls/{pr}/comments` |
| Existing issue comments | `GET /repos/{owner}/{repo}/issues/{pr}/comments` |
| **Submit a review** (batched) | `POST /repos/{owner}/{repo}/pulls/{pr}/reviews` with `{commit_id, event, body, comments[]}` |
| Single inline comment (rarely needed) | `POST /repos/{owner}/{repo}/pulls/{pr}/comments` |

---

## Related Skills

- `workspace/dev-knowledge/skills/MUST_READ.md` — branch / commit / **identity** rules (the review must be posted from the agent identity)
- `workspace/dev-knowledge/skills/pr_code_review_fix.md` — the inverse skill: addressing review feedback on the agent's own PR
- `workspace/dev-knowledge/skills/pr_title_description.md` — title/description conventions; useful for evaluating whether the PR's metadata matches its diff
- `workspace/dev-knowledge/skills/known_repos.md` — repo paths, integration branches, tech stack — required context for accurate feedback
- `workspace/dev-knowledge/skills/code_comment_style.md` — style rules to enforce when reviewing in-code comments
- `workspace/dev-knowledge/skills/planning_workflow.md` — for very large PRs (>30 files), persist a review plan instead of holding it in chat
