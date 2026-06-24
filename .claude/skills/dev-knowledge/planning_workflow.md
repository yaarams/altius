# Skill: Planning Workflow — Per-Ticket Plan Files

## Goal

Whenever planning a non-trivial change (research, refactor, feature, fix), persist the plan as a **markdown file in the workspace** so it survives session compaction, can be shared with the user, and is reused if the task resumes. Always email the final plan to the requesting user when planning concludes.

---

## Trigger

Use this skill any time you:
- Build an execution plan with `xpcreate_agent_plan` for a multi-step task
- Are asked to “plan”, “design”, “scope”, “research and propose”, or “replan” something
- Need to capture an investigation/spec for an implementation that will follow in another session

---

## File Layout

| Path | Purpose |
|---|---|
| `workspace/local/plans/{TICKET-ID}.md` | One plan file per ticket. Living document — update as the plan evolves. |
| `workspace/local/plans/_unticketed/{slug}-{YYYYMMDD}.md` | Fallback when no ticket exists yet (rare — always ask for a ticket first). |

- **Ticket ID is mandatory** (per `MUST_READ.md`). Ask the user for one before writing the file when missing.
- File name must match the ticket exactly (e.g. `RDT-456.md`, `PRO-123.md`).
- Never put plan files in `workspace/tmp/` — plans are not disposable.

---

## Required Sections (in order)

Every plan file MUST contain these sections, even when terse:

```markdown
# {TICKET-ID}: {Short title}

## Status
- **State**: drafting | ready | in-progress | blocked | done
- **Owner**: {user / agent}
- **Created**: {YYYY-MM-DD}
- **Last updated**: {YYYY-MM-DD HH:MM Asia/Jerusalem}
- **Related PRs / branches**: …

## Context
Why this work exists. Link to the user request, prior threads, or upstream tickets. Include the **verbatim user ask** if it is short enough.

## Research / Findings
File paths, function names, services, and concrete behaviour observed in the codebase. Cite paths with line ranges (`services/x/y.py:120-180`) so the implementer can jump directly. Diagrams welcome.

## Proposed Plan
Numbered steps, each with:
- **What** — the change
- **Where** — exact files / modules
- **How** — function signatures, flags, or commands when known
- **Risks / unknowns** — what might break, what needs validation

## Out of Scope
Explicit list of things this plan does NOT cover. Prevents scope creep.

## Validation
How we’ll know it worked: tests to add/run, linters, manual checks, smoke tests, metrics.

## Rollout / Migration
Feature flags, env vars, backfills, ordering of merges across repos.

## Open Questions
Things still needing user input. Each question on its own line, each answered question moved to the **Decisions** section once resolved.

## Decisions
Timeline-ordered log of decisions: `YYYY-MM-DD — short reasoning`.

## Next Action
The single concrete next step (one tool call / file edit / question). Updated every time the plan progresses.
```

Keep prose tight — this file is for the next agent (or future-you). Bullets > paragraphs.

---

## Step-by-Step Execution

### 1. Confirm the ticket number
- Required. If missing, use `xpask_for_information` to request it before doing anything else.

### 2. Create / locate the plan file
```bash
mkdir -p workspace/local/plans
ls workspace/local/plans/{TICKET-ID}.md 2>/dev/null || echo "new plan"
```
- If the file exists, **update it in place** (don’t duplicate). Bump `Last updated`.
- If not, scaffold from the template above with `xpworkspace-file-write`.

### 3. Mirror the plan in the agent execution plan
For every numbered step in the markdown plan, also create a matching `xpcreate_agent_plan` task. Keep titles short (≤6 words) and stable so the file and the runtime plan stay aligned.

### 4. Research before implementation
- Inspect repos, services, and existing skills first.
- Capture findings under `## Research / Findings` with concrete paths.
- Update the plan as you learn — never silently change direction.

### 5. Track progress
- Update `## Status`, `## Decisions`, and `## Next Action` whenever something changes.
- When questions are raised, log them under `## Open Questions` with the date.
- When tasks are completed in code, append the PR / branch under `## Status > Related PRs / branches`.

### 6. Email the plan to the user (mandatory at end of planning)
- Use the assistant-facing email tool (`XpanderEmailServiceSendEmailWithHtmlOrTextContent`).
- **Recipient**: the user who requested the work (from the user details at the top of the task).
- **Subject**: `Plan ready — {TICKET-ID}: {short title}`
- **Body (HTML)**: include the rendered markdown of the plan (status, context, plan, validation, next action), plus a link/path to the workspace file.
- Send the moment the plan reaches `ready` (or after a major replan), not just when the whole task ends.

### 7. Keep plans alive across sessions
- Plans persist in `workspace/local/plans/`. On resume, re-read the relevant plan file before doing anything else.
- When work completes, set `## Status > State` to `done` and add a final entry to `## Decisions`. Do not delete the file — historical plans are valuable.

---

## Conventions Cross-Reference

- Branch / commit / PR rules: `MUST_READ.md`
- PR title & description from the diff: `pr_title_description.md`
- Workspace layout (skills / memory / context / tmp): `MUST_READ.md` §5
- Aha moments captured during planning: `aha_moments.md`

---

## Anti-Patterns (Don’t)

- Plans in chat only — they vanish after compaction.
- Multiple plan files for the same ticket — one file, updated.
- Plan files in `workspace/tmp/` — wrong location.
- Skipping the email step — the user must receive the plan when planning concludes.
- Vague steps (“fix it later”) — every step must specify Where + How.
- Forgetting to bump `Last updated` after edits.
