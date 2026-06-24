# 📥 Agent Import — Replicate Another Agent's Brain Into This Workspace

Mirror image of `agent_export.md`. Given a single URL pointing to a bundle
produced by `agent_export.sh` (a `.zip` for v2.0+ bundles; legacy v1 `.b64`
sidecars are still auto-detected for backwards compatibility), this skill
downloads, verifies, and merges the bundle into the current workspace —
with explicit user prompting on conflicts.

> **v2.1 — auto-auth on Phase 2.** When the bundle's manifest reports
> `auth_included: true` and the `auth/` subdir is present, Phase 2 also
> writes the bundled gh + git credentials into HOME (with proper perms),
> patches `workspace_setup.md`, and creates `agent_identity.md`. The
> recipient agent comes online as `xpander-fullstack-generalist`
> automatically — **no Phase 3 onboarding needed**. Pass `--no-auto-auth`
> (or set `IMPORT_NO_AUTO_AUTH=1`) to suppress that and fall back to the
> v2.0 onboarding flow.

---

## When to Use

- The user provides a bundle URL and says "import", "restore", "clone from", "replicate from", or similar
- Standing up a new agent that should inherit another agent's skills/memory/context
- Restoring a workspace from a snapshot bundle

---

## How It Works

The script `workspace/dev-knowledge/skills/agent_import.sh`:

1. **Downloads** the URL into a staging dir under `workspace/tmp/import_<ts>/`
2. **Auto-detects** payload type:
   - PK-magic header → zip → unzip directly
   - Base64-text → `base64 -d` → unzip
   - Anything else → abort with a clear error
