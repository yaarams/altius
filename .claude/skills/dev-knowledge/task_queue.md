# Task Queue — Single-Task Execution Discipline

**Why this exists:** there is one developer (me) and one shared dev folder where repos are cloned. Switching repos/branches mid-task corrupts working state. This skill enforces **one in-progress task at a time**, persisted in the local SQLite DB so it survives across sessions. It also drives self-scheduling so I can wake myself up when a task is time-deferred or the queue needs polling.

---

## 0. Bootstrap — Idempotent Schema (run if `task_queue` is missing)

The entry check below silently fails on a fresh agent that hasn't run this skill yet. If `xpworkspace-local-db-list-tables` doesn't show `task_queue`, run this DDL once — it's idempotent and safe to run repeatedly:

```sql
CREATE TABLE IF NOT EXISTS task_queue (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL CHECK(status IN ('pending','in_progress','completed','cancelled','blocked')) DEFAULT 'pending',
  priority INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  started_at TEXT,
  completed_at TEXT,
  repo TEXT,
  branch TEXT,
  notes TEXT,
  requested_by TEXT,
  scheduled_for TEXT,            -- nullable; UTC ISO timestamp for deferred tasks
  schedule_id TEXT               -- xpschedule-create id linked to this row (for dedup/cancel)
);

CREATE INDEX IF NOT EXISTS idx_task_queue_status_priority
  ON task_queue(status, priority DESC, created_at ASC);

-- Hard guard: at most one in_progress row, ever.
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_queue_one_in_progress
  ON task_queue(status) WHERE status = 'in_progress';

-- Helps the scheduler peek for due-but-not-yet-started rows.
CREATE INDEX IF NOT EXISTS idx_task_queue_scheduled_for
  ON task_queue(scheduled_for) WHERE scheduled_for IS NOT NULL;
```

The export bundle ships `memory/db/task_queue.sql` with this DDL plus a row dump; on import the same statements run, so a freshly-imported agent has the queue ready without manual setup.

---

## ⚠️ MANDATORY ENTRY CHECK — Run on Every User Request

Before doing **anything** else when a user sends a request:

```sql
SELECT id, title, status, repo, branch, started_at, scheduled_for, schedule_id
FROM task_queue
WHERE status IN ('in_progress','blocked')
   OR (status = 'pending' AND scheduled_for IS NOT NULL)
ORDER BY status DESC, started_at DESC;
```

Then branch on the result:

| State | Action |
|---|---|
| **No `in_progress` row** AND request is normal work | Insert as `pending` → start it (move to `in_progress`) → execute |
| **`in_progress` row exists** AND new request is unrelated | Enqueue new request as `pending`, reply: *"I'm currently working on **<active title>**. I've queued your request as #N. I'll start it once the current task completes."* — then **stop**, do not execute |
| **`in_progress` row exists** AND new request is a follow-up / clarification on the same task | Continue the current task; append to `notes` |
| **Special command** (see §3) | Handle the command, do not execute new work |
| **All `pending` rows are deferred** (`scheduled_for` in the future) | Tell the user when next task wakes up; offer to start one now |

**Never start a second `in_progress` task.** The DB has a partial unique index that will reject it.

---

