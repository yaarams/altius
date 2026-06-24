# AI Agent Skill: Security GitHub Issue Workflow

## Goal

When a security CVE / Trivy / IQ Server / Dependabot finding is tracked as a **GitHub issue** (and usually mirrored to a Notion ticket), drive it cleanly from triage through fix → PR → close → board update, in a way that is consistent with `security_vulnerability_fix.md`, `pr_title_description.md`, `notion_ticket_creation.md`, and `MUST_READ.md`.

This skill is the **process glue** — it does not replace the package-fix mechanics in `security_vulnerability_fix.md`; it tells you how the GH issue and Notion ticket flow alongside the code change.

---

## When to Use

Any task involving a security GitHub issue — e.g.:
- "Fix the openssl CVE flagged in xpander-mono#3745"
- "Trivy bulk scan filed N issues, work through them"
- "Patch IQ Server policy violation tracked in <repo>#<n>"
- "Resolve and close GH issue for CVE-XXXX-XXXXX"

If the finding is **only** in a scanner UI (no GH issue yet), open the issue first via the scanner workflow output, then follow this skill.

---

## Source-of-Truth Map

| Artifact | Lives in | Role |
|---|---|---|
| **CVE technical details** | NVD / Aqua / Debian DSA / GHSA | Authoritative description and patched versions |
| **GH issue** | `xpander-ai/<repo>` Issues | Tracks remediation progress, links Trivy run + PR |
| **Notion ticket** | Product & engineering board | Ownership, priority, status, sprint visibility |
| **PR** | `xpander-ai/<repo>` | The actual fix; references both the GH issue and Notion ticket ID |
| **Trivy / scanner workflow run** | `.github/workflows/trivy-scan-*.yml` | Validation — must report 0 CRITICAL on the new image |

Keep them in sync: every step below updates one or more of these.

---

## Standard Workflow

### 1. Triage the GH issue

```bash
gh issue view <n> --repo xpander-ai/<repo> --json title,body,labels,assignees,state
```

Extract:
- CVE ID(s) and CVSS score
- Affected image / package / service
- Current vs. patched version
- Linked Trivy / scanner run URL

Confirm the `gh` active account:

```bash
gh auth status 2>&1 | grep -E 'Logged in|Active account'
```

Must be `xpander-fullstack-generalist`. If not, fix per `MUST_READ.md` §2a before continuing.

### 2. Find or create the Notion ticket

- Search the Product & engineering board for the CVE / image name. Reuse if it exists.
- If missing, create per `notion_ticket_creation.md` with:
  - **Type** = `SecurityVulnerability`
  - **📍Priority** initial state = `P1` (CRITICAL) / `P2` (HIGH) / `Backlog` (MEDIUM–LOW)
  - **Assignee** = the person owning the service / repo (or self if owner-less)
  - **Name** = `\[Security\] Patch <image-or-package> — <N> <SEVERITY> CVEs (<short cause>)`
  - Body must reference the GH issue, the Trivy run URL, and the CVE table.
- Note the ticket ID (e.g. `PRO-1086`) — this becomes the branch / commit / PR prefix.
- **Immediately back-comment on the source GH issue** with the Notion ticket URL (per `notion_ticket_creation.md` → “GitHub Issue → Notion Ticket Back-Link”). This is **mandatory** and must happen at ticket-create time — not deferred until the PR-open comment in step 6.
  ```bash
  gh issue comment <n> --repo xpander-ai/<repo> --body "Notion ticket created: <notion-url>"
  ```

### 3. Plan the change

Use `planning_workflow.md` to write `workspace/local/plans/<TICKET-ID>.md`. Mirror it as an `xpcreate_agent_plan`. The standard task list for a security issue:

1. Branch `fix/develop/<TICKET-ID>` from `develop`.
2. Apply the package / Dockerfile / manifest fix per `security_vulnerability_fix.md`.
3. Validate locally where possible (lock file, dpkg, scanner manifest preview).
4. Open PR per `pr_title_description.md`.
5. Comment on the GH issue with the PR link — keep open until validated.
6. Build / push / deploy (owner-driven if agent lacks creds; document as PR follow-up).
7. Re-run the scanner workflow; confirm 0 of the original severity rows.
8. Close the GH issue with `--reason completed` and link to the PR + green run.
9. Move Notion ticket priority to **`Validation`** (post-merge, awaiting deploy / scan re-run) and then to **`Done`** once verified in production.

### 4. Branch + commit conventions (per `MUST_READ.md`)

- Branch: `fix/develop/<TICKET-ID>` (always from `develop`).
- Commit identity: `xpander-fullstack-generalist <ai_employee_2@xpander.ai>`. **No `Co-authored-by` trailers**.
- Commit message:
  ```
  fix(<TICKET-ID>): patch <CVE-ID> in <component>

  <one-paragraph what + why, including patched version and source advisory>
  ```

### 5. PR description must include

Follow `pr_title_description.md`. For security issues, the body must additionally contain:

- Full CVE table (CVE / package / installed / fixed)
- Link to the upstream advisory (NVD / GHSA / Debian DSA / OSV)
- Link to the original Trivy / scanner run that flagged it
- Link to the GH issue (so GitHub auto-links the PR back)
- Link to the Notion ticket (`PRO-XXXX` URL)
- Explicit Follow-ups section listing build/push/deploy/scan-rerun if those will be done after merge

