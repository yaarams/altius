# Code comment style

**Rule (from user, 2026-04-28):** Comments in code must be **short, precise, and
professional**. They explain intent or non-obvious behaviour - nothing more.

**Reinforced (from user, 2026-05-07):** *"too much comments... do one line
comment, 2 if needed. never add the ticket number in comment."* Five-line
prose blocks are not acceptable, even when describing real edge cases. If you
can't say it in one line (two max), the code itself needs to be clearer.

## Hard limits

- **One line per comment. Two lines maximum.** No multi-paragraph commentary.
- **No ticket numbers in source.** Not as a tag (`# PRO-1168:`), not as a bare
  reference (`# PRO-1168`), not as a footnote. Tickets live in commit messages
  and PR descriptions only.
- **ASCII only** (rule from user, 2026-04-29). No smart quotes, em/en dashes,
  ellipses, arrows, checkmarks, emojis, or non-Latin glyphs. Use `-`, `--`,
  `...`, `->`, `'`, `"`. Applies to all languages and styles (`#`, `//`,
  `/* */`, docstrings, JSDoc).

## Do

- Explain **why**, not what - the code already shows what it does.
- Use complete words, normal sentence case, no leading filler
  ("Note that...", "Just a quick...").
- When summarising a tricky transform, name the input + output shape in one
  line (e.g. `# Coerce per-execution duration (seconds, float) to non-negative int ms.`).

## Don't

- Don't enumerate every event/branch/edge case in prose when a one-line
  summary plus the code itself is clearer.
- Don't narrate history ("used to be...", "legacy bots...") - explain current
  intent.
- Don't paste long quoted requirements; link out via PR/ticket if needed.
- Don't justify defensive code in a paragraph ("so a malformed/missing field
  can't poison the running sum") - the `try/except` or `or 0` already says
  that. A one-line summary is enough.

## Bad (verbose, ticket-tagged, narrates history)

```python
# PRO-1063: when False, suppress all tool events (ToolCallRequest,
# ToolCallResult) AND all plan events (PlanUpdated, which covers both
# plan creation and updates) from the Slack live render. Lifecycle,
# reasoning, sub-agent triggers, chunks and compaction continue to
# stream. Default True preserves today's behaviour for legacy bots.
```

## Bad (5-line prose justifying a 3-line transform)

```python
# PRO-1168: Per-execution wall-clock duration from
# the monitor doc (seconds, float). Defensively
# coerced to a non-negative int millisecond value
# so a malformed/missing field can't poison the
# running sum.
raw_duration = execution_data.get("duration") if isinstance(execution_data, dict) else None
try:
    duration_ms = int(round(max(0.0, float(raw_duration or 0.0)) * 1000))
except (TypeError, ValueError):
    duration_ms = 0
```

## Good (one-liner, intent-only)

```python
# Coerce per-execution duration (seconds, float) to non-negative int ms.
raw_duration = execution_data.get("duration") if isinstance(execution_data, dict) else None
try:
    duration_ms = int(round(max(0.0, float(raw_duration or 0.0)) * 1000))
except (TypeError, ValueError):
    duration_ms = 0
```

## TypeScript / TSX example

Bad:

```ts
// PRO-1063: defaults for any setting that may be missing from a legacy
// bot payload so the form always has a defined value to bind to.
const DEFAULT_SETTINGS: SlackBotSettingsType = { ... };
```

Good:

```ts
// Defaults for legacy bots missing newer settings keys.
const DEFAULT_SETTINGS: SlackBotSettingsType = { ... };
```

## Self-check before committing

Run this in the repo before `git commit` on any branch you authored:

```bash
grep -RInE '(PRO|XPS|PROD|JIRA)-[0-9]+' --include='*.py' --include='*.ts' --include='*.tsx' --include='*.js' --include='*.go' --include='*.md' src services packages 2>/dev/null | grep -v '^.*test' | grep -v '\.md:' || echo 'CLEAN'
```

If it prints anything that isn't `CLEAN` and isn't inside a test fixture or a
markdown doc, scrub it before committing. Comments in source code must come
back `CLEAN`.

Also scan for multi-line comment blocks longer than two lines:

```bash
awk '/^[[:space:]]*#/{c++; if(c==3) print FILENAME":"NR": 3+ line comment block"} !/^[[:space:]]*#/{c=0}' $(git diff --name-only --cached -- '*.py')
```

If any block >= 3 lines, collapse it.

## When trimming existing comments

1. Back up the file under `workspace/local/backups/` per the backup-first rule.
2. Replace verbose blocks with a single intent-line (two max).
3. Strip ticket numbers and "legacy/today's behaviour" narration.
4. Re-run the repo's lint/type-check + relevant tests before committing.
5. Commit message format stays per repo convention
   (`{fix|feat|chore}({ticket}): ...`) - the ticket lives **there**, not in
   source.

## Lessons logged

- 2026-04-28: User flagged verbose multi-line comments on a Slack-bot setting.
  Rule established: one-liner, intent-only, no ticket numbers.
- 2026-04-29: User flagged a non-ASCII em-dash in a Python comment. Rule
  established: ASCII only.
- 2026-05-07: User re-flagged 5-line prose comments on `activity.py`
  (`duration_ms` / `is_running`) that I authored despite this skill already
  existing. Reinforced: 1 line, 2 max, never the ticket number, even when the
  edge case feels worth explaining. The skill rule was correct; my discipline
  failed. The hard limits and self-check sections above are the response.

## See also

- `MUST_READ.md` - references this skill for any code edits.
- `pr_title_description.md` - ticket numbers belong in PR titles/descriptions.
