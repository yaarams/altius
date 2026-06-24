# 📝 Notion Ticket Creation — Product & Engineering Board

This skill defines how to create tickets (tasks, features, bugs, improvements) on the **🏗️ Product and Engineering** board in Notion when the user asks to "create a ticket / task / bug / feature" without specifying the board.

---

## When to Use

Trigger this skill whenever the user asks (in chat or via transcribed voice note) to:

- "Create a ticket" / "create a task" / "open a ticket" / "file a bug" / "add a feature request"
- "Create a Notion ticket / task / page"
- Phrases like "add this to the board", "add a new item to product & engineering"

If the user explicitly names a different Notion location (e.g. "add to my personal notes", "in the Bugs database"), follow that instead.

---

## Default Target — Product & Engineering Board

| Field | Value |
|---|---|
| Database title | 🏗️ Product and engineering board |
| Database URL | https://www.notion.so/22029ef830b380769cead5f0af55b9ec |
| Database ID | `22029ef8-30b3-8076-9cea-d5f0af55b9ec` |
| **Data source ID (for create_pages parent)** | `22029ef8-30b3-80e1-b744-000bcde48853` |

Always pass the **data source ID**, not the database ID, when calling `mcp_tool_notion-create-pages`:

```json
"parent": { "type": "data_source_id", "data_source_id": "22029ef8-30b3-80e1-b744-000bcde48853" }
```

---

## Schema — Property Names & Allowed Values

Use these **exact** property names (case + emoji sensitive):

| Property | Type | Allowed values / notes |
|---|---|---|
| `Name` | title | Concise, action-oriented title of the ticket |
| `📍Priority` | status | `🕔 Ideas`, `Backlog`, `P2`, `P1`, `Now`, `Validation`, `Done` |
| `Type` | select | `Bug`, `Feature`, `Improvement`, `feat`, `SecurityVulnerability` |
| `Assignee` | person | JSON array of user IDs (string-encoded) |
| `Customer` | select | `Cox`, `Aquant`, `AppsFlyer`, `JLL`, `Riskified`, `Mercury`, `Internal - Observability Platform`, `Telegram user 7610819257`, `Telegram bot / external integrations`, `Cost visibility / pricing changes`, `SLB`, `HMG`, `ChargeAfter`, `All`, `xpander.ai`, `KaloSys`, `qbiq` |
| `userDefined:ID` | auto_increment_id | Auto-set, do **not** populate |
| `Created by` / `Created time` / `Last edited time` | system | Read-only, do **not** populate |
| `GitHub Pull Requests` | relation | Optional |

### Mapping the user's words → properties

| User says | Set |
|---|---|
| "priority now" / "urgent" / "asap" | `📍Priority` = `Now` |
| "P1" / "high priority" | `📍Priority` = `P1` |
| "P2" / "medium" | `📍Priority` = `P2` |
| "backlog" / "later" | `📍Priority` = `Backlog` |
| "idea" / "someday" | `📍Priority` = `🕔 Ideas` |
| "feature" / "feature request" | `Type` = `Feature` |
| "bug" / "bug report" / "defect" | `Type` = `Bug` |
| "improvement" / "polish" | `Type` = `Improvement` |
| "security" / "CVE" / "vulnerability" | `Type` = `SecurityVulnerability` |
| "assign to me" | Lookup user via `mcp_tool_notion-search` (`query_type: user`) using the email from the runtime user details, set `Assignee` to `["<user_uuid>"]` |
| "assign to <name>" | Same lookup with the provided name/email |
| "for customer X" | `Customer` = matching option (must be exact) |

### Known user IDs (cache)

| Email | Name | User ID |
|---|---|---|
| moriel@xpander.ai | Moriel Pahima | `21f07760-2bdf-475f-b6b3-5924eb84bf49` |

If an assignee is unknown, resolve it once with:

```
mcp_tool_notion-search { query: "<email or name>", query_type: "user", filters: {} }
```

and append the result to the cache table above (update this skill).

---

## Ticket Body — Required Sections

