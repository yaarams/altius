# AI Agent Skill: Security GitHub Issue Lifecycle

## Goal

Keep upstream GitHub security issues (Trivy / Dependabot / Snyk / GHSA / IQ Server tickets that live as `xpander-ai/<repo>` GitHub issues) in sync with the actual fix work — from PR open to verified-and-closed — so the security backlog reflects reality.

This skill sits **next to** `security_vulnerability_fix.md`:
- `security_vulnerability_fix.md` → *how* to fix the CVE
- `security_github_issue_lifecycle.md` → *how to manage the upstream GitHub issue + paired Notion ticket* around that fix

---

## When to Use

Any time a security finding is tracked as a GitHub issue in an `xpander-ai/*` repo — e.g.:
- A Trivy bulk-scan run opened an auto-issue (`[trivy] <service> bulk-services — N CRITICAL`)
- A Dependabot/Snyk alert was promoted to an issue
- A manual security review filed an issue with `security`, `vulnerability`, or `cve` labels
- An IQ Server policy failure has a mirrored GitHub issue

Use alongside the matching Notion `SecurityVulnerability` ticket (e.g. `PRO-XXXX`).

---

## Lifecycle States

| Phase | GitHub issue | Notion `📍Priority` | PR |
|---|---|---|---|
| Triaged | Open, has `security` label | `P1` (or `Now` if blocking deploy) | — |
| Fix in flight | Open, comment links to draft/open PR | `P1` / `Now` | Open, draft/ready |
| Patch ready | Open, comment links to PR | `Validation` | Open, ready |
| Resolved | **Closed** as `completed`, comment links to fix PR | `Done` (after deploy) | Merged |
| Won’t fix / accepted risk | Closed as `not planned`, comment explains rationale | `Done` (or archived) | n/a |

> Close the GitHub issue as soon as the fix PR is opened (or merged) and the comment links it to the PR. We do **not** gate close on a scanner re-run — the next scheduled scan will confirm the fix on its own, and re-running on demand creates noise.

---

## Step-by-Step Workflow

### 1. Verify identities once per session
Follow `MUST_READ.md` §2a:
```bash
gh auth status 2>&1 | grep -E 'Logged in|Active account'
# Active account MUST be xpander-fullstack-generalist
```
Git commit identity: `xpander-fullstack-generalist <ai_employee_2@xpander.ai>`. No `Co-authored-by` trailers.

### 2. Confirm the GitHub issue + Notion ticket are linked
- Pull the GH issue body and any pinned comments to extract: image / package name, scanner run URL, CVE list, severity, fixed version.
- Confirm a Notion ticket exists with `Type = SecurityVulnerability` and a matching `userDefined:ID` (e.g. `PRO-1086`). If missing, create one before doing code work — Notion is the source of truth for prioritization.

### 3. Open the fix PR
Use `security_vulnerability_fix.md` for the actual change. PR title/body per `pr_title_description.md`.
Mandatory cross-references in the PR body:
- `Closes upstream issue #<N>` (or close the issue manually with a verification comment in step 7).
- Notion ticket ID + URL.
- Scanner run URL that flagged the CVE.
- Advisory link (NVD, Debian DSA, GHSA, etc.).

### 4. Comment on the GH issue when the PR opens
Keep it terse and machine-grep-friendly. Use `gh issue comment`:
```bash
gh issue comment <N> --repo xpander-ai/<repo> --body "\
Patch PR opened: #<PR> — \`<commit-subject>\`.

<one-line summary of the fix mechanism (e.g. apt-get upgrade pulls 3.5.5-1~deb13u2)>."
```
Before commenting, check for existing duplicates:
```bash
gh issue view <N> --repo xpander-ai/<repo> --json comments --jq '.comments[].author.login + ": " + (.comments[].body | split("\n")[0])'
```
Do NOT post repeated status updates — edit your previous comment with `gh issue comment <N> --edit-last` instead.

### 5. Update the Notion ticket
When the PR is open and waiting on validation:
- Move `📍Priority` → `Validation` (use `mcp_tool_notion-update-page` with `update_properties`).
- Add a comment / link to the PR using `mcp_tool_notion-create-comment` if the ticket has discussion enabled.
- If the PR description changes substantially (e.g. version bump dropped), keep the Notion ticket’s `## Next Action` aligned in `workspace/local/plans/<TICKET-ID>.md`.

### 6. Close the GH issue
Close as soon as the PR is open (or merged). Do **not** wait for a scanner re-run — the next scheduled scan will confirm the fix on its own.
```bash
gh issue close <N> --repo xpander-ai/<repo> --reason completed --comment "\
Resolved by #<PR>. <one-line fix summary referencing patched version / CVE list>."
```
- Use `--reason not planned` only when the team has explicitly accepted the risk — in that case the comment MUST cite the decision (Notion link, Slack thread).
- If the issue is already closed (auto-closed by `Closes #N` in the PR), still post the resolution comment so the audit trail is complete.

### 7. Move the Notion ticket to `Done`
- After the patched artifact is built and deployed, set `📍Priority` → `Done`.
- Update `workspace/local/plans/<TICKET-ID>.md` `## Status > State` to `done` and append a final entry to `## Decisions` with the PR + deploy reference.

---

## Hard Rules

- **Do not** trigger an on-demand scanner re-run to verify a security fix. Close the issue with a comment linking the PR; the next scheduled scan provides verification.
- **Never** post duplicate status comments — edit-last or skip.
- **Always** include the CVE list and patched-version ref in the close comment — grep-friendly for future audits.
- **Always** update the Notion priority in lockstep with the GH state transitions (`Validation` when the PR is open, `Done` once the patched artifact is deployed).

---

## Notion Priority Reference (Product and engineering board)

Valid `📍Priority` values for security tickets:
- `Backlog` — triaged but not scheduled
- `P2` / `P1` / `Now` — active work, increasing urgency
- `Validation` — fix merged, awaiting scanner re-run
- `Done` — verified clean by scanner

Use `mcp_tool_notion-update-page` with `update_properties` and exactly one of these strings (case-sensitive).

---

## Quick Command Snippets

List open security issues in a repo:
```bash
gh issue list --repo xpander-ai/<repo> --label security --state open --limit 50
```

Find the Trivy auto-issue for a service:
```bash
gh issue list --repo xpander-ai/xpander-mono --search '[trivy] <service> in:title' --state open
```

Dump issue + comments for triage:
```bash
gh issue view <N> --repo xpander-ai/<repo> --comments
```

Close with resolution comment (canonical form):
```bash
gh issue close <N> --repo xpander-ai/<repo> --reason completed --comment "\
Resolved by #<PR>. <fix summary — e.g. apt-get upgrade pulls openssl 3.5.5-1~deb13u2 on next build>."
```

---

## Cross-References

- Fix mechanics: `workspace/dev-knowledge/skills/security_vulnerability_fix.md`
- PR title/body: `workspace/dev-knowledge/skills/pr_title_description.md`
- Notion ticket creation: `workspace/dev-knowledge/skills/notion_ticket_creation.md`
- Planning persistence: `workspace/dev-knowledge/skills/planning_workflow.md`
- Branch / commit / identity rules: `workspace/dev-knowledge/skills/MUST_READ.md`