## 1. Schema Reference

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | UUID, generated with `lower(hex(randomblob(16)))` |
| `title` | TEXT | Short (≤80 chars) human label |
| `description` | TEXT | Full original user request, verbatim |
| `status` | TEXT | `pending` / `in_progress` / `completed` / `cancelled` / `blocked` |
| `priority` | INT | Default 0. Higher = sooner. Bump only on explicit user request. |
| `created_at` | TEXT | `datetime('now')` UTC |
| `started_at` | TEXT | Set when moved to `in_progress` |
| `completed_at` | TEXT | Set when moved to `completed`/`cancelled` |
| `repo` | TEXT | e.g. `frontend`, `xpander-mono`, `xpander-sdk` |
| `branch` | TEXT | Branch name once created |
| `notes` | TEXT | Free-form progress / blockers (append, don't overwrite) |
| `requested_by` | TEXT | User email from the request context |
| `scheduled_for` | TEXT | Optional UTC ISO timestamp; row stays `pending` until this time |
| `schedule_id` | TEXT | UUID returned by `xpschedule-create` for the wake-up call |

Constraints:
- `CHECK(status IN (...))` on status
- Partial unique index: at most one `in_progress` at any time
- Composite index `idx_task_queue_status_priority`: fast peek/next lookups
- Partial index `idx_task_queue_scheduled_for`: fast deferred-task queries

---

## 2. Standard Operations (copy-paste SQL)

### 2.1 Peek — active + ready-to-run + deferred
```sql
-- Currently active
SELECT id, title, repo, branch, started_at FROM task_queue WHERE status='in_progress';

-- Ready to start now (pending, no future scheduled_for)
SELECT id, title, priority, created_at, requested_by
FROM task_queue
WHERE status='pending'
  AND (scheduled_for IS NULL OR scheduled_for <= datetime('now'))
ORDER BY priority DESC, created_at ASC LIMIT 10;

-- Deferred (pending but waiting for scheduled_for)
SELECT id, title, scheduled_for, schedule_id FROM task_queue
WHERE status='pending' AND scheduled_for > datetime('now')
ORDER BY scheduled_for ASC;
```

### 2.2 Enqueue a new task (no auto-start)
```sql
INSERT INTO task_queue (id, title, description, status, priority, repo, requested_by)
VALUES (lower(hex(randomblob(16))), ?, ?, 'pending', 0, ?, ?);
```

### 2.3 Start the next ready pending task
```sql
UPDATE task_queue
SET status='in_progress', started_at=datetime('now')
WHERE id = (
  SELECT id FROM task_queue
  WHERE status='pending'
    AND (scheduled_for IS NULL OR scheduled_for <= datetime('now'))
  ORDER BY priority DESC, created_at ASC LIMIT 1
);
```

### 2.4 Add a progress note
```sql
UPDATE task_queue
SET notes = COALESCE(notes || char(10), '') || ?
WHERE id = ?;
```

### 2.5 Set repo / branch on the active task
```sql
UPDATE task_queue SET repo=?, branch=? WHERE status='in_progress';
```

### 2.6 Complete the active task
```sql
UPDATE task_queue SET status='completed', completed_at=datetime('now')
WHERE status='in_progress';
```
Then run §2.3 to auto-start next. If nothing ready and a deferred task exists, see §8 to self-schedule a wake-up.

### 2.7 Block the active task
```sql
UPDATE task_queue
SET status='blocked', notes=COALESCE(notes||char(10),'')||?
WHERE status='in_progress';
```

### 2.8 Cancel the active task
```sql
UPDATE task_queue
SET status='cancelled', completed_at=datetime('now'),
    notes=COALESCE(notes||char(10),'')||'cancelled by user: '||?
WHERE status='in_progress';
```

### 2.9 Cancel a specific pending task
```sql
UPDATE task_queue SET status='cancelled', completed_at=datetime('now')
WHERE id=? AND status='pending';
```

### 2.10 Reprioritize
```sql
UPDATE task_queue SET priority=? WHERE id=? AND status='pending';
```

### 2.11 Defer a task to a specific UTC time
```sql
UPDATE task_queue SET scheduled_for=? WHERE id=? AND status='pending';
-- Then create a wake-up via xpschedule-create (see §8) and store its id:
UPDATE task_queue SET schedule_id=? WHERE id=?;
```

### 2.12 Reset queue (DESTRUCTIVE — explicit user command only)
```sql
UPDATE task_queue
SET status='cancelled', completed_at=datetime('now'),
    notes=COALESCE(notes||char(10),'')||'queue reset by user'
WHERE status IN ('pending','in_progress','blocked');
```
Also call `xpschedule-delete` on every non-null `schedule_id` to clean up pending wake-ups.

### 2.13 Hard wipe (rarely needed)
```sql
DELETE FROM task_queue;
```

---

## 3. Recognized User Commands

| Phrase pattern | Action |
|---|---|
| "show queue", "queue status", "what are you working on" | Run §2.1, render markdown table including deferred rows |
| "cancel current", "abort" | Run §2.8 → §2.3 |
| "cancel #N" / "cancel <id>" | Run §2.9 (and `xpschedule-delete` if `schedule_id`) |
| "reset queue", "clear queue" | Run §2.12 |
| "work on this instead", "switch to this" | Ask: cancel current or just bump priority? Do NOT silently preempt. |
| "pause", "block this" | Run §2.7 on the active task |
| "resume <id>", "unblock <id>" | Set blocked row back to `pending` |
| "bump <id>", "prioritize <id>" | Run §2.10 |
| "do this in 2 hours", "start tomorrow at 9am" | §2.11 + self-schedule per §8 |
| "check back in an hour", "poll the queue later" | Self-schedule per §8.3 |

If ambiguous between command and new task, ask via `xpask_for_information`.

---

## 4. Lifecycle

```
User request arrives
  │
  ▼
[Entry check]  ── in_progress exists & unrelated? ──► enqueue (§2.2), reply "queued", STOP
  │ no
  ▼
Insert pending (§2.2) → start (§2.3) → set repo/branch (§2.5)
  │
  ▼
Do the work. Append progress notes (§2.4) at meaningful checkpoints.
  │
  ▼
Finish work → complete (§2.6) → auto-start next (§2.3)
  │
  ▼
Nothing ready? → if deferred task exists, self-schedule wake-up (§8); else done.
```

Rules of thumb:
- **One `in_progress` row.** DB enforces it; you should too.
- **Never silently drop a request.** If you can't take it now, enqueue it.
- **Mark `completed` immediately** when done.
- **Persist intent in `notes`.** Branch name, PR url, blocker reason — a future session resumes from these.
- **`completed`/`cancelled` rows stay** for audit. Don't delete them.

---

## 5. Reporting Templates

**Enqueue:** `📥 Queued as **#<short-id>** — *<title>*. Currently working on *<active title>*. Position: <N>.`

**Start:** `▶️ Starting **#<short-id>** — *<title>*.`

**Complete + auto-pick:** `✅ Completed **#<short-id>** — *<title>*. ▶️ Now starting **#<next-id>**.`

**Deferred:** `⏰ Scheduled **#<short-id>** — *<title>* for <UTC ts> (in <H>h <M>m). I'll resume automatically.`

**Idle wake-up:** `🛌 Queue empty, going idle. Will check back at <UTC ts> (or sooner if you send a request).`

**Short-id convention:** first 8 chars of UUID (`substr(id,1,8)`).

---

## 6. Edge Cases

- **DB rejects new `in_progress`** → another task is active; redo the entry check.
- **Continuation vs new task** → stay on active task, append a `notes` entry; do NOT create a new row.
- **Stale `in_progress` row** (started_at days old, no recent notes) → ask user before accepting new work.
- **Plan tool vs queue:** `xpcreate_agent_plan` tracks **steps within one task**; `task_queue` tracks **tasks across user requests**.
- **Repo conflict:** if active task touches `frontend` and a new pending request also touches `frontend`, queueing it is correct — do NOT peek at another repo while a task is active (dirty working tree risk).

---

## 7. First Action in Every Session

```sql
SELECT id, title, status, repo, branch, started_at, scheduled_for, schedule_id, notes
FROM task_queue
WHERE status IN ('in_progress','blocked')
   OR (status='pending' AND scheduled_for IS NOT NULL)
ORDER BY started_at DESC;
```

If anything comes back, report to the user before accepting new work:
> "Resuming context: task **#<id>** (*<title>*) is `<status>` on `<repo>`/`<branch>`. Last note: `<notes-tail>`. Continue, complete, or cancel?"

Also run `xpschedule-list` once per session and reconcile against `schedule_id` column — stale schedules (linked task already completed/cancelled) should be deleted.

---

## 8. Self-Scheduling — When and How

`xpschedule-create` lets me wake myself up. The queue uses it for three cases:

### 8.1 Deferred task start ("do X tomorrow at 9am")
```text
1. Insert task as pending with scheduled_for set (§2.11)
2. Compute UTC ISO ts (append `Z`).
3. Call xpschedule-create with:
     prompt = "Wake up: pending task #<short-id> (<title>) is due. Run the entry check and start it if no in_progress task exists."
     run_at = <UTC ISO>
     task_id = <omit>  (continue current thread; or pass a new UUIDv4 for a fresh thread)
4. Save returned schedule id into schedule_id column (§2.11 second statement).
5. Reply with the "Deferred" template (§5).
```

### 8.2 Resume a blocked task ("check back in an hour")
```text
Use §2.7 to mark blocked, then xpschedule-create with prompt:
"Re-check blocked task #<short-id> — if blocker is cleared, set it back to pending and run §2.3."
Store the returned id in schedule_id.
```

### 8.3 Idle queue polling ("come back later if anything new")
Only if the user explicitly asks me to follow up later AND the queue is empty. Do NOT self-schedule speculatively — it costs runs. Pattern:
```text
xpschedule-create prompt="Poll task_queue: if any pending row is ready, start it. Otherwise idle." run_at=<UTC ISO>
```
Store the returned id in `workspace/dev-knowledge/memory/queue_idle_schedule.txt` (single-line file) so a future session knows there's an outstanding poll and won't double-book.

### 8.4 Anti-patterns (DO NOT)
- Don't self-schedule when an `in_progress` task is active — you'll be working anyway.
- Don't cascade self-schedules (one wake-up shouldn't schedule another wake-up). Always check `xpschedule-list` first; if a relevant schedule already exists, no-op.
- Don't self-schedule for under 60 seconds — use direct work instead.
- Don't self-schedule indefinitely — cap at one outstanding idle-poll per task, max 24h horizon.
- Don't forget to clear `schedule_id` when the linked task is completed/cancelled, and call `xpschedule-delete` on it.

### 8.5 Reconciliation on session start
```text
1. Run xpschedule-list.
2. SELECT id, schedule_id FROM task_queue WHERE schedule_id IS NOT NULL.
3. For each schedule_id in DB but not in xpschedule-list → NULL the column (already fired).
4. For each schedule in xpschedule-list but linked to a completed/cancelled row → xpschedule-delete it.
```

---

## 9. Export / Import Persistence

The `task_queue` table is part of the agent's persistent brain. Export and import handle it automatically:

- **`agent_export.sh`** dumps the schema + all rows to `memory/db/task_queue.sql` inside the bundle. Cancelled rows are kept (audit trail), but `schedule_id` values are nulled in the dump because they reference the source agent's scheduler.
- **`agent_import.sh`** detects `memory/db/task_queue.sql` after the file merge and applies it to the local SQLite DB. The DDL uses `CREATE TABLE IF NOT EXISTS` and the row inserts use `INSERT OR IGNORE` keyed on `id`, so re-import is idempotent.
- A fresh agent that never had the table can run the bootstrap DDL in §0 manually — same statements as the export bundle.
