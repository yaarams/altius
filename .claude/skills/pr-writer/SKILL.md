Gather context by running these git commands before writing anything:

1. `git log develop...HEAD --oneline` — commit messages and IDs
2. `git diff develop...HEAD --stat` — files changed (all commits)
3. `git status --short` — uncommitted changes
4. `git diff HEAD` — uncommitted diff
5. `git diff develop...HEAD` — full committed diff (omit if very large; use `--stat` only in that case)

Also use any available context from @Selected text on page, @The active tab, @Any attached files, and @What I typed (PR text, notes).

Follow these rules for the **title**:

- The title must start with one of: `feat/`, `fix/`, or `chore/`.
  - Choose `feat/` for new functionality or behavior changes, `fix/` for bug fixes, and `chore/` for refactors, tooling, or non-functional changes.
- Immediately after the prefix, include a feature or ticket ID in parentheses, then a colon, then the description, e.g.:
  - `feat(PRO-123): enforce signup validation rules`
- Derive the feature ID from any branch name, ticket reference, or ID found in the PR page, commit messages, or surrounding context in @The active tab/@Selected text on page. If none is clearly available, synthesize a short, uppercased identifier that reflects the domain (e.g. `AUTH`, `BILLING`, `SEARCH`).
- The description portion after the colon must be short, precise, and clearly describe the main change(s). Avoid vague wording like "update code" or "misc changes" and instead use concrete, developer-friendly phrases.

Follow these rules for the **description**:

- Output must be valid Markdown.
- Structure the description into these sections in this exact order and with these headings:
  - `## Purpose`
  - `## Key changes`
  - `## Notes`
  - `## Testing`
  - `## Follow-ups`
- Fill each section based on the diff and commit messages:
  - **Purpose**: 1–3 clear sentences explaining why the change was made (problem, motivation, or requirement).
  - **Key changes**: bullet list summarizing all main code and behavior changes (cover all important files/modules and user-visible behaviors; group related changes logically).
  - **Notes**: call out migrations, configuration changes, backwards-incompatible changes, risks, edge cases, and performance implications.
  - **Testing**: describe how the change was tested (unit, integration, E2E, or manual), referencing specific test files/commands if visible in the diff or commits. If tests are clearly missing, note that explicitly.
  - **Follow-ups**: list any known follow-up tasks, tech debt, or future improvements mentioned in commits or that are clearly implied. If none are apparent, say something like `- None currently planned`.
- **Screenshots section rule**: Only add a `## Screenshots` section if either:
  - The diff indicates changes to React components, UI views, styles, or other front-end presentation code, **or**
  - There are changes to customer-facing/public APIs (HTTP endpoints, SDK interfaces, or other external contracts), **or**
  - The user explicitly asks for screenshots via @What I typed.
    When you add it, use exactly:
  ```
  ## Screenshots
  <!-/
  ```

Important behavior:

- The title and description together must reflect **all significant changes** in the PR. Do not ignore major modules, endpoints, or features present in the diff.
- If there are multiple logical areas touched (e.g., backend + frontend + tests), ensure they are all represented in **Key changes** and, where relevant, in **Notes** and **Testing**.
- Prefer concise wording but include enough technical detail (e.g., key function names, endpoints, or components) for reviewers to quickly understand the scope.

Final output format:

- Return exactly two labeled blocks, in this order, with no extra commentary:

`title`

```
<single-line PR title following the rules above>
```

`description`

```
## Purpose
...

## Key changes
- ...

## Notes
- ...

## Testing
- ...

## Follow-ups
- ...

## Screenshots
<!-- Paste screenshots here if applicable -->
```

- Omit the final `## Screenshots` section entirely if the screenshots rule does not apply. Keep the rest of the section headings even if some may be brief.​​
