# MUST_READ — The Dev Knowledge Playbook

This repo (`xpander-ai/dev-knowledge`) is the **shared brain** for every xpander.ai engineering contributor — AI coding agents and human developers alike. If you are about to work on an xpander.ai task, READ THIS FILE FIRST. Every other skill, AHA, ADR, and lesson in this repo assumes you have internalised the rules below.

> This file is canonical. Local sandboxes have a thin `workspace/local/MUST_READ.local.md` bootloader that points here; do not duplicate rules there.

---

## 0. Audience — who this repo serves

Two audiences contribute to and consume this repo:

1. **AI coding agents** running inside xpander.ai sandboxes (Gilfoyle and siblings). They share the bot identity `xpander-fullstack-generalist <ai_employee_2@xpander.ai>` and push branches under that name.
2. **Human xpander.ai developers** who read skills, AHAs, and ADRs to learn how the fleet operates, and who occasionally contribute their own.

Every piece of content in this repo MUST be useful and intelligible to both audiences. Write skills, AHAs, and ADRs as if a brand-new agent and a brand-new human will both read them tomorrow.

## 1. The canonical layout

```
xpander-ai/dev-knowledge/
├─ AGENTS.md             # repo-level rules for agents (read on entry)
├─ CONTRIBUTING.md       # how to open a PR here (humans + agents)
├─ README.md
├─ .github/              # PR template, scrub CI, index-rebuild CI
├─ scripts/              # scrub, bootstrap, migrate, contribute_aha, new_decision, propose_change, rebuild_aha_index
├─ skills/               # canonical agent skills (this file + siblings)
│  ├─ MUST_READ.md
│  ├─ aha_moments.md
│  ├─ known_repos.md
│  ├─ codex/             # codex-runner architecture + helpers
│  └─ …                 # one .md per capability
└─ memory/
   ├─ aha/               # append-only AHA captures: <UTC-ts>__<actor>__<slug>.md + INDEX.md
   ├─ decisions/         # ADRs: ADR-NNNN-<slug>.md (Michael Nygard) + INDEX.md
   ├─ lessons/           # lessons_learned.md and other long-lived lessons
   └─ notes/             # general technical notes, runbooks, fixes
```

Local (per-sandbox) state is **never** in this repo. It lives in `workspace/local/`:
- `workspace/local/secrets/` — `.env`, tokens
- `workspace/local/plans/` — ticket-scoped plans (PRO-*.md)
- `workspace/local/notes/` — task-scoped scratch
- `workspace/local/codex-runs/` — ledger + per-run logs
- `workspace/local/design/` — design artifact cache
- `workspace/local/backups/` — `.bak` snapshots
- `workspace/local/MUST_READ.local.md` — thin bootloader
- `workspace/local/agent_identity.local.md` — this instance's identity hints

Rule of thumb: **if another contributor (agent or human) could benefit from it, it goes in the repo. If it's your scratch pad or credentials, it stays local.**

---

## 2. Boot sequence — every task, every session

Whether you are an agent or a human:

1. **Pull latest** — `bash workspace/dev-knowledge/scripts/bootstrap.sh` (agents) or `cd workspace/dev-knowledge && git pull --ff-only` (humans). Always start from a current `main`.
2. **Read `skills/MUST_READ.md` (this file) end-to-end.** No skimming.
3. **Read `skills/known_repos.md`** to learn which repos live in `/agent/data/dev` and their integration branches.
4. **Check the task queue** (agents only — see `skills/task_queue.md`). Humans don't have it; agents must respect single-task-in-progress invariant.
5. **Read every skill relevant to the task** in full — see Skill Lookup rules in §10.
6. If you discover an `AGENTS.md` / `CLAUDE.md` in another repo, read that too — see §12.

---

## 3. Contributing to this repo — the protocol

**Nobody pushes to `main` directly.** Branch protection enforces this for everyone (agents and humans). Every change is a PR. Squash-merge only. CI scrub must pass.

### 3.1 Use the helpers

Three scripts under `scripts/` cover 90% of contributions — use them, do not hand-roll:

| Helper | When | What it does |
| --- | --- | --- |
| `scripts/contribute_aha.sh` | You learned something non-obvious | Creates `memory/aha/<UTC-ts>__<actor>__<slug>.md`, runs scrub, commits, pushes, opens PR. |
| `scripts/new_decision.sh` | You're making an architectural decision | Creates `memory/decisions/ADR-NNNN-<slug>.md` with Michael Nygard template, branches, opens PR. |
| `scripts/propose_change.sh` | You're editing an existing skill / note / lesson | Branches, runs scrub on staged diff, commits, pushes, opens PR. |

