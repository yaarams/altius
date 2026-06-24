# AI Agent Skill: PR Title & Description Generator

## Goal

Generate a **developer-readable PR title and description** from the diff and commit messages, optimized for code review clarity.
Screenshots section to be added Only if had a changed react components or customer facing apis!

---

## When to Use

Always use this skill when creating a pull request via `gh pr create` — generate the title and description from the actual diff and commit messages before opening the PR.

---

## Title Rules

* **Prefix**: must start with `feat/`, `fix/`, or `chore/`
* **Feature ID**: must appear in parentheses before colon
  Example:

  ```
  feat(PRO-123): enforce signup validation rules
  ```
* **Content**: short, descriptive, and accurately summarizing the changes
* **Readable**: avoid vague terms ("update stuff"), use precise language developers expect in PRs

---

## Description Rules

* **Markdown format**
* Must be clear and structured for reviewers
* Sections included:

  * **Purpose**: why the change was made
  * **Key changes**: bullet points summarizing main changes
  * **Notes**: migrations, configs, risks, performance impacts
  * **Testing**: unit, integration, or manual steps
  * **Follow-ups**: future tasks or linked tickets
* **Optional (only if applicable — react components or customer-facing APIs changed)**:
  Add a placeholder for screenshots:

  ```
  ## Screenshots
  <!-- Paste screenshots here if applicable -->
  ```

---

## Output Format

Return exactly **two separate results**:

**title**

```
feat(PRO-123): enforce signup validation rules
```

**description**

```
## Purpose
Introduce server-side validation for signup requests to prevent invalid payloads and improve error clarity.

## Key changes
- Added `SignupRequest` Pydantic model
- Applied validation to `POST /api/v1/signup`
- Standardized 400 error response with `code` and `message`
- Extended unit tests to cover invalid inputs

## Notes
- No database migrations required
- Error responses may affect API clients relying on old structure

## Testing
- Unit tests updated in `tests/api/test_signup.py`
- Manual: verified invalid payloads return expected responses

## Follow-ups
- PRO-129: add password policy configuration

## Screenshots
<!-- Paste screenshots here if applicable -->
```

---

## IMPORTANT

- The title & description **must cover ALL changes in the PR** — derive them from `git diff` and commit messages, not from assumptions
- Never use generic descriptions — inspect the actual diff before writing
- Always run `git diff develop...HEAD` (or the relevant base branch) to get the full picture
