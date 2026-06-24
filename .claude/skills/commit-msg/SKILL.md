Gather context by running these git commands before writing anything:

1. `git diff --cached` — staged changes (the diff to commit)
2. `git log --oneline -10` — recent commits to match style and ticket IDs
3. `git status --short` — confirm what is staged

Use any available context from @Selected text on page, @The active tab, @Any attached files, and @What I typed (notes, ticket ID, intent).

Follow these rules for the **commit message**:

### Format

Use Conventional Commits: `<type>(<scope>): <subject>`

- **type**: `feat` (new feature/behavior), `fix` (bug fix), `chore` (refactor, tooling, non-functional)
- **scope**: the affected module or domain (e.g. `connectors`, `billing`, `auth`, `workflows`). Derive from changed file paths.
- **subject**: imperative mood, ≤50 chars, no period at end. Describe _what_ changes, not _how_.

### Ticket ID

- If recent commits include a ticket ID like `PRO-1108`, include it in the subject: `feat(PRO-1108): ...`
- Ticket ID goes inside the scope parentheses, replacing or alongside the scope: `feat(PRO-1108): subject`
- If no ticket ID found, use scope only: `feat(connectors): subject`

### Body (optional)

- Add a body only when the _why_ is non-obvious from the subject alone.
- Separate from subject with a blank line.
- Wrap at 72 chars.
- Explain motivation, not mechanics.

### Rules

- Never mention file names or implementation details in the subject — those belong in the body or are obvious from the diff.
- One commit = one logical change. If staged changes span multiple unrelated concerns, note that in your output.
- Do NOT include `Co-Authored-By` lines — the user will add those.

### Output format

Return exactly one labeled block with no extra commentary:

`commit message`

```
<type>(<scope>): <subject>

[optional body]
```