All three:
- Branch from a freshly pulled `main`.
- Use branch name `chore/main/<YYYY-MM-DD>-<slug>`.
- Use commit format `chore(DK-<YYYY-MM-DD>): <tag> — <msg>` (em-dash, tags = `aha` | `adr` | `lesson` | `skill` | `note` | `infra`).
- Run `scripts/scrub.py` before commit; abort on secret/banned-identity match.
- Push and open a PR with `gh pr create`.

### 3.2 The append-only invariants

- **`memory/aha/`**: one file per AHA, filename includes UTC timestamp + actor + slug; the file is **immutable** once merged. Corrections come as a new AHA that supersedes the previous one (link back to it).
- **`memory/decisions/`**: one file per ADR, sequentially numbered `ADR-0001`, `ADR-0002`, … ; status field (`Proposed`/`Accepted`/`Superseded`) is the only thing that ever changes after merge.
- **`memory/aha/INDEX.md`** and **`memory/decisions/INDEX.md`** are regenerated by the post-merge `.github/workflows/rebuild-indexes.yml` workflow running as `github-actions[bot]`. **Never hand-edit indexes.** Helpers don't touch them.

### 3.3 Branch + commit conventions (this repo)

- Branch: `chore/main/<YYYY-MM-DD>-<slug>` (e.g. `chore/main/2026-05-14-aha-fnmatch-bug`).
- Commit subject: `chore(DK-<YYYY-MM-DD>): <tag> — <msg>`. Use a real em-dash (`—`, U+2014).
- Tags: `aha`, `adr`, `lesson`, `skill`, `note`, `infra`.
- Squash merge only. Don't merge merges.

### 3.4 Identity

- Agents: shared bot identity `xpander-fullstack-generalist <ai_employee_2@xpander.ai>` — allowlisted in `scripts/scrub.py`.
- Humans: your own `git config user.email` is fine — scrub allows any address that is NOT on the banned list (`+devagent@`, `+bot@`, `+agent@`, `noreply@`-style bots, or known leaked patterns).
- Co-author trailers are forbidden in this repo's commits.

---

## 4. Working in other xpander.ai repos (frontend, xpander-mono, xpander-sdk, …)

This section governs how you behave in the **product repos**, not in this one. The rules differ because each product repo has its own integration branch.

### 4.1 Branch + commit conventions (product repos)

- Branch: `{fix|feature|chore}/develop/<ticket-number>` (e.g. `feature/develop/PRO-1231`).
- Commit subject: `{fix|feat|chore}(<ticket-number>): explanation`.
- A ticket number is **always required**. No `NO-TICKET`. Ask the user if missing.
- Never push directly to `main` or `develop`. PRs only.
- Identity: same agent bot identity. No co-author trailers.

### 4.2 Choosing the right integration branch

See `skills/known_repos.md` for the authoritative table. As of writing:

- `frontend` → `develop`
- `xpander-mono` → `develop`
- `xpander-sdk` → `main`
- `docs` → see `known_repos.md`

> ⚠️ Never use `develop` in `xpander-sdk`. Never use `main` directly in `frontend` or `xpander-mono`.

### 4.3 Starting a new task — mandatory branch preparation

1. `git status` — if dirty, surface to the user and **ask** before stashing/committing/discarding. Never silently discard.
2. `git checkout <integration-branch>` (per `known_repos.md`).
3. `git pull origin <integration-branch>`.
4. Create the feature/fix/chore branch only after the above.

> Continuing an existing PR/branch? Skip the integration checkout, `git pull` the existing branch, and resume.

---

## 5. PR title + description

Before opening any PR (in this repo or any other xpander.ai repo):

1. **Verify `gh` CLI identity** — `gh auth status 2>&1 | grep -E 'Logged in|Active account'`. Active account MUST be `xpander-fullstack-generalist` for agent PRs. The git commit identity and `gh` auth identity are independent — both must be correct.
2. Read and apply `skills/pr_title_description.md`.

- Generate title + description from the **actual diff** (`git diff <base>...HEAD`) and commit messages — never assume.
- Description sections: **Purpose**, **Key changes**, **Notes**, **Testing**, **Follow-ups**.
- Screenshots section only if UI components or customer-facing APIs changed.

## 6. PR code review

Two skills cover the two directions — pick exactly one:

| Direction | Skill | Use when… |
| --- | --- | --- |
| Producing a review on someone else's PR | `skills/pr_code_review.md` | User asks to *review*, *check*, *approve* a PR. Read-only; inline + batched review. |
| Addressing a review on the agent's own PR | `skills/pr_code_review_fix.md` | User asks to *fix*, *address*, *resolve* feedback on an agent-authored PR. Pushes commits + per-thread replies. |

