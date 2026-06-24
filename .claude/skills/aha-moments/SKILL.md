---
name: aha-moments
description: >
  Capture "aha moments" — non-obvious insights, gotchas, conventions, or decisions Claude learns
  during a conversation — and offer to persist them to a knowledge-base markdown file.
  Use this skill proactively whenever Claude discovers something worth remembering that is NOT
  already obvious from the code: a surprising bug root cause, a hidden constraint, a project-specific
  convention, an undocumented API quirk, a user preference, a decision and its reasoning, or a
  recurring pitfall. Also use when the user says "aha", "good to know", "remember this", "save this",
  "/aha", "capture this", or "note that". Do NOT use for trivial facts derivable from reading code.
---

# Aha Moments — Capture Insights to KB

Detect insight → summarize → ask user → save to markdown file.

## When to trigger (proactive)

Fire when one of these happens in conversation:

- **Root cause found** for a non-trivial bug (not just "typo fixed").
- **Hidden constraint** discovered (e.g. "this API requires query param X, not body").
- **Convention learned** that is not in CLAUDE.md / AGENTS.md (e.g. "we always use parseFloat here because…").
- **Decision + reasoning** the user states (e.g. "we picked Cal.com over Stigg because PLG deprecated").
- **Recurring pitfall** ("third time this week the same import broke X").
- **User preference** that goes beyond style ("I want PRs split, not bundled, for this module").
- User explicitly says: "aha", "remember", "save this", "note this", "good catch".

Skip if:

- Info is already in CLAUDE.md / AGENTS.md / existing memory files.
- It's a one-off ephemeral task detail.
- It's pure code state derivable from `git log` or file read.
- It's already covered by auto-memory (user/feedback/project/reference types) — in that case prefer auto-memory.

## Flow

### Step 1 — Detect & summarize

When triggered, pause current work and surface the insight. One short paragraph:

```
💡 Aha moment: <one-line title>

<2-4 sentences: what was learned + why it matters + where it applies>
```

### Step 2 — Ask user (single question)

Ask using AskUserQuestion with these options:

- **Save to existing KB file** (show suggested file based on topic — see Step 3)
- **Save to new file** (suggest filename, kebab-case)
- **Skip** (don't save)
- **Edit before saving** (let user refine wording)

Header chip: "Save aha?"

### Step 3 — Pick destination

Default KB root: `~/.claude/projects/<project-slug>/memory/` (auto-memory dir) for cross-session knowledge, OR `<repo>/docs/kb/` if user prefers repo-local.

Ask user once per session which root they prefer; remember choice for rest of session.

Suggest filename based on topic:
- Bug pattern → `gotcha_<area>.md`
- Convention → `convention_<area>.md`
- Decision → `decision_<topic>.md`
- API quirk → `api_<service>.md`

If saving to auto-memory dir, follow auto-memory format (frontmatter with `name`, `description`, `metadata.type`) and add a line to `MEMORY.md` index.

If saving to repo `docs/kb/`, use plain markdown with `# Title` + `## Context` + `## Insight` + `## Applies to` sections.

### Step 4 — Write & confirm

Append to existing file (under a new `## <date> — <title>` heading) or create new file. Then one-line confirmation:

```
✓ Saved → <relative path>
```

Return to prior task.

## Format templates

### Auto-memory entry (cross-session)

```markdown
---
name: <kebab-slug>
description: <one-line, specific>
metadata:
  type: project | feedback | reference | user
---

<insight body>

**Why:** <reason / incident>
**How to apply:** <when this rule kicks in>
```

### Repo KB entry (project-local)

```markdown
## <YYYY-MM-DD> — <title>

**Context:** <what we were doing>
**Insight:** <what was learned>
**Applies to:** <files / area / situation>
**Source:** <commit, PR, or conversation date>
```

## Rules

- One aha per prompt. Don't batch multiple insights — ask separately.
- Never save without user approval. Default = skip if no answer.
- Keep entries short. If body > 10 lines, summarize.
- Link related entries with `[[name]]` (auto-memory) or relative path (repo KB).
- If insight contradicts existing entry, offer to **update** that entry instead of creating new one.
- Don't trigger more than ~3 times per session unless user invites more.
