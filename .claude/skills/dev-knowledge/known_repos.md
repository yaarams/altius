# Known Repositories — `/agent/data/dev`

This skill documents all repositories cloned in the local dev directory (`/agent/data/dev`).
Always read this before starting any code task to know what repos are available, their purpose, and their integration branch.

> **Auto-discovery command** (run to refresh state):
> ```bash
> for repo in /agent/data/dev/*/; do
>   echo "=== $(basename $repo) ==="
>   cd "$repo"
>   git remote get-url origin | sed 's|https://[^@]*@|https://|'
>   echo "Branch: $(git branch --show-current)"
>   git log --oneline -1
>   echo
> done
> ```

---

## Repositories

### 1. `frontend`

| Field | Value |
|---|---|
| **Path** | `/agent/data/dev/frontend` |
| **Remote** | `https://github.com/xpander-ai/frontend.git` |
| **Integration branch** | `develop` |
| **Tech stack** | Next.js, TypeScript, Tailwind CSS, Supabase, pnpm |
| **Purpose** | Web application — the user portal for xpander.ai platform functionality |
| **Agent guidance** | `AGENTS.md` and `CLAUDE.md` present — read before touching this repo |
| **Env sync skill** | `workspace/dev-knowledge/skills/frontend_env_sync.md` — apply when user asks to sync/update frontend `.env.local`. Backup lives at `workspace/dev-knowledge/memory/secrets/frontend.env.local`. |

---

### 2. `xpander-mono`

| Field | Value |
|---|---|
| **Path** | `/agent/data/dev/xpander-mono` |
| **Remote** | `https://github.com/xpander-ai/xpander-mono.git` |
| **Integration branch** | `develop` |
| **Tech stack** | Monorepo (multiple services, packages, and platform infrastructure) |
| **Purpose** | Core monorepo for the xpander.ai platform — all backend services, packages, and infrastructure |
| **Agent guidance** | Check for `AGENTS.md` / `CLAUDE.md` at root and in each package before working |
| **Env sync skill** | `workspace/dev-knowledge/skills/frontend_env_sync.md` (covers both repos) — apply when user asks to sync/update mono `.env` files. Backup tree at `workspace/dev-knowledge/memory/secrets/xpander-mono/`. |
| **Venv skill** | `workspace/dev-knowledge/skills/xpander_mono_venv.md` — single root `.venv`, bootstrap via `createEnvironment.sh` fed through stdin (`printf 'y\nall\n' \| bash createEnvironment.sh`). |

---

### 3. `xpander-sdk`

| Field | Value |
|---|---|
| **Path** | `/agent/data/dev/xpander-sdk` |
| **Remote** | `https://github.com/xpander-ai/xpander-sdk.git` |
| **Integration branch** | `main` |
| **Tech stack** | Python 3.9+, pip, pytest |
| **Purpose** | The xpander.ai Python SDK — agent management, task execution, tools repository, knowledge bases, event-driven decorators |
| **Published** | [`xpander-sdk` on PyPI](https://pypi.org/project/xpander-sdk/) |
| **Agent guidance** | Check for `AGENTS.md` / `CLAUDE.md` before working |

> ⚠️ **Note**: `xpander-sdk` uses `main` as integration branch (not `develop`). Branch convention: `feature/main/{ticket}`, `fix/main/{ticket}`, `chore/main/{ticket}`.

---

### 4. `docs`

| Field | Value |
|---|---|
| **Path** | `/agent/data/dev/docs` |
| **Remote** | `https://github.com/xpander-ai/docs.git` |
| **Integration branch** | `main` |
| **Tech stack** | Mintlify (MDX), Node.js, npm |
| **Purpose** | Public documentation for xpander.ai — `https://docs.xpander.ai`. Authored as MDX pages plus a single `api-reference/openapi.json` that drives all auto-generated REST API reference pages. |
| **Build commands** | `npm install` then `npm run dev` (Mintlify dev server, port 3000), `npm run build` (production build / link & MDX validation), `npm run preview` (local prod preview). Always run `npm run build` before opening a PR — it is the closest equivalent to the deploy-time validator and surfaces broken links / bad MDX / OpenAPI schema issues. |
| **OpenAPI spec** | `api-reference/openapi.json` — single source of truth for REST endpoints. Each `*.mdx` under `api-reference/v1/**` references one operation via the front-matter `openapi: "<METHOD> /path"` directive. To add/update an endpoint, update the JSON spec **and** the corresponding `.mdx`. |
| **Agent guidance** | No `AGENTS.md` / `CLAUDE.md`. Follow `README.md` and Mintlify component conventions (`<ParamField>`, `<ResponseField>`, etc.). Prefer editing the OpenAPI spec for schema/parameter changes; use the `.mdx` body for prose, examples, and use cases. |

> ⚠️ **Note**: `docs` uses `main` as the integration branch. Branch convention: `feature/main/{ticket}`, `fix/main/{ticket}`, `chore/main/{ticket}`.

---

## ⚠️ Integration Branch Quick Reference (MANDATORY)

| Repo | Start every new task from | Branch naming |
|---|---|---|
| `frontend` | **`develop`** | `{fix|feat|chore}/develop/{ticket}` |
| `xpander-mono` | **`develop`** | `{fix|feat|chore}/develop/{ticket}` |
| `xpander-sdk` | **`main`** | `{fix|feat|chore}/main/{ticket}` |
| `docs` | **`main`** | `{fix|feat|chore}/main/{ticket}` |

> Always `git checkout <integration-branch> && git pull origin <integration-branch>` before creating any feature/fix/chore branch.
>
> **Exception — Continuing existing work**: If the user references an existing PR or branch, check it out directly and continue on it. Do NOT reset to the integration branch.

---

## Rules When Working With These Repos

1. **Always branch from the integration branch** (`develop` for frontend/xpander-mono, `main` for xpander-sdk)
2. **Never push directly to `main` or `develop`** — all changes via PR
3. **Read `AGENTS.md` / `CLAUDE.md`** in the repo root (and relevant subdirs) before writing any code
4. **Run pre-commit / lint / tests** as defined in each repo before committing
5. **Update this skill** whenever a new repo is cloned into `/agent/data/dev`