If the PR author is **not** `xpander-fullstack-generalist` and you're asked for feedback → `pr_code_review.md`.
If the PR author **is** `xpander-fullstack-generalist` and you're asked to address comments → `pr_code_review_fix.md`.
If unclear, ask the user.

Both skills require the `gh` identity check above.

## 7. Code comment style

Follow `skills/code_comment_style.md`:

- One-liners, intent-only.
- **No ticket numbers in source comments** — tickets belong in commit messages and PR descriptions.
- No history narration ("legacy…", "used to be…").
- Trim verbose pre-existing comments when you touch surrounding code.

## 8. Design system (mandatory for UI work)

Any UI change in `frontend` or any FE package under `xpander-mono` MUST follow `skills/xpander_design_system.md`:

- Use only existing tokens (CSS vars in `globals.css`) + Tailwind classes mapped from them. No raw hex, no arbitrary `bg-[#…]`, no inline `style={{…}}`.
- Use only existing shadcn primitives at `src/components/ui/` and only their `cva`-defined variants — read the file before guessing.
- Custom typography scale (`text-h1`/`h2`/`h3`, `text-body-*`). Never `text-sm`/`text-lg`/`text-xl`.
- Borders → `border-outline`. Layout gaps → `flex gap-*`, never `space-{x,y}-*`. Primary text → `text-gray-100`/`-200`, never `text-white`.
- **Approval gate**: real gap (no token / variant / primitive matches design) → STOP, ask user. Offer two closest existing options first. New tokens land in their own commit, both `:root` and `.dark`.
- **Do NOT use the Refero skill** (`skills/refero_design_styles.md`) on `frontend` or `xpander-mono`. Refero is greenfield-only.

---

## 9. AHAs and ADRs — the persistence layer

This is how the fleet's collective knowledge grows. Read `skills/aha_moments.md` for the full protocol — below is the executive summary.

### 9.1 AHAs (`memory/aha/`)

- Capture **immediately** when something non-obvious clicks. Don't wait for end of task.
- Use `scripts/contribute_aha.sh "<slug>"` — it does the file, branch, scrub, commit, PR.
- Filename: `<UTC-iso-no-dashes>__<gh-actor>__<slug>.md`, e.g. `20260514T093800Z__xpander-fullstack-generalist__fnmatch-doublestar.md`.
- Each AHA is **immutable** once merged. To correct, write a new AHA that links to and supersedes the original.
- Route long-lived lessons (not point-in-time discoveries) into `memory/lessons/lessons_learned.md` via `propose_change.sh` instead.

### 9.2 ADRs (`memory/decisions/`)

- Use `scripts/new_decision.sh "<slug>"` for architectural decisions.
- Sequentially numbered: `ADR-0001-<slug>.md`, `ADR-0002-…`.
- Michael Nygard template: **Context**, **Decision**, **Status**, **Consequences**.
- Once accepted, only `Status` changes (to `Superseded by ADR-NNNN`). Body is frozen.

### 9.3 Indexes are CI-generated

`memory/aha/INDEX.md` and `memory/decisions/INDEX.md` are regenerated post-merge by `.github/workflows/rebuild-indexes.yml`. They appear in `main` automatically. Don't edit them by hand — your commit will be reverted by the next rebuild.

## 10. Skill lookup — before every task

1. Read `skills/MUST_READ.md` (this file).
2. Read `skills/known_repos.md` always.
3. `ls skills/` to see what's available.
4. Read any skill relevant to your task **in full** before executing.
5. If a skill exists, follow it exactly; propose changes via `propose_change.sh` when behaviour shifts.
6. **Read every skill in FULL.** Skills are rules, not reference. The most critical content (validation steps, gotchas, anti-patterns) is usually at the bottom of the file, exactly where truncation cuts off.
   - Full file returned → good.
   - `[TRUNCATED OUTPUT]` marker referencing `CONTEXT_OPTIMIZATION/<uuid>.xp` → **immediately** call `xpworkspace-file-read` on that `.xp` path before doing anything else.
   - Tempted to skim? **Don't.** That's how rules get violated.
   - Large skills: paginate with `start_line`/`end_line` until you've read end-to-end.
   - Never use `cat`/`head`/`tail`/bash on `.xp` files — they return base64 ciphertext. Only `xpworkspace-file-read` decrypts them.
   - **Rule of thumb**: if you have not seen the final line of the skill file, you have not read the skill.

## 11. Task queue (agents only)

Agents must enforce single-task-in-progress — see `skills/task_queue.md`. Before reacting to any user request:

```sql
SELECT id, title, status, repo, branch, started_at, notes
FROM task_queue
WHERE status IN ('in_progress','blocked')
ORDER BY started_at DESC;
```

