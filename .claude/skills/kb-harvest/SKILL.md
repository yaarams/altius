---
name: kb-harvest
description: >
  One-shot retrospective. Scan a finished PR, a range of commits, or the current conversation session,
  extract every non-obvious insight worth remembering (gotchas, conventions, decisions, hidden constraints,
  API quirks, recurring pitfalls, user preferences), and present them as a batched list of suggested KB
  updates the user can accept/reject/edit in bulk. Use when the user says "harvest kb", "kb harvest",
  "/kb-harvest", "review session for KB", "extract learnings from PR <num>", "what should we remember
  from this", "summarize aha moments", "kb from commits", or finishes a feature and wants a retro.
  Differs from aha-moments: aha-moments fires per-insight in real time, kb-harvest runs once over a
  finished body of work.
---

# KB Harvest — Batched Retro KB Extraction

One pass over PR / commits / session → batched list of candidate KB entries → user approves/edits in bulk → write all approved.

## Step 1 — Determine source

Ask user (single AskUserQuestion) only if not already specified:

- **PR** — `gh pr view <num>` + `gh pr diff <num>` + commits
- **Commit range** — `git log <from>..<to>` + `git diff <from>..<to>`
- **Current branch vs main** — default for "harvest this branch"
- **Conversation session** — scan visible transcript for insights
- **Specific files** — user-supplied list

If user invocation already names a source ("harvest PR 1234", "harvest this session"), skip the question.

## Step 2 — Gather raw material

Based on source:

```bash
# PR
gh pr view <num> --json title,body,commits,files
gh pr diff <num>
gh api repos/{owner}/{repo}/pulls/<num>/comments  # review threads
gh api repos/{owner}/{repo}/issues/<num>/comments # discussion

# Commit range
git log <range> --pretty=format:"%h %s%n%b"
git diff <range> --stat
git diff <range>

# Current branch
git log $(git merge-base HEAD develop)..HEAD
git diff $(git merge-base HEAD develop)..HEAD

# Session — re-read transcript context already loaded
```

For session source: scan the conversation for user corrections, "no don't", "yes exactly", root-cause findings, decisions, surprise moments.

## Step 3 — Extract candidates

Apply these filters. Each candidate must pass ALL:

1. **Non-obvious** — can't be derived from reading current code alone.
2. **Reusable** — applies beyond this single PR/task.
3. **Not duplicate** — check existing KB files first (see Step 4).
4. **Has a "why"** — reason, incident, or constraint behind it.

Categories to look for:

- **Root cause** — bug fix where the cause was surprising (cite commit/file)
- **Hidden constraint** — API requires X, schema enforces Y, race condition Z
- **Convention** — "always use parseFloat", "RHF panels never call updateAgent directly"
- **Decision + reason** — chose A over B because…
- **Pitfall** — recurring mistake worth flagging
- **User preference** — workflow choice user confirmed
- **Reference** — external system pointer (dashboard URL, Linear project)

Skip:

- Pure code state (file paths, function names) — `git log` is authoritative
- One-off task details
- Already documented in CLAUDE.md / AGENTS.md
- Style nits

## Step 4 — Check existing KB

Before listing candidates, read:

- `~/.claude/projects/<project>/memory/MEMORY.md` (auto-memory index)
- `<repo>/docs/kb/` if exists
- `CLAUDE.md` / `AGENTS.md` for already-documented rules

For each candidate, mark:
- 🆕 new entry
- ✏️ update existing — name the file
- ⏭️ skip — already covered (don't show unless user asks for full list)

## Step 5 — Present batched list

Single message. Format:

```
🌾 KB Harvest — <source label> — <N> candidates

1. 🆕 [convention] RHF panels never call updateAgent directly from onChange
   Why: bypasses dirty-tracking + staged-version flows
   Source: PR #2424, AgentSettingsPanel.tsx
   → suggest: convention_rhf_panels.md (auto-memory, type: feedback)

2. ✏️ [api] Custom connector OAuth2 needs serviceVersion in vault key
   Update existing: project_oauth2_vault_flow.md
   Diff: add note about srvurl fallback for legacy connectors
   Source: commit 254b4d771

3. 🆕 [pitfall] pnpm scripts append args to last shell command
   Why: `pnpm compile --project X` ran `rm -rf X` and nuked dir
   Source: AGENTS.md already has it — ⏭️ skip

… (etc)
```

## Step 6 — Single bulk decision

AskUserQuestion (multiSelect):

- Header: "KB harvest"
- Question: "Which entries to save?"
- Options: one per candidate ("Save #1", "Save #2", …) + "Save all" + "Edit before saving" + "Skip all"

Cap at 4 options per Ask — if more candidates, ask in groups OR present numbered list and let user reply with numbers ("save 1,3,4").

For "Edit before saving": let user provide quick corrections per entry, then re-show list.

## Step 7 — Write approved entries

For each approved entry:

- **Auto-memory destination**: write `<slug>.md` in `~/.claude/projects/<project-slug>/memory/` with required frontmatter (`name`, `description`, `metadata.type`). Append one-line pointer to `MEMORY.md`.
- **Repo destination**: append section to existing file or create new file in `<repo>/docs/kb/` (or `<repo>/.claude/kb/`).

Use auto-memory format from `aha-moments` skill for cross-session entries; use repo KB format for project-local.

## Step 8 — Summary

One line per saved entry:

```
✓ Saved 4/7 entries:
  → memory/convention_rhf_panels.md (new)
  → memory/project_oauth2_vault_flow.md (updated)
  → memory/decision_plg_to_cal.md (new)
  → memory/api_pnpm_args.md (new)
Skipped 3 (already covered or user declined).
```

## Rules

- One harvest per invocation. Don't auto-rerun.
- Default scope when ambiguous: current branch vs `develop`.
- Cap candidates shown at 15. If more, ask user to narrow scope.
- Never write without explicit approval per entry (or "save all").
- Always cite source (commit SHA, PR#, file, conversation timestamp) in the entry body.
- If session source and transcript empty/short — say so, don't fabricate.
- Related entries → link with `[[name]]`.
- For PR source, also surface anything from review-thread comments that reads like a lesson.
