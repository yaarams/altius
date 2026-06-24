---
name: notion-docs-sync
description: Use when user asks to dump, sync, mirror, or publish markdown docs (e.g. files under /docs) to a Notion page with subpages, or update an existing Notion index page with child pages per md file.
---

# notion-docs-sync

Mirror a directory of markdown files into Notion as a parent index page + one child page per md file. Index uses `<mention-page>` so each row renders with the child page icon + title.

## When to use

- "dump docs to notion"
- "create notion page with subpage per md file"
- "sync /docs with this notion page"
- "publish architecture docs to notion"

Skip if user wants single page, or non-md content.

## Required inputs

Ask user only if missing:
1. **Scope** — which md files (top-level dir? recursive? glob?)
2. **Parent page URL** — Notion API cannot create at workspace root; need existing page UUID

## Workflow

1. `find <dir> -maxdepth N -name "*.md"` to list files.
2. If parent page lacks index table, build one:
   - Replace content with intro + table (`| Doc | Topic |`).
   - One row per md file.
3. For each md file: call `mcp__claude_ai_Notion__notion-create-pages` with `parent.page_id = <parent uuid>`. Batch up to 100 in one call.
4. After creation, `notion-update-page` `update_content` to replace each table cell title with `<mention-page url="...">TITLE</mention-page>`.

## Notion markdown gotchas

- Parent param is **required** by schema even though tool description says "omit for workspace-root". Workspace-root creation **not supported via API** — must pass valid page UUID.
- For child-page links in tables, use `<mention-page url="https://www.notion.so/<id>">Title</mention-page>` (renders icon + title). `<a href>` and `[text](url)` get mangled by Notion's md parser inside table cells.
- `update_content` uses `old_str`/`new_str` exact-match search-replace. After each edit Notion may rewrite content — fetch fresh before next pass if old_str fails.
- Code blocks, tables, mermaid blocks pass through. Strip emojis only if user requested.
- Page icon via `icon` field (single emoji char). Use distinct icon per page type for scannability.

## Bulk-create pattern

```
mcp__claude_ai_Notion__notion-create-pages({
  parent: { type: "page_id", page_id: "<uuid>" },
  pages: [
    { properties: { title: "FOO" }, icon: "📄", content: "<md...>" },
    ...up to 100
  ]
})
```

Returned IDs feed the table-update pass.

## Link-update pattern

```
mcp__claude_ai_Notion__notion-update-page({
  page_id: "<parent uuid>",
  command: "update_content",
  properties: {},
  content_updates: [
    {
      old_str: "<tr>\n<td>FOO</td>\n<td>desc</td>\n</tr>",
      new_str: "<tr>\n<td><mention-page url=\"https://www.notion.so/<child id>\">FOO</mention-page></td>\n<td>desc</td>\n</tr>"
    },
    ...
  ]
})
```

## Tools to load via ToolSearch

- `mcp__claude_ai_Notion__notion-create-pages`
- `mcp__claude_ai_Notion__notion-update-page`
- `mcp__claude_ai_Notion__notion-fetch` (when old_str matching fails — fetch current state)
- `mcp__claude_ai_Notion__notion-search` (only if parent page not given)

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `parent.page_id should be a valid uuid` | Sent empty/null parent | User must supply parent URL/ID |
| `No matches found for <old_str>` | Notion rewrote content after prior edit | Fetch page, use actual stored markdown |
| Table cell shows raw `<a href>` text | `<a>` inside table cell got escaped | Use `<mention-page>` instead |
| `[Title](url">Title</a>)` garbage in cell | HTML mixed with md link syntax | Replace entire cell content via `<mention-page>` |

## Don't

- Don't try to create at workspace root (API rejects).
- Don't paste full md verbatim if file >100KB — split or summarize.
- Don't re-create existing subpages on re-sync — fetch parent first, match by title, update instead.
- Don't use `[text](url)` for child-page references in tables.