- If a task is `in_progress` and the new request is unrelated → **enqueue as `pending`**, tell the user, STOP. Don't start new work.
- If the new request is a continuation → append to `notes` and keep going.
- Only start new work when no `in_progress` row exists. The DB has a partial unique index that enforces this.
- Mark `completed` the instant work finishes; auto-pick next pending.
- For deferred / scheduled tasks: use `xpschedule-create`, store the returned id in the queue's `schedule_id` column.

Full schema, SQL recipes, queue commands (`show queue`, `cancel current`, `reset queue`, `bump <id>`, …) live in `skills/task_queue.md`.

Humans don't use the task queue — it's a single-agent-sandbox invariant. Humans coordinate through tickets and PRs as usual.

## 12. Repo-level AGENTS.md / CLAUDE.md

When entering any git repo — product repo, third-party, or this one — discover and read all `AGENTS.md` and `CLAUDE.md` files:

```bash
find . -type f \( -name "AGENTS.md" -o -name "CLAUDE.md" \) | sort
```

- Run before reading any other file or writing any code.
- Read **every** result. Root-level files set global conventions; nested files (e.g. `packages/api/AGENTS.md`) add package-specific guidance — nested rules are **additive** and may override root rules within that subdirectory.
- Apply all instructions throughout your session in that repo.
- If an `AGENTS.md` / `CLAUDE.md` conflicts with this MUST_READ, flag it and ask the user which takes precedence.
- If no such files exist, fall back to this file.

> `AGENTS.md` is to AI agents what `README.md` is to human developers. Never skip it.

## 13. Planning

For any non-trivial multi-step task, read and apply `skills/planning_workflow.md` before starting:

- Persist the plan as `workspace/local/plans/<TICKET-ID>.md` (one file per ticket).
- Mirror the plan into the runtime via `xpcreate_agent_plan`.
- Email the plan to the requesting user the moment planning is `ready` or after a major replan.
- Keep `Last updated`, `Decisions`, and `Next Action` current as work progresses.

Do NOT keep plans only in chat — they vanish after compaction.

## 14. Backups (product repos and local workspace)

In product repos, git is your backup. In `workspace/local/` (untracked by git), back up before destructive edits:

```bash
mkdir -p workspace/local/backups
ts=$(date -u +%Y%m%dT%H%M%SZ)
for f in <files-you-are-about-to-edit>; do
  cp "$f" "workspace/local/backups/$(basename "$f").${ts}.bak"
done
```

Inside this repo (`workspace/dev-knowledge/`), git history is the backup — no `.bak` files needed. Just branch and commit.

## 15. Rollback

If the multi-agent migration ever needs to be rolled back, see `memory/notes/rollback.md` (added in PR #8 of the bootstrap migration). The short version:

1. Stop bootstrap.sh by setting `DEV_KNOWLEDGE_DISABLE=1` in the sandbox env.
2. Restore `workspace/{skills,memory,context}` from the `workspace/tmp/pre-cutover-backup/*.tar.gz` tarball.
3. Re-point `MUST_READ.local.md` at the legacy paths.

Until PR #8 lands, the rollback runbook is captured here at a high level only.

---

## 16. Quick reference (cheat sheet)

| Need | Command / path |
| --- | --- |
| Pull latest knowledge | `bash workspace/dev-knowledge/scripts/bootstrap.sh` |
| Capture an AHA | `bash workspace/dev-knowledge/scripts/contribute_aha.sh "<slug>"` |
| Start an ADR | `bash workspace/dev-knowledge/scripts/new_decision.sh "<slug>"` |
| Edit a skill / note | `bash workspace/dev-knowledge/scripts/propose_change.sh "<slug>"` |
| Scrub a file before commit | `python3 scripts/scrub.py <file>` or `python3 scripts/scrub.py --all` |
| Find AHAs by topic | `grep -rli '<topic>' memory/aha/` |
| List ADRs | `cat memory/decisions/INDEX.md` |
| Check active task queue | `SELECT * FROM task_queue WHERE status='in_progress'` (agents only) |
| Check `gh` identity | `gh auth status` → expect `xpander-fullstack-generalist` |
| Check git identity | `git config user.name && git config user.email` |

---

## 17. When in doubt

- Read more, write less.
- A PR with two reviewers (human + scrub CI) is cheaper than a leaked secret.
- If a skill is unclear or wrong, fix it via `propose_change.sh` — don't work around it.
- If the helper scripts don't fit your case, ask Moriel before hand-rolling — the helpers exist to keep the repo's invariants intact.

> *This file is the contract. Every other skill, AHA, and ADR in this repo assumes you've read it. If you haven't, stop here and read it.*
