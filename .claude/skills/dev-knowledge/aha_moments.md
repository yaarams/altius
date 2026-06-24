# 💡 AHA Moments — Append-Only Capture Protocol

This skill defines how every contributor (agent or human) captures point-in-time insights so the rest of the fleet benefits from them. The protocol is **append-only**: each AHA is its own immutable file. There is no "latest AHAs" log to edit and no shared scroll to append to.

> See `skills/MUST_READ.md` §9 for the executive summary. This file is the deep dive.

---

## 1. What is an AHA?

An AHA is a **point-in-time discovery** — something you didn't know an hour ago, that surprised you, that another contributor would benefit from. Examples:

- *"`fnmatch` doesn't make `**` recursive across `/` — you need `glob.glob` or a hand-rolled regex."*
- *"Branch protection rulesets in GitHub are an org-level construct; the per-repo `branches/<x>/protection` API returns 404 even when protection is in force."*
- *"`gh repo clone` will embed a PAT in `origin` if `url.<pat>@github.com/.insteadof=https://github.com/` is set globally — the resulting URL is logged everywhere git logs."*
- *"EBS snapshots don't follow symlinks that point outside the snapshot scope."*

If you're tempted to write *"the rule is…"* or *"the lesson is…"*, you're looking at a **lesson** (long-lived, evolving) — see §6 below. AHAs are dated, immutable discoveries.

Trigger phrases that signal an AHA is forming:

- "Oh, *that's* why…"
- "So the trick is…"
- "It works because…"
- "I was wrong about X, the actual behaviour is Y"
- "After three hours, I finally figured out…"

Capture **immediately**. Don't wait until end-of-task — the nuance fades fast.

---

## 2. The helper does the work

```bash
bash workspace/dev-knowledge/scripts/contribute_aha.sh "<slug>"
```

The helper:

1. Branches from a freshly pulled `main` as `chore/main/<YYYY-MM-DD>-aha-<slug>`.
2. Creates `memory/aha/<UTC-iso-no-dashes>__<gh-actor>__<slug>.md` with the template (see §3).
3. Opens the file in `$EDITOR` (humans) or expects the agent to fill it in via `xpworkspace-file-write` (agents).
4. Runs `python3 scripts/scrub.py memory/aha/<file>` before commit.
5. Commits as `chore(DK-<YYYY-MM-DD>): aha — <slug>`.
6. Pushes the branch.
7. Opens a PR via `gh pr create` against `main`.

**Don't hand-roll.** The helper guarantees the filename pattern, the scrub gate, the branch + commit format, and the PR shape. Hand-rolled AHAs slip through these gates and the indexes break.

---

## 3. AHA file template

The helper writes this skeleton; you fill it in.

```markdown
# AHA: <Short imperative title>

- **Date (UTC)**: 2026-05-14T09:38:00Z
- **Actor**: xpander-fullstack-generalist
- **Slug**: fnmatch-doublestar
- **Supersedes**: _(optional path to previous AHA this corrects)_

## Context

What were you doing? Be concrete — task, tool, repo, ticket if any.

## What I discovered

One or two paragraphs. State the observation precisely. Include the exact command output / API response / file path that made it click, if useful.

## Why it matters

What will change in how you (or any future contributor) approach similar problems. Be specific about the *next time someone does X*.

## Rule (optional)

A single actionable line, distilled.

## References

- Links to docs, source files, PRs, tickets that ground the discovery.
```

### Tone

- Write for two audiences: a new agent reading this in six months, and a human developer joining the team next quarter.
- Concrete > abstract. Include the exact command, the exact error, the exact path.
- No hedging ("maybe", "I think") — if you're not sure, capture it as a question in `memory/notes/` instead.

---

## 4. Filename and immutability

- Filename: `memory/aha/<UTC-iso>__<gh-actor>__<slug>.md`
  - UTC ISO with no dashes/colons: `20260514T093800Z`
  - `<gh-actor>` is the `gh auth status` active account (e.g. `xpander-fullstack-generalist`)
  - `<slug>` is `kebab-case`, max ~6 words.
- **Once merged, the file is immutable.** To correct, write a *new* AHA with `Supersedes:` pointing to the original. Both files remain.
- Don't edit existing AHAs after merge. Don't rename. Don't delete. The append-only invariant is what makes the corpus trustworthy.

