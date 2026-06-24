# Skill: agent_onboarding

Post-import bootstrap. After `agent_import.sh --mode=<merge|...>` finishes
merging files, the new agent has skills, memory, and context — but it has no
GitHub credentials, no git identity, and no record of who it is. This skill
drives the LLM-side onboarding loop that closes that gap.

## When to run

Immediately after a successful import that produced an
`onboarding_required.json` manifest. Detect it by globbing:

```bash
ls workspace/tmp/import_*_onboarding_required.json 2>/dev/null | tail -1
```

If the file exists, onboarding has not yet been completed for that import. If
it doesn't exist, either the bundle didn't request onboarding (older bundle)
or it was already consumed.

## Loop (LLM-side, executed by the agent)

1. **Read the manifest.** Open the latest
   `workspace/tmp/import_<ts>_onboarding_required.json`. It contains a
   `questions` array — each item has `id`, `prompt`, and optional
   `sensitive` / `optional` flags.
2. **Ask one question at a time** via `xpask_for_information`.
   - Use the `prompt` text verbatim.
   - For `sensitive: true`, tell the user to paste the secret. **Never echo
     the answer back, never write it into a tool reasoning field, never log
     it.** Treat it like a password.
   - For `optional: true`, accept `"skip"` / empty as a valid answer (store
     as empty string).
3. **Persist answers** to `workspace/tmp/onboarding_inputs.json` as a flat
   JSON object keyed by question `id`:
   ```json
   {
     "agent_name": "my-new-agent",
     "git_user_name": "my-bot",
     "git_user_email": "bot@example.com",
     "gh_user": "my-bot",
     "gh_token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxx",
     "xpander_email": "user@example.com",
     "notion_workspace": ""
   }
   ```
   Files under `workspace/tmp/` are NEVER included in any future export
   (export excludes `tmp/`), so it's safe to keep the token there
   transiently. Delete the file once onboarding succeeds.
4. **Apply** by invoking the import script in onboard mode:
   ```bash
   bash workspace/dev-knowledge/skills/agent_import.sh --onboard \\
        --inputs=workspace/tmp/onboarding_inputs.json
   ```
   The script:
   - Backs up any existing `~/.config/gh/hosts.yml`, `~/.gitconfig`,
     `~/.git-credentials`, `~/.netrc` to
     `workspace/tmp/import_<ts>_home_backup/`.
   - Writes new versions with `0600` (creds) / `0644` (gitconfig).
   - Patches the `## Git Identity` section of
     `workspace/dev-knowledge/memory/workspace_setup.md` to reflect the new identity.
   - Creates `workspace/dev-knowledge/memory/agent_identity.md`.
   - Runs best-effort smoke tests (`gh auth status`, `git config --global
     --list`) and includes their output in the printed summary.
   - Prints a summary JSON with `gh_token` redacted.
5. **Confirm** by reading the printed summary. If `smoke.gh_auth_status.rc`
   is `0`, GitHub auth is live. If `git_config_list.rc` is `0` and shows
   `user.name` / `user.email`, git is configured.
6. **Clean up** the inputs file:
   ```bash
   shred -u workspace/tmp/onboarding_inputs.json 2>/dev/null \\
     || rm -f workspace/tmp/onboarding_inputs.json
   rm -f workspace/tmp/import_<ts>_onboarding_required.json
   ```
7. **Direct the user** to `workspace/dev-knowledge/skills/MUST_READ.md` and
   `workspace/dev-knowledge/memory/agent_identity.md`. Onboarding is done.

## Reruns

If the user asks to re-onboard (e.g. token rotation), pass `--force`:

```bash
bash workspace/dev-knowledge/skills/agent_import.sh --onboard \\
     --inputs=workspace/tmp/onboarding_inputs.json --force
```

Without `--force`, the script refuses to overwrite existing credential files
and returns `error: already_onboarded`.

## Custom locations (for tests / sandbox)

For self-tests, point onboarding at a sandbox HOME so you don't touch the
real agent home dir:

```bash
bash workspace/dev-knowledge/skills/agent_import.sh --onboard \\
     --inputs=workspace/tmp/fake_inputs.json \\
     --home=workspace/tmp/sandbox_home \\
     --target-root=workspace/tmp/sandbox_target
```

This is the recommended way to validate a new install without risking the
live credentials.

## Security rules

- `gh_token` MUST never appear in logs, summary stdout, tool-call reasoning
  fields, or any persisted file under `workspace/dev-knowledge/memory/` or
  `workspace/local/`. The export scrubber will catch obvious shapes
  (`ghp_…`, `github_pat_…`), but defence-in-depth is better.
- The credential files (`hosts.yml`, `.git-credentials`, `.netrc`) live
  outside `workspace/` (under `/agent/data/.home/` by default) and are
  therefore not included in any export bundle. Don't ever copy them in.
- The `onboarding_required.json` manifest contains only prompts, not
  answers. Safe to keep around / commit if needed, though it normally
  belongs under `tmp/`.
- The `onboarding_inputs.json` file contains the live token. Delete it the
  moment onboarding succeeds.

## Required field reference

From `agent_import.sh --onboard`'s validator:

| Field | Purpose | Required |
|---|---|---|
| `agent_name` | Display name written into `agent_identity.md` | yes |
| `git_user_name` | `git config user.name` | yes |
| `git_user_email` | `git config user.email` | yes |
| `gh_user` | GitHub username; goes into `hosts.yml` and credential URLs | yes |
| `gh_token` | GitHub PAT (classic, scopes: repo + workflow + read:org) | yes |
| `xpander_email` | The xpander.ai user the agent operates on behalf of | optional |
| `notion_workspace` | Notion workspace label, or empty | optional |

Adding new questions: extend the `questions` list emitted in
`agent_import.sh` (search for `onboarding_required.json` in that file) and
teach this skill how to consume them.

## Cross-references

- `workspace/dev-knowledge/skills/agent_import.md` — phases 1–2 (download, verify, merge).
- `workspace/dev-knowledge/skills/agent_export.md` — explains why bundles can never carry
  these credentials in the first place (export scrubber + exclusions).
- `workspace/dev-knowledge/skills/MUST_READ.md` — universal rules every onboarded agent
  must follow.
