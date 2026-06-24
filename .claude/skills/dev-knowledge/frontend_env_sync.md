# Skill — Sync Repo `.env` Files on User Request

> **Scope:** `frontend` (single `.env.local`) **and** `xpander-mono` (many service `.env` files).
> File name kept as `frontend_env_sync.md` for backwards compatibility — it now covers both repos.

**Trigger phrases** (case-insensitive, any of these or close variants):
- "sync frontend env" / "update frontend .env" / "refresh frontend env"
- "set/save/install frontend .env(.local)" / "here's the .env for frontend"
- "sync mono env" / "sync xpander-mono env" / "set mono .env files"
- "here's the .env for all services" / "here are the env files for xpander-mono"
- Any request mentioning **frontend** or **xpander-mono / mono / services** + **env / .env / supabase keys / vercel env / service envs**
- User attaches a zip / link to env files

When any such request arrives, follow this skill exactly. Do NOT improvise.

---

## Why this skill exists

Both repos cannot run locally without secret env files supplied by the user:

- **`frontend`** — a single `.env.local` (Next.js + Supabase + many `NEXT_PUBLIC_*` service URLs).
- **`xpander-mono`** — ~30 `.env` files, one per service (`services/<svc>/.env`), plus `packages/xpander_dev_utils/.env`, `agent_containers_images/openclaw_scaffold/.env`, and `services/agent-controller/opentelemetry/config.env`. Loaded by `src/secrets/get_secrets.py` when `IS_XPANDER_CLOUD=false`.

We need a deterministic way to:
1. Receive fresh env files from the user (single file or zip bundle).
2. Persist them in the correct repo paths so builds/services run.
3. Persist a backup in workspace memory so they survive across sessions.
4. Guarantee they are **never committed**.

---

## Locations

### Frontend

| Purpose | Path |
|---|---|
| Active env used by builds | `/agent/data/dev/frontend/.env.local` |
| Persistent backup | `workspace/dev-knowledge/memory/secrets/frontend.env.local` |
| Repo `.gitignore` rule | `.env*.local` (line 30 of `frontend/.gitignore`) |

### xpander-mono

| Purpose | Path |
|---|---|
| Active env files (one per service + others) | `/agent/data/dev/xpander-mono/<relative-path>` (see file map below) |
| Persistent backup tree (mirrors repo structure) | `workspace/dev-knowledge/memory/secrets/xpander-mono/` |
| Repo `.gitignore` rule | `**/.env` (root `.gitignore` line 3) + per-package extras |
| Bundle reference doc (saved with backup) | `workspace/dev-knowledge/memory/secrets/xpander-mono/SETUP.md` |

**xpander-mono env file map** (31 files total — keep in sync if services are added/removed):

```
packages/xpander_dev_utils/.env
agent_containers_images/openclaw_scaffold/.env
agent_containers_images/openclaw_scaffold/.env.example   # tracked file, identical placeholder — see notes
services/a2a/.env
services/actions/.env
services/agent-controller/.env
services/agent-controller/opentelemetry/config.env
services/agent-worker/.env
services/agentic-rag/.env
services/agents/.env
services/ai-gateway/.env
services/api/.env
services/api-caller/.env
services/authenticator/.env
services/aws-operator/.env
services/bots/.env
services/catalog/.env
services/client-auth/.env
services/code-runner/.env
services/deployment-manager/.env
services/functions/.env
services/hosted-assistants-webui/.env
services/inbound/.env
services/logs/.env
services/mcp/.env
services/metrics/.env
services/monitoring/.env
services/openapi-spec-generator/.env
services/plugins/.env
services/voice/.env
services/webhook/.env
```

---

## Workflow — Frontend (single file)

### Step 1 — If env contents not provided, ask

If a plan is running, use `xpask_for_information`; otherwise ask directly:

> Please paste the full `.env.local` contents for the frontend (the block from Vercel CLI, including the Supabase URL/anon key and all `NEXT_PUBLIC_*` service URLs). I'll save it to `/agent/data/dev/frontend/.env.local`, back it up to workspace memory, and never commit it.

### Step 2 — Verify gitignore