### 6. Comment on the GH issue when PR opens

```bash
gh issue comment <n> --repo xpander-ai/<repo> --body "$(cat <<'EOF'
Patch PR opened: #<pr> — `fix(<TICKET-ID>): patch <CVE-ID> in <component>`.

<1–2 sentences on the change and the patched version.>

Will close once the new image / package is built, deployed, and the scanner reports 0 of the original <SEVERITY> on the new artifact.
EOF
)"
```

### 7. Close the GH issue (after validation OR with explicit user sign-off)

The GH issue is the source of truth for “is this CVE remediated?”. Default policy:

1. **Preferred**: close only after the rebuilt artifact has been re-scanned and reports 0 CRITICAL/HIGH for the listed CVEs.
2. **User-directed early close** (e.g. “also mark the issue as resolved” before deploy): allowed, but the close comment **must** explicitly note that build/deploy/scan re-validation is still owner-driven and tracked in the PR’s Follow-ups.

Close command:

```bash
gh issue close <n> --repo xpander-ai/<repo> --reason completed --comment "$(cat <<'EOF'
Resolved via PR #<pr> — <one-line summary of the fix and patched version>.

Follow-up handled outside this issue: build/push of the new tag, deploy, and scanner re-validation.
EOF
)"
```

Use `--reason not planned` only if the issue is a duplicate / wont-fix / false positive, and document why in the close comment.

### 8. Update the Notion ticket

After the PR is opened (and especially after the GH issue is closed), move the ticket along the `📍Priority` status property:

| Stage | `📍Priority` value |
|---|---|
| Triaged, not yet picked up | `P1` / `P2` / `Backlog` (severity-based) |
| In active development | `Now` (or keep `P1` if board convention) |
| Code merged, awaiting deploy + scan re-run | **`Validation`** |
| Deployed, scanner clean, GH issue closed | `Done` |

Update using the Notion update-page tool:

```json
{
  "page_id": "<notion-page-id>",
  "command": "update_properties",
  "properties": { "📍Priority": "Validation" }
}
```

The property name is literally `📍Priority` (with the pin emoji); valid values: `🕔 Ideas`, `Backlog`, `P2`, `P1`, `Now`, `Validation`, `Done`.

Also ensure:
- **Type** stays `SecurityVulnerability`
- The Notion page links to the PR and the GH issue (add to body if missing)

### 9. Cross-link in the plan file

Update `workspace/local/plans/<TICKET-ID>.md`:
- `## Status > State`: `in-progress` → `done`
- `## Status > Related PRs / branches`: PR URL
- `## Status > Upstream issue`: GH issue URL + close comment URL
- `## Decisions`: append `YYYY-MM-DD — closed GH issue #<n>; Notion moved to Validation`
- `## Next Action`: owner-driven build/deploy/scan steps if any

---

## Validation Checklist (do not finish without all of these)

- [ ] PR opened from `fix/develop/<TICKET-ID>` against `develop`, by `xpander-fullstack-generalist`.
- [ ] PR description contains CVE table, advisory link, Trivy run link, GH issue link, Notion ticket link, Follow-ups.
- [ ] GH issue has a comment linking the PR (open) **or** is closed with a comment linking the PR (closed).
- [ ] Notion ticket `📍Priority` updated to `Validation` on PR-open. **Do not** advance to `Done` from the agent — that is owner-driven post-verification.
- [ ] Plan file updated, including the GH issue close URL and Notion priority change.
- [ ] If close happened pre-validation: PR Follow-ups + GH close comment explicitly call out the remaining build/deploy/scan steps and their owner.

### Terminal state for the agent (no further action after this)

Once the four side-effects above are done — PR open, GH issue closed, Notion at `Validation`, plan file updated — the agent's work on the ticket is **complete**. Specifically:

- **No status / confirmation email** to the requester. The Notion `📍Priority = Validation` is the status signal. Status emails are reserved for **plans** (per `planning_workflow.md`), never for execution completion on security tickets.
- **No status polling**. Do not check deploy status, image rebuild, scanner runs, or PR checks. The auto-deploy on merge to `develop` and the post-deploy scan are owner-driven (platform/security team). Polling wastes context and crosses an ownership boundary.
- **No `Done` move from the agent**. Notion stays at `Validation` until the owner verifies and advances it.

---

## Anti-Patterns (Don’t)

- Closing the GH issue silently with no comment linking the PR.
- Closing the GH issue with `--reason completed` when no fix shipped (use `not planned` instead).
- Updating Notion to `Done` before the scanner is green on the new artifact.
- Editing the GH issue body to mark it “resolved” — use the issue state and a close comment, not body edits.
- Forgetting to comment on the GH issue when the PR opens (breaks discoverability for the security team).
- Letting GH and Notion drift (one closed, the other still `P1`) — always update both in the same step.
- Skipping the plan-file update — future agents lose the audit trail across sessions.

---

## Cross-References

- Package / image fix mechanics: `security_vulnerability_fix.md`
- PR title & body: `pr_title_description.md`
- Notion ticket creation: `notion_ticket_creation.md`
- Plan file format: `planning_workflow.md`
- Branch / commit / PR rules: `MUST_READ.md`