3. **Verifies** integrity using `manifest.json` (sha256 every file)
4. **Plans** the merge: for each of `skills/`, `memory/`, `context/`, computes
   - new files (don't exist locally)
   - identical files (same sha256 — no-op)
   - conflicts (same path, different content)
5. **Reports** the plan as JSON (dry-run) or applies it (mode-driven)
6. **Applies** in one of these modes:
   - `merge` — add new files, keep local versions of conflicts (safe default)
   - `overwrite-conflicts` — add new files, replace conflicts with bundle versions
   - `overwrite-all` — replace every file from the bundle (dangerous)
   - `skip` — abort without changes (used to just inspect the plan)
7. Backs up replaced files to `workspace/tmp/import_<ts>/.backup/` before any overwrite
8. **Replays DB dumps** found under `memory/db/*.sql` against the local SQLite DB
   (e.g. recreates the `task_queue` table). Idempotent: the dumps use
   `CREATE TABLE IF NOT EXISTS` and `INSERT OR IGNORE`. Failures are recorded in
   `summary.db_apply.errors` but never abort the merge.
9. **Auto-applies bundled auth (v2.1+)** when `manifest.auth_included` is
   true and `auth/` exists on disk. Backs up any existing
   `~/.config/gh/hosts.yml`, `.gitconfig`, `.git-credentials`, `.netrc`
   into `workspace/tmp/import_<ts>_home_backup/` and writes the bundled
   versions with `0600`/`0644` perms. Patches
   `workspace/dev-knowledge/memory/workspace_setup.md` Git Identity block and writes
   `workspace/dev-knowledge/memory/agent_identity.md`. Reports the result under
   `summary.auth_apply`. When this step succeeds, the
   `onboarding_required.json` file is **not** emitted.

---

## Three-Phase Agent Workflow (recommended)

Because the agent has no TTY, it cannot answer interactive prompts. Use the
three-phase flow:

```bash
# Phase 1 — Dry-run: produce a JSON conflict report, no changes made
bash workspace/dev-knowledge/skills/agent_import.sh --dry-run <URL>
```

The script prints a JSON summary like:

```json
{
  "bundle": "agent_bundle_20260426T092707Z",
  "sha256_ok": true,
  "plan": {
    "skills":  {"new": 2, "identical": 8, "conflicts": 1, "conflict_paths": ["skills/MUST_READ.md"]},
    "memory":  {"new": 0, "identical": 2, "conflicts": 0, "conflict_paths": []},
    "context": {"new": 1, "identical": 0, "conflicts": 0, "conflict_paths": []}
  }
}
```

The agent then uses `xpask_for_information` to ask the user:

> "Found 1 conflict (skills/MUST_READ.md) and 3 new files. Choose: **merge**
> (keep local), **overwrite-conflicts** (use bundle for conflicts), **overwrite-all**
> (replace everything), or **skip** (cancel)?"

```bash
# Phase 2 — Apply with the user's chosen mode
bash workspace/dev-knowledge/skills/agent_import.sh --mode=overwrite-conflicts <URL>
```

For v2.0+ bundles, the merge step also writes
`workspace/tmp/import_<ts>_onboarding_required.json` (containing the
question schema for Phase 3) and the apply summary will include
`onboarding_required: true` and `onboarding_manifest: <path>`.

```bash
# Phase 3 — Onboarding (credentials & identity for v2.0+ bundles)
# After merging the files, the new agent has skills/memory/context but no
# GitHub creds, no git identity, and no agent_identity.md. Drive the
# onboarding loop documented in workspace/dev-knowledge/skills/agent_onboarding.md:
#
#   1. Read workspace/tmp/import_<ts>_onboarding_required.json
#   2. Ask each question via xpask_for_information (sensitive=true → never
#      log/echo the answer)
#   3. Save answers to workspace/tmp/onboarding_inputs.json
#   4. Apply:
bash workspace/dev-knowledge/skills/agent_import.sh --onboard \
     --inputs=workspace/tmp/onboarding_inputs.json
#   5. Delete the inputs file once the smoke tests pass.
```

The `--onboard` step writes `~/.config/gh/hosts.yml`, `~/.gitconfig`,
`~/.git-credentials`, and `~/.netrc` (with appropriate `0600`/`0644`
permissions), patches `workspace/dev-knowledge/memory/workspace_setup.md`, creates
`workspace/dev-knowledge/memory/agent_identity.md`, and runs `gh auth status` +
`git config --global --list` smoke tests. The printed summary redacts
the token. Existing credential files are backed up to
`workspace/tmp/import_<ts>_home_backup/` before being overwritten, and the
step refuses to clobber an already-onboarded home unless `--force` is set.

For sandbox / dry tests, override the home dir:

```bash
bash workspace/dev-knowledge/skills/agent_import.sh --onboard \
     --inputs=workspace/tmp/fake_inputs.json \
     --home=workspace/tmp/sandbox_home
```

See `workspace/dev-knowledge/skills/agent_onboarding.md` for the full LLM-side onboarding
runbook.

---

## Direct (non-conflict) flow

If the dry-run shows zero conflicts, the agent can apply `--mode=merge`
immediately without prompting — nothing local would be changed.

---

## CLI Reference

### File merge (Phase 1 / 2)

```
agent_import.sh [--dry-run|--mode=MODE] [--keep-staging] [--target-root DIR]
                [--no-auto-auth] [--home DIR] <URL>

MODES:
  merge                 add new files, keep local on conflict (safe)
  overwrite-conflicts   add new files, bundle wins conflicts
  overwrite-all         replace every file from bundle
  skip                  parse + verify, do nothing

FLAGS:
  --dry-run             plan only, output JSON, no changes
  --keep-staging        do not delete the staging dir after import (for debug)
  --target-root DIR     workspace root (default: workspace)
  --no-auto-auth        for v2.1 bundles: skip auto-applying auth/ into HOME
                        (falls back to onboarding_required.json + Phase 3)
  --home DIR            target HOME for the auto-auth apply
                        (default: $AGENT_HOME or /agent/data/.home)
```

### Onboarding (Phase 3)

```
agent_import.sh --onboard --inputs=<path-to-onboarding_inputs.json>
                [--home DIR] [--target-root DIR] [--force]

FLAGS:
  --inputs PATH         JSON file with answers (keys: agent_name,
                        git_user_name, git_user_email, gh_user, gh_token,
                        and optional xpander_email, notion_workspace)
  --home DIR            HOME for the credential files (default:
                        $AGENT_HOME or /agent/data/.home)
  --target-root DIR     workspace root (default: workspace)
  --force               overwrite already-onboarded credential files
                        (existing ones are backed up first)
```

Exit codes: `0` ok · `1` error · `2` integrity failure (Phase 1/2) or
`already_onboarded` without `--force` (Phase 3) · `3` no mode supplied
(dry-run completed, awaiting decision)

---

## Safety Rules

- Never silently overwrite. The default mode is `merge`.
- Always back up replaced files under `workspace/tmp/import_<ts>/.backup/`.
- Refuse to import if the bundle's sha256 verification fails.
- After import, the agent must read `workspace/dev-knowledge/skills/MUST_READ.md` to pick up
  any new conventions that just landed.
- The agent's xpander.ai profile (system instructions, goals, name, connected
  tools) is **not** part of the bundle — the agent should remind the user to
  copy those manually from the source agent's profile UI.

---

## See Also

- `workspace/dev-knowledge/skills/agent_export.md` — produces the bundles this skill consumes
- `workspace/dev-knowledge/skills/agent_onboarding.md` — the LLM-side runbook for Phase 3
- Bundle's own `REPLICATION_GUIDE.md` — step-by-step import instructions for humans