```bash
cd /agent/data/dev/frontend && grep -E '^\.env' .gitignore
```

Must output `.env*.local`. If missing, STOP — do not write the file.

### Step 3 — Write the file (verbatim)

Use `xpworkspace-file-write` (NOT bash heredoc). Path: `/agent/data/dev/frontend/.env.local`. Preserve all comments, blank lines, and commented-out STG/LOCAL/PROD blocks exactly — the user toggles between environments by uncommenting blocks.

### Step 4 — Persist backup

```bash
mkdir -p workspace/dev-knowledge/memory/secrets
cp /agent/data/dev/frontend/.env.local workspace/dev-knowledge/memory/secrets/frontend.env.local
chmod 600 workspace/dev-knowledge/memory/secrets/frontend.env.local
```

### Step 5 — Verify ignored

```bash
cd /agent/data/dev/frontend && git check-ignore -v .env.local && git status --short
```

Both must pass: `check-ignore` prints a match, `status` does not list `.env.local`. If either fails, delete and STOP.

### Step 6 — Report (no secret values in output)

Show a short status table. Never echo env contents back.

### Step 7 — Optional rebuild

If the request implies it (e.g. "sync env and build"), run `pnpm build` from `/agent/data/dev/frontend` and report.

---

## Workflow — xpander-mono (bundle of files)

### Step 1 — If env bundle not provided, ask

> Please share the env bundle for `xpander-mono` — a zip with the `services/*/.env`, `packages/xpander_dev_utils/.env`, `agent_containers_images/openclaw_scaffold/.env`, and `services/agent-controller/opentelemetry/config.env` files (or a link to one). I'll drop them into the matching repo paths, back them up, and never commit them.

### Step 2 — Fetch and unpack the bundle

If the user supplies a URL (e.g. an `https://...storage/...zip` link), download into a temp dir; if they paste contents inline, write each file directly. Steps for the zip case:

```bash
mkdir -p workspace/tmp/mono_env && cd workspace/tmp/mono_env
curl -sSL -o envs.zip '<USER URL>'
unzip -o envs.zip -d extracted/ > /dev/null
rm -rf extracted/__MACOSX           # strip macOS metadata
find extracted -type f | sort       # confirm layout matches the file map above
```

If the bundle ships its own `SETUP.md` file map, treat it as authoritative for that bundle (re-read before copying).

### Step 3 — Verify gitignore (root + per-package)

```bash
cd /agent/data/dev/xpander-mono && grep -nE 'env' .gitignore | head -20
```

Root `.gitignore` must contain `**/.env` (or equivalent global `.env` rule). Note: `**/.env` does **not** match `.env.example` — see notes.

### Step 4 — Place files (preserve directory structure)

Use `rsync` with explicit include filters so we only place real env files (no source code, no docs):

```bash
SRC=workspace/tmp/mono_env/extracted/xpander-env-setup
DST=/agent/data/dev/xpander-mono
rsync -a \
  --include='*/' --include='.env' --include='.env.example' --include='config.env' \
  --exclude='*' \
  "$SRC/" "$DST/"
```

Do NOT manually copy file by file unless the bundle is tiny — rsync is the source of truth and avoids missed paths.

### Step 5 — Persist backup tree

```bash
BACKUP=workspace/dev-knowledge/memory/secrets/xpander-mono
mkdir -p "$BACKUP"
rsync -a \
  --include='*/' --include='.env' --include='.env.example' --include='config.env' \
  --exclude='*' \
  "$SRC/" "$BACKUP/"
find "$BACKUP" -type f -exec chmod 600 {} +
cp "$SRC/SETUP.md" "$BACKUP/SETUP.md" 2>/dev/null && chmod 644 "$BACKUP/SETUP.md" || true
```

The SETUP.md (if shipped) is preserved at 644 because it's just a file map (no secrets) and is useful for humans inspecting the backup.

### Step 6 — Verify every placed file is ignored AND git status is clean