---

## 5. The INDEX is CI-generated

`memory/aha/INDEX.md` is regenerated on every push to `main` by `.github/workflows/rebuild-indexes.yml` (running as `github-actions[bot]`). The workflow calls `scripts/rebuild_aha_index.sh`, which scans `memory/aha/*.md`, sorts by timestamp, and produces a table grouped by month.

- **Don't hand-edit `INDEX.md`.** A merge to `main` will revert your edits on the next rebuild.
- If the index is wrong (missing entries, broken links), fix `scripts/rebuild_aha_index.sh` via `propose_change.sh`. The fix lands; the index regenerates.

---

## 6. AHA vs. lesson vs. note vs. ADR — routing

| You have | Destination | Helper |
| --- | --- | --- |
| A dated, surprising discovery you want frozen in time | `memory/aha/` | `contribute_aha.sh` |
| A long-lived rule that evolves with experience | `memory/lessons/lessons_learned.md` | `propose_change.sh` |
| A neutral technical note / runbook / fix recipe | `memory/notes/` | `propose_change.sh` |
| An architectural decision (what we chose and why) | `memory/decisions/ADR-NNNN-<slug>.md` | `new_decision.sh` |
| A repo-specific fact (integration branch, stack) | `skills/known_repos.md` | `propose_change.sh` |
| A new reusable capability (procedure, recipe) | `skills/<topic>.md` | `propose_change.sh` |

If in doubt: AHAs are **discoveries**, lessons are **rules**, ADRs are **decisions**, notes are **facts**, skills are **procedures**.

---

## 7. Reasoning before writing

Before you invoke `contribute_aha.sh`, briefly think through:

1. **What exactly did I discover?** (Specific. Reproducible.)
2. **Is this dated, or is it a long-lived rule?** (Dated → AHA. Rule → lesson.)
3. **Would I have benefited from knowing this at the start of the task?** (Yes → high signal, capture.)
4. **Does it contradict an existing AHA?** (Yes → write a new AHA with `Supersedes:` link. Don't edit the old.)
5. **What's the smallest slug that names it?** (`fnmatch-doublestar`, not `the-fnmatch-double-star-bug-i-hit-today`.)

---

## 8. Anti-patterns

- ❌ Editing an existing AHA after merge — break the immutability invariant.
- ❌ Hand-editing `INDEX.md` — CI will revert you.
- ❌ Capturing vague insights (*"things can be tricky"*) — be specific or don't capture.
- ❌ Waiting until end-of-task — nuance fades.
- ❌ Saving secrets / tokens / PATs in an AHA — scrub CI will block, and once it's in git history it's leaked. Redact before writing.
- ❌ Duplicating an existing AHA — search `memory/aha/` first (`grep -rli <topic> memory/aha/`).
- ❌ Writing AHAs for trivia (*"I learned `ls -la` shows hidden files"*) — only capture things another contributor wouldn't know.
- ❌ Putting AHAs in `workspace/local/notes/` — that's local-only; the fleet won't see it.

---

## 9. Examples to read

Browse `memory/aha/INDEX.md` for recent captures. Good models early in the corpus:

- `20260514T*__xpander-fullstack-generalist__ebs-symlinks-not-persisted.md` (planned)
- `20260514T*__xpander-fullstack-generalist__gh-clone-pat-leak.md` (planned)
- `20260514T*__xpander-fullstack-generalist__fnmatch-doublestar.md` (planned)
- `20260514T*__xpander-fullstack-generalist__scrub-regex-tuning.md` (planned)

These will be filed as part of plan item *Capture AHAs from this migration*.

---

## 10. Cross-references

- `skills/MUST_READ.md` — the overall playbook (this skill is referenced from §9).
- `scripts/contribute_aha.sh` — the helper that creates AHA files.
- `scripts/rebuild_aha_index.sh` — the index regenerator (runs in CI).
- `.github/workflows/rebuild-indexes.yml` — the post-merge workflow.
- `memory/lessons/lessons_learned.md` — where long-lived rules live (cousin of AHAs).
- `memory/decisions/INDEX.md` — ADRs (the *why* behind big choices).
