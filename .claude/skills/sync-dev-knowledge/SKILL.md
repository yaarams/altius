---
name: sync-dev-knowledge
description: Use when user asks to sync, pull, load, install, or onboard xpander dev-knowledge (cortex) for Claude Code. Triggers on "sync dev-knowledge", "install cortex", "onboard claude code to cortex", "pull dev-knowledge", "/sync-dev-knowledge", or at session start for xpander work.
---

# sync-dev-knowledge — xpander.ai cortex onboarding

You are being installed as contributor to **xpander.ai shared cortex** — team live brain of skills, AHAs, ADRs, lessons. Shared by humans + AI dev-agents.

REPO: https://github.com/xpander-ai/dev-knowledge

Cortex is **live source of truth**. Do NOT mirror into local Claude memory. Read from repo. Pull often.

## STEP 1 — Local checkout

Clone target: `~/dev/dev-knowledge` (or convenient path).

```bash
REPO=~/dev/dev-knowledge
REMOTE=git@github.com:xpander-ai/dev-knowledge.git
if [ ! -d "$REPO/.git" ]; then
  mkdir -p "$(dirname "$REPO")"
  git clone "$REMOTE" "$REPO"
fi
```

**Forbidden:**
- `scripts/bootstrap.sh` — touches git identity, sandbox-only.
- Modify git config, gh auth, credentials, remote URLs.

## STEP 2 — Treat cortex as live source, not snapshot

Session start for xpander work:

```bash
cd ~/dev/dev-knowledge && git pull --ff-only origin main
```

Need rule/AHA/ADR → read file from repo. Do NOT copy contents into `~/.claude` memory. Mirrors go stale, drift from main, duplicate cortex.

## STEP 3 — What goes in local Claude memory

Only persistent pointers + user-specific context. Max ~5 short files under `~/.claude/projects/<encoded-cortex-path>/memory/` with `MEMORY.md` index. Save:

- User is cortex contributor.
- Local clone path: `~/dev/dev-knowledge`.
- Rule: pull on session start, read live, never mirror.
- Rule: contribute via helper scripts, never hand-roll.
- Forbidden: `bootstrap.sh`, git config edits, INDEX hand-edits, committing secrets.

Anything beyond → cortex itself, not memory.

## STEP 4 — First-install read order (one-time)

End-to-end once, then re-read on demand:

1. `README.md`
2. `AGENTS.md`
3. `skills/MUST_READ.md`
4. `skills/known_repos.md`
5. `ls skills/` (scan titles)
6. `memory/aha/INDEX.md`
7. `memory/decisions/INDEX.md`
8. `memory/lessons/lessons_learned.md`

## STEP 5 — Content types + append-only rules

| Path | Type | Mutability |
|------|------|------------|
| `skills/` | reusable how-to + conventions | editable, versioned |
| `memory/aha/` | one file per insight | **append-only**, immutable post-merge |
| `memory/decisions/` | ADRs (Michael Nygard fmt), numbered | **append-only**, immutable |
| `memory/lessons/`, `memory/notes/` | long-form | editable |

Append-only = never edit existing AHA/ADR. Write new one superseding old.

## STEP 6 — Contribute back

All writes = PRs to main. **Always helpers, never hand-roll:**

```bash
scripts/contribute_aha.sh "<slug>"            # non-obvious insight
scripts/new_decision.sh "<title>"             # architectural call
scripts/propose_change.sh "<slug>" "<msg>"    # edit skill/lesson/note
```

AHA flow = two-step:
1. Run once → scaffold + open `$EDITOR`. Fill bullets: Context / What I learned / Why it matters / Rule / References.
2. Re-run with `EDITOR_DONE=1` → regen INDEX, scrub, branch, commit, push, open PR.

Branch: `chore/main/<YYYY-MM-DD>-<slug>`
Commit: `chore(DK-<YYYY-MM-DD>): <tag> — <message>` (real em-dash —)
Tag ∈ `aha | adr | lesson | skill | note | infra`

INDEX files regenerated inline by helpers per ADR-0003. **Never hand-edit.**

**Contribute when:**
- Learned something non-obvious another contributor benefits from.
- Made architectural call worth recording.
- Skill/lesson out of date, can fix.

**Don't contribute:**
- Per-task scratch, ticket-scoped context, in-progress plans.
- Secrets, `.env`, tokens, keys. CI scrub gate rejects.

Rule of thumb: another contributor (human or agent) benefits tomorrow → cortex. Else local.

## STEP 7 — Hello-world AHA

Exercise full flow once:

```bash
scripts/contribute_aha.sh "hello-from-<your-firstname>"
# fill bullets honestly, save, exit
EDITOR_DONE=1 scripts/contribute_aha.sh "hello-from-<your-firstname>"
```

Verify PR diff = INDEX update + new file. CI green → self-merge (squash). Installed.

## STEP 8 — Steady state

- Session start in xpander work → pull cortex.
- Need rule → read from repo, not memory.
- Learned something → AHA via helper.
- Architectural call → ADR via helper.
- Edit existing skill/lesson → `propose_change` helper.
- Stop. Wait for actual task.