```bash
cd /agent/data/dev/xpander-mono
# Sample a representative set across the three .gitignore rules:
git check-ignore -v \
  services/api/.env \
  services/agent-controller/opentelemetry/config.env \
  packages/xpander_dev_utils/.env \
  agent_containers_images/openclaw_scaffold/.env
# Ensure no env files appear in status (look only for env-shaped paths to ignore unrelated noise):
git status --short | grep -E '\.env(\.example)?$|config\.env$' || echo 'clean: no env files in git status'
```

All four `check-ignore` lines must show a matching rule. The grep must print `clean: ...`. If anything env-shaped appears in `git status`, **delete that file from the repo immediately** and STOP.

### Step 7 — Cleanup temp dir

```bash
rm -rf workspace/tmp/mono_env
```

### Step 8 — Report (count placed, never echo values)

Give the user a short table:

```
| Repo                       | Files placed | Backup tree                             | Gitignored | In git status |
| /agent/data/dev/xpander-mono | 31 (or N)  | workspace/dev-knowledge/memory/secrets/xpander-mono/  | ✅         | ❌            |
```

Do NOT print env contents, secret values, or service-by-service breakdowns of variables.

---

## Restoring from backup (no user input needed)

### Frontend
```bash
cp workspace/dev-knowledge/memory/secrets/frontend.env.local /agent/data/dev/frontend/.env.local
chmod 600 /agent/data/dev/frontend/.env.local
```

### xpander-mono
```bash
rsync -a \
  --include='*/' --include='.env' --include='.env.example' --include='config.env' \
  --exclude='*' \
  workspace/dev-knowledge/memory/secrets/xpander-mono/ /agent/data/dev/xpander-mono/
```

Then run the relevant verification step (Step 5 for frontend, Step 6 for mono).

---

## Hard rules

1. **Never** commit any `.env`, `.env.local`, `config.env`, or any file containing secrets. Verify via `git check-ignore` AND `git status --short` before declaring success.
2. **Never** echo env contents (or any individual secret value) back in chat. Reference user input as "the env you provided".
3. **Never** edit / reorder / "normalize" user-supplied env files — write them verbatim. Users toggle STG/LOCAL/PROD by uncommenting blocks.
4. **Never** use `xpworkspace-bash` heredoc for writes — use `xpworkspace-file-write` for inline content, `rsync` for bundles.
5. **Always** back up to `workspace/dev-knowledge/memory/secrets/...` after writing (chmod 600 on each file).
6. **Always** verify gitignore coverage AND clean `git status` before reporting success.
7. If the user supplies env contents inline in chat, treat the chat message itself as sensitive.
8. For zips: always `rm -rf __MACOSX` and verify the layout matches the file map before placing files.

---

## Notes / gotchas

- **`.env.example` is NOT covered by `**/.env`** — it can match an explicit `.env.example` rule or be tracked. In `xpander-mono` today, `agent_containers_images/openclaw_scaffold/.env.example` is **already tracked** (with placeholder values like `{YOUR_API_KEY}`); ensure the bundle's version matches via `git diff` before reporting success. If it differs, the bundle is contaminating a tracked file — STOP and surface to the user.
- **`services/agent-controller/opentelemetry/config.env`** is ignored via a per-package `.gitignore` (`services/agent-controller/opentelemetry/.gitignore: config.env`), not the root rule. Always include this path in the `git check-ignore -v` sample.
- **`packages/xpander_dev_utils/.env`** is ignored via that package's own `.gitignore`. Keep that path in the sample too.
- **K8s deploys ignore these `.env` files** — production secrets come from AWS Secrets Manager via `src/secrets/secrets.json`. Local dev only loads `.env` when `IS_XPANDER_CLOUD=false`.
- **Activate the monorepo venv** before running mono services: `source .venv/bin/activate`.
- If the user adds a new service/package and the bundle ships an env for it, **append the new path to the file map above** in this skill so future syncs cover it.

---

## Out of scope

- Generating Supabase URLs, anon keys, or any secret values yourself — always ask the user.
- Syncing env for `xpander-sdk` — that repo doesn't currently use developer-supplied `.env` files. Add a section here if/when it does.
- Editing individual variables across many services — if the user asks to change one value across all services, push back and ask them to re-share the bundle, then run the full sync.
- Pushing env files to AWS Secrets Manager — cloud secrets are managed elsewhere; this skill is for local dev only.
