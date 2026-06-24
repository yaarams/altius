# Skill: Bump Last Updated Timestamps

## Trigger
User says: "bump the [target] in mono" where target is one of:
- `services` -> scopes: `dev/xpander-mono/services/` + `dev/xpander-mono/agent_containers_images/`
- `sdk` -> scope: `dev/xpander-mono/packages/` or SDK repos
- `dev utils` / `dev-utils` -> scope: relevant dev-utils package path
- `all` / `mono` -> scope: entire `dev/xpander-mono/`

**Note**: "services" always includes `agent_containers_images/` — confirmed 14 files total (11 in services/ + 3 in agent_containers_images/).

## What It Does
Finds all `.md` files containing `## Last updated: {date}` in the target scope,
updates the timestamp to current Israel time (Asia/Jerusalem), commits on a new branch, and opens a PR.

## Step-by-Step Execution

### 1. Ask for ticket number (if not provided)
- Ask: "What's the ticket number for this bump? (e.g. RDT-123)"
- A ticket number is **always required** — never use `NO-TICKET` or skip

### 2. Checkout develop
```bash
cd dev/xpander-mono
git checkout develop
git pull origin develop
```

### 3. Create branch
```bash
git checkout -b chore/develop/{ticket-number}
```
Example: `chore/develop/RDT-123`

### 4. Get current Israel time
```python
from datetime import datetime
import pytz
tz = pytz.timezone('Asia/Jerusalem')
now = datetime.now(tz)
formatted = now.strftime('%-d.%m.%Y %-I:%M%p')  # e.g. 20.04.2025 11:57AM
# Ensure AM/PM is uppercase, no leading zero on day/hour
```
Format: `DD.MM.YYYY H:MMAM` or `H:MMPM` (no leading zero on day or hour)

### 5. Find and update all matching md files
```bash
# Find files
grep -rl '## Last updated:' {scope_path}

# Replace in each file (sed)
sed -i 's/## Last updated: .*/## Last updated: {new_datetime}/g' {file}
```

### 6. Verify changes
```bash
grep -rn '## Last updated:' {scope_path}
```

### 7. Commit
```bash
git add -A
git commit -m "chore({ticket-number}): bump last updated timestamps in {target} READMEs

Co-authored-by: xpander.ai <dev@xpander.ai>"
```

### 8. Push branch
```bash
git push origin chore/develop/{ticket-number}
```

### 9. Create PR
```bash
gh pr create \
  --base develop \
  --head chore/develop/{ticket-number} \
  --title "chore({ticket-number}): bump last updated timestamps in {target} READMEs" \
  --body "Automated timestamp bump for {target} README files.\n\nUpdated \`## Last updated:\` in all {target} markdown files to: {new_datetime} (Israel time)"
```

## Notes
- Date format: `DD.MM.YYYY H:MMAM/PM` (Israel time, Asia/Jerusalem, DST-aware)
- Never push directly to `develop` or `main`
- Always pull latest develop before branching
- Commit type is always `chore` for this operation