Every ticket created via this skill must include rich, well-structured Markdown content. Use these sections (omit any that don't apply, but never write an empty body):

1. `# Overview` — one paragraph describing what this ticket is about
2. `# Background / Problem` — for bugs, include the repro steps verbatim from the user; for features, include the motivation
3. `# Goal` — concise statement of the desired end-state
4. `# Proposed Behavior` *or* `# High-level Flow` — numbered steps of how it should work
5. `# Acceptance Criteria` — checkbox list (`- [ ] ...`) covering correctness, edge cases, observability, and tests
6. `# Out of Scope` — short list of what this ticket does **not** cover
7. `# Notes / References` — touchpoints, related repos, SDK references, links

Writing rules:

- Preserve the user's repro steps and concrete details verbatim — do not paraphrase technical specifics
- Prefer **action-oriented** wording in `Name` ("Add X", "Fix Y", "Prevent Z")
- Keep titles ≤ ~120 chars; put detail in the body, not the title
- Markdown rules: follow the Notion enhanced-markdown spec (no triple-backtick fences for the title, etc.)
- Add a relevant emoji `icon` to the page (e.g. 🧹 cleanup, 🛑 stop/cancel, 🐛 bug, ✨ feature, 🔒 security)

---

## Required Steps (every time)

1. **Resolve assignee user ID** if not in cache — `mcp_tool_notion-search` with `query_type: "user"`.
2. **Confirm the data source ID is still `22029ef8-30b3-80e1-b744-000bcde48853`** if the operation has not been run recently in this session — a single `mcp_tool_notion-fetch` on the database URL is enough. Skip if just used.
3. **Create the page** with `mcp_tool_notion-create-pages`:
   - `parent.type = "data_source_id"` and `parent.data_source_id` = the value above
   - `properties.Name` = clean title
   - `properties."📍Priority"` = mapped value
   - `properties.Type` = mapped value
   - `properties.Assignee` = JSON-encoded string array of user IDs, e.g. `"[\"21f07760-2bdf-475f-b6b3-5924eb84bf49\"]"`
   - `icon` = a relevant emoji
   - `content` = full markdown body following the section template above
4. **If the ticket was created from a GitHub issue, back-comment on that GH issue** with the Notion ticket URL — see §“GitHub Issue → Notion Ticket Back-Link” below. **Mandatory**, no exceptions.
5. **Return** the resulting page URL to the user, along with a short summary block (Name / Priority / Type / Assignee / link / GH issue link if applicable).

---

## GitHub Issue → Notion Ticket Back-Link (MANDATORY)

Whenever a Notion ticket is created **in response to a GitHub issue** (any source: Trivy / Dependabot / IQ Server / human-filed bug / feature request / etc.), the GH issue **must** receive a comment linking the Notion ticket the moment the page is created. This keeps the GH issue and the engineering board in sync and gives the security/triage team one click to find the owning ticket.

### When this applies

- The user references a GH issue (`#1234`, full URL, or “go over the gh issues and create tickets”).
- The body of the new Notion ticket cites a GH issue (e.g. “Tracked in upstream GitHub issue #3787”).
- Any task that says “file a ticket for this bug report” where the bug report is a GH issue.

If there is no GH issue (e.g. ticket created from a voice note or a Slack message), this rule does not apply.

### How to comment

Use `gh issue comment` (preferred — runs as the agent identity) or, if `gh` is unavailable in the current shell, the GitHub MCP tool. Always verify the active `gh` account is `xpander-fullstack-generalist` first (see `MUST_READ.md` §2a).

```bash
gh issue comment <n> --repo xpander-ai/<repo> --body "$(cat <<'EOF'
Notion ticket created: [<Notion ticket title>](<notion-url>)

- **Priority:** <📍Priority value>
- **Type:** <Type value>
- **Assignee:** <name>

Will update the ticket to `Validation` once a fix PR is opened, and to `Done` after validation.
EOF
)"
```

Minimal acceptable comment (when batch-creating many tickets at once):

```
Notion ticket created: <notion-url>
```

### Batch creates

If you create N tickets from N GH issues in one pass, post N comments — one per issue, each linking only to the ticket created for **that** issue. Do not post a single combined comment listing all tickets on every issue; it pollutes the threads and breaks 1:1 traceability.

### Failure handling

- If `gh issue comment` fails (auth, network, repo access), surface the failure to the user and do not silently skip. The Notion ticket exists; the GH back-link is missing and must be retried.
- Never edit the GH issue body to insert the Notion link — comments only. Body edits break audit trails.

### Why

- Security team triages from the GH Security tab; they need the Notion ticket without leaving GitHub.
- The reverse link (Notion → GH) is already in the ticket body; without the forward link (GH → Notion) the loop is broken and tickets get duplicated on the next scan.

---

## Reference: Working Tool Call Skeleton

```json
{
  "parent": {
    "type": "data_source_id",
    "data_source_id": "22029ef8-30b3-80e1-b744-000bcde48853"
  },
  "pages": [
    {
      "properties": {
        "Name": "<Action-oriented title>",
        "📍Priority": "Now",
        "Type": "Feature",
        "Assignee": "[\"21f07760-2bdf-475f-b6b3-5924eb84bf49\"]"
      },
      "icon": "✨",
      "content": "# Overview\n...\n\n# Goal\n...\n\n# Proposed Behavior\n1. ...\n\n# Acceptance Criteria\n- [ ] ...\n\n# Out of Scope\n- ...\n\n# Notes\n- ..."
    }
  ]
}
```

---

## Gotchas

- **Use the data source ID, NOT the database ID** for `parent`. Using the database ID will silently create the page elsewhere.
- The Priority property name contains the **📍 emoji** — `📍Priority`. Do not strip it.
- `Assignee` must be a JSON-encoded string of an array of user IDs (Notion's expanded format), not a plain JS array.
- Do not set `userDefined:ID` — it auto-increments.
- If the user gives only a voice note, transcribe → extract → still produce a structured body (Overview / Goal / AC / etc.). Don't dump the raw transcript as the body.
- If multiple tickets are requested in one message, create them all (each as a separate `pages[]` entry or sequential calls), and return one summary block per ticket.

---

## Updating This Skill

When the board's schema changes (new option in `📍Priority`, `Type`, or `Customer`; renamed property; added required field), update the tables above so the next run uses the correct values. Re-fetch the database with `mcp_tool_notion-fetch` to confirm the new schema before editing.

---

## Cross-Skill Rule — Move to `Validation` on PR-Open

When a PR that resolves a Notion ticket is **opened** (any ticket type, not just security), set the ticket's `📍Priority` to `Validation` immediately. This signals engineering is done and the team owns validation/sign-off.

```
mcp_tool_notion-update-page {
  page_id: "<notion-page-id>",
  command: "update_properties",
  properties: { "📍Priority": "Validation" }
}
```

For **security-fix** PRs, this is doubly enforced — see `workspace/dev-knowledge/skills/security_vulnerability_fix.md` ("Post-PR Bookkeeping"), which also requires immediately closing the upstream GitHub security issue with a reference to the new PR.
