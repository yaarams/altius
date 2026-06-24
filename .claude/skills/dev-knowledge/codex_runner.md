# 🤖 codex_runner — Delegate Code Tasks to OpenAI Codex CLI as a Sandboxed Sub-Agent

This skill lets me (Gilfoyle) hand a self-contained coding subtask to **OpenAI
Codex CLI** as a sub-agent, while keeping it strictly fenced to repository
code. Codex can read/write inside a single `/agent/data/dev/<repo>` and run
shell commands there. It cannot see, mutate, or impersonate my skills, memory,
context, queue, or git/GitHub identity.

> **TL;DR.** Write a tight prompt → call `bash workspace/dev-knowledge/skills/codex/codex-run.sh
> <repo> <mode> <prompt-file> [model]` → review the diff → I commit + push + PR
> myself per `MUST_READ.md` §2a. Codex never commits, never pushes, never opens PRs.

## When to Use

- Self-contained code edits with clear acceptance criteria — "implement
  function X per spec at file Y", "refactor file Z to use the new helper",
  "resolve compile errors after dependency bump", "write tests for module W".
- Codebase scouting / Q&A inside a single repo (use `read` mode).
- Bulk mechanical edits across many files in one repo where I want a sub-agent
  to do the typing while I review the diff.

## When NOT to Use

- Anything that touches `workspace/dev-knowledge/skills/**`, `workspace/dev-knowledge/memory/**`,
  `workspace/local/**`, the local SQLite `task_queue`, or any xpander tool
  (Notion / email / CDN / scheduler / local DB) — those stay with me.
- Anything that crosses repos in a single run (one repo per Codex invocation).
- Anything that requires committing, pushing, tagging, opening/merging a PR,
  or otherwise mutating remote state — I keep PR ownership.
- Anything where a human signoff is needed mid-task (Codex runs in
  `--ask-for-approval=never`).
- Anything that needs network egress to package registries or external APIs
  unless the dependency cache is pre-warmed (network is **off** by default).

## Architecture (1-line)

```
Gilfoyle plans → writes prompt → bin/codex-run.sh → codex exec (sandboxed) → audit → I review diff → I commit/push/PR
```

Full architecture diagram and v3 proposal live at:
- `workspace/dev-knowledge/skills/codex/architecture/proposal_v3.md`
- `workspace/dev-knowledge/skills/codex/architecture/proposal_v3.html`
- `workspace/dev-knowledge/skills/codex/architecture/architecture_v3.png`

## Components

| Path | Purpose |
|---|---|
| `workspace/dev-knowledge/skills/codex_runner.md` | This skill — the rules. |
| `workspace/dev-knowledge/skills/codex/codex-run.sh` | Wrapper. The **only** way to invoke Codex. Enforces every guardrail. |
| `workspace/dev-knowledge/skills/codex/preflight.sh` | Self-heal preflight — sourced by the wrapper on every run. Installs codex CLI + `jq` if missing, refreshes auth, probes sandbox capability. Survives workspace scaledown / restore-from-backup. |
| `workspace/dev-knowledge/skills/codex/system_prompt.md` | Pinned system prompt prepended to every Codex prompt. |
| `workspace/tmp/codex-prompts/` | Per-run prompt files (audited; never inline). |
| `workspace/tmp/codex-runs/<ts>/` | Per-run logs: `events.jsonl`, `last_message.txt`, `usage.json`, `meta.json`, `prompt.md`, `git_status.txt`, `pre_head.txt`, `post_head.txt`. |
| `workspace/dev-knowledge/memory/codex-runs/_ledger.jsonl` | Append-only token-usage ledger across runs. |

## Prerequisites

Most of these are now **self-healing** — the wrapper sources `preflight.sh`
on every invocation, which installs/upgrades codex CLI, ensures `jq` is on
`PATH`, refreshes `auth.json`, and caches a sandbox-capability probe. The
workspace can be scaled down or restored from backup and the next wrapper
call will rebuild whatever is missing.

1. **API key + env file.** The wrapper auto-sources `workspace/dev-knowledge/memory/secrets/codex.env`
   (override path via `CODEX_ENV_FILE`). That file is `chmod 600` and holds:
   ```
   CODEX_OPENAI_API_KEY=sk-...        # forwarded to Codex as OPENAI_API_KEY only
   CODEX_DEFAULT_MODEL=gpt-5.5        # fallback when MODEL arg is omitted
   CODEX_NETWORK=1                    # 1 = allow outbound HTTPS in write mode
   ```
   Parent agent's own `OPENAI_API_KEY` (if any) is **not** reused — keep them
   separate so a compromised Codex cannot escalate. The secrets file lives in
   `workspace/dev-knowledge/memory/secrets/` (NOT under `workspace/dev-knowledge/skills/`) so `agent_export`
   STRICT mode never bundles it. **This is the only thing the operator must
   provide manually**; preflight handles the rest.
2. **Codex CLI installed.** Auto-installed by `preflight.sh` into
   `/agent/data/.persist/npm/bin/codex` (npm-global on the persistent volume).
   Pinned via `CODEX_PINNED_VERSION` env (default **0.128.0**); preflight
   reinstalls when missing or version mismatches. Manual override:
   `CODEX_PINNED_VERSION=0.129.0 bash codex-run.sh ...`.
3. **Codex CLI logged in.** Preflight refreshes `~/.codex/auth.json` from
   `CODEX_OPENAI_API_KEY` whenever the file is missing or the stored key
   doesn't match. Codex 0.128's WSS handshake to `/v1/responses` reads
   `auth.json` (env-var-only auth produces 401). `HOME` is pinned to
   `/agent/data/.home` so `auth.json` survives session restarts.
4. **`jq` available.** Used to parse JSONL events. Preflight tries `apt-get`
   first, then falls back to a static binary download from the jq GitHub
   releases (`jq-linux-amd64` / `jq-linux-arm64`) into `/agent/data/.persist/bin/`.
5. **Sandbox capability probe.** Preflight runs `codex sandbox linux -- /bin/sh -lc 'true'`
   to detect whether the kernel allows `bwrap` to create user namespaces.
   Result is cached at `~/.codex/.preflight/sandbox_mode` for 1h. In our
   Kubernetes pods unprivileged user namespaces are blocked, so the probe
   returns `bypass` and the wrapper switches to
   `--dangerously-bypass-approvals-and-sandbox` (the workspace itself is the
   external sandbox; the wrapper's perimeter — env redaction, `--cd`,
   `--ignore-rules`, `--ignore-user-config`, `--ephemeral`, post-run audit,
   HEAD-moved check, cross-repo dirty-tree check, and the strengthened
   system_prompt — is the actual policy boundary). On any host where bwrap
   *can* create namespaces (laptop, less restrictive container), the probe
   returns `native` and the wrapper passes `-s read-only|workspace-write`
   exactly as before.
6. **Repo cloned and on the right branch** per `MUST_READ.md` §7 / §7a and
   `known_repos.md`. The wrapper requires the target dir to be a git repo but
   does NOT check the branch — that's the parent agent's job.
7. **`task_queue` row** for the parent task is `in_progress` (per
   `task_queue.md`). One Codex run = one queue task at most.

## Wrapper Contract (`workspace/dev-knowledge/skills/codex/codex-run.sh`)

```
bash workspace/dev-knowledge/skills/codex/codex-run.sh <REPO> <MODE> <PROMPT_FILE> [MODEL]
```

| Arg | Allowed values | Notes |
|---|---|---|
| `REPO` | `frontend` \| `xpander-mono` \| `xpander-sdk` \| `docs` | Resolved to `/agent/data/dev/$REPO` (overridable via `DEV_ROOT`). Allowlisted to known repos. |
| `MODE` | `read` \| `write` | `read` → `--sandbox read-only`. `write` → `--sandbox workspace-write`. No third option. |
| `PROMPT_FILE` | path | Must be readable. Copied verbatim into `LOG_DIR/prompt.md` so every run is auditable. |
| `MODEL` | `gpt-5-codex` \| `gpt-5.1-codex` \| `gpt-5.2-codex` \| `gpt-5.3-codex` \| `gpt-5` \| `gpt-5-mini` \| `gpt-5-nano` \| `gpt-5-pro` \| `gpt-5.1` \| `gpt-5.2` \| `gpt-5.2-pro` \| `gpt-5.4` \| `gpt-5.4-mini` \| `gpt-5.4-nano` \| `gpt-5.4-pro` \| `gpt-5.5` \| `gpt-5.5-pro` \| `o3` \| `o3-mini` \| `o3-pro` \| `o4-mini` | Default `$CODEX_DEFAULT_MODEL` (typically `gpt-5.5`) or `gpt-5-codex`. Allowlist prevents typos / unapproved models. |

Locked-in flags (anything unsafe here is a wrapper bug, not a user knob):

- `-C <repo>` — Codex's only logical workspace (resolved from `REPO`).
- `-s <mode>` — derived from MODE (`read-only` or `workspace-write`).
- `-c approval_policy="never"` — non-interactive. **Do not** pass
  `--ask-for-approval`; that flag does not exist in `codex exec` 0.128 and
  causes a hard arg-parse failure.
- `--ignore-user-config` — neutralises `~/.codex/config.toml` so a stale or
  malicious config can't loosen the sandbox at runtime. Auth (`~/.codex/auth.json`)
  is **not** affected by this flag, which is why the login pre-flight still works.
- `--ignore-rules` — repo-side `.rules` files cannot relax policy.
- `--ephemeral` — no session rollouts left under `~/.codex/sessions`.
- `--json` — JSONL event stream → `events.jsonl`.
- `-o <file>` — final summary → `last_message.txt`.
- `-c sandbox_workspace_write.network_access=$NETWORK_ACCESS` — `false` unless
  `CODEX_NETWORK=1` is set in `codex.env`. In `read` mode this is a no-op.
- `-c sandbox_workspace_write.writable_roots='[]'`.
- `-c sandbox_workspace_write.exclude_slash_tmp=true`.
- `-c shell_environment_policy.exclude=['XPANDER_*','GH_*','GITHUB_*','AWS_*','AGENT_*','GIT_*_NAME','GIT_*_EMAIL']`.

Forbidden flags (the wrapper itself rejects any caller wiring):
- `--dangerously-bypass-approvals-and-sandbox` — never.
- Any `--add-dir` outside the target repo — never.
- Setting `CODEX_NETWORK=1` simultaneously with `MODE=read` — no-op (sandbox is
  read-only) but still discouraged; toggle network only when a `write` run
  truly needs it (npm/pip fetch, git remote ops). Network defaults to `1` in
  the shared env file per workspace policy.

## Pre-flight Checklist (every run)

1. `task_queue` shows the right row in `in_progress`. If not, fix the queue
   first — do not delegate work that isn't queued.
2. Repo is on the correct branch per `MUST_READ.md` §7 / §7a (`develop` for
   `frontend` / `xpander-mono`, `main` for `xpander-sdk`). The wrapper does
   not enforce this; I do.
3. Working tree is clean OR I have explicit user approval for any uncommitted
   work (per `MUST_READ.md` §7a).
4. `CODEX_OPENAI_API_KEY` is set in env. `printenv CODEX_OPENAI_API_KEY | head -c 6`
   should print a non-empty prefix.
5. Prompt file exists at `workspace/tmp/codex-prompts/<run-id>.md` and starts
   with a copy/paste of `workspace/dev-knowledge/skills/codex/system_prompt.md` followed by
   the task body. Do NOT inline prompts on the command line — file-only for
   audit.
6. Capture pre-flight HEAD: `git -C /agent/data/dev/<repo> rev-parse HEAD` —
   the wrapper records this too, but I keep it in my own scratch for the
   review step.

## Standard Invocations

### Read-only scouting / Q&A

```bash
mkdir -p workspace/tmp/codex-prompts
cat workspace/dev-knowledge/skills/codex/system_prompt.md > workspace/tmp/codex-prompts/scout.md
cat >> workspace/tmp/codex-prompts/scout.md <<'PROMPT'

## Task

List the top-level packages in this monorepo and summarise their purpose in
one sentence each. Do not modify any files.
PROMPT

bash workspace/dev-knowledge/skills/codex/codex-run.sh xpander-mono read \
  workspace/tmp/codex-prompts/scout.md
```

### Write task on a feature branch

```bash
# Branch prep is MY responsibility, not Codex's.
git -C /agent/data/dev/frontend status                              # confirm clean
git -C /agent/data/dev/frontend checkout develop
git -C /agent/data/dev/frontend pull origin develop
git -C /agent/data/dev/frontend switch -c feature/develop/PRO-1234

mkdir -p workspace/tmp/codex-prompts
cat workspace/dev-knowledge/skills/codex/system_prompt.md > workspace/tmp/codex-prompts/PRO-1234.md
cat >> workspace/tmp/codex-prompts/PRO-1234.md <<'PROMPT'

## Task (PRO-1234)

<Concrete, scoped task description. Reference exact file paths. Define
acceptance criteria. Specify which lint/test commands to run.>
PROMPT

bash workspace/dev-knowledge/skills/codex/codex-run.sh frontend write \
  workspace/tmp/codex-prompts/PRO-1234.md
```

### Override the model

```bash
bash workspace/dev-knowledge/skills/codex/codex-run.sh xpander-mono write \
  workspace/tmp/codex-prompts/PRO-1234.md gpt-5
```

## Status Polling While Codex Runs

The wrapper streams JSONL to `workspace/tmp/codex-runs/<ts>/events.jsonl`. I
poll it from the parent loop — cheap, no full-context reads:

```bash
LOG=workspace/tmp/codex-runs/<ts>
wc -l "$LOG/events.jsonl"
tail -n 3 "$LOG/events.jsonl" | jq -r '.type + "  " + (.tool_call.name // .content // "")'
```

Feed the snapshot into a `think` step ("Codex is editing file X, ran tests, 4
files changed so far"). For long-running tasks, self-schedule a wake-up via
`xpschedule-create` instead of idling on the same turn.

## Result Handling (after the wrapper exits)

### Exit 0 (success, audit clean)

1. `cat workspace/tmp/codex-runs/<ts>/last_message.txt` — read Codex's final
   summary.
2. `git -C /agent/data/dev/<repo> diff --stat` — confirm scope matches the
   prompt. If anything looks unexpected, `git -C ... restore .` and re-prompt.
3. Run repo validation per its conventions (`pnpm lint`, `pnpm test`, the
   repo's `pre-commit run -a`, etc.). Fix issues myself or via another Codex
   run.
4. Read `workspace/tmp/codex-runs/<ts>/usage.json`. If `output_tokens` or
   wall-clock crossed a threshold I care about, surface it in the queue note
   and (optionally) email a milestone update to the requester.
5. I commit + push + open the PR per `MUST_READ.md` §2a (verify `gh auth`
   identity is `xpander-fullstack-generalist`, generate title/desc from the
   diff via `pr_title_description.md`).
6. `xpcomplete_agent_plan_items` for the parent plan item; append a one-line
   note to the `task_queue` row referencing the run ts and tokens.

### Exit 99 (guardrail violation)

The wrapper aborted because Codex touched something it shouldn't have, HEAD
moved, or another repo went dirty. Do NOT retry blindly.

1. Read `workspace/tmp/codex-runs/<ts>/violations.txt` (if present) and
   `events.jsonl` to see what Codex tried.
2. `git -C /agent/data/dev/<repo> restore .` to discard any partial edits in
   the target repo.
3. Verify protected paths are intact: `git -C <other-repo> status` for every
   sibling, `ls -la ~/.codex ~/.gitconfig ~/.config/gh`.
4. Capture an aha moment per `aha_moments.md` if the violation revealed a
   wrapper gap; tighten the wrapper or system prompt before any retry.
5. Replan with `xpadd_new_agent_plan_item` ("investigate Codex violation on
   <task>"). Do not silently re-attempt the same prompt.

### Exit 2 (bad args / missing prereq)

Fix the call, re-run. Common causes: REPO not allowlisted, MODE typo, prompt
file missing, `CODEX_OPENAI_API_KEY` unset, repo not a git repo.

### Other non-zero (Codex/model failure)

1. Read `events.jsonl` — look for `error` events, rate-limit signals, or model
   refusals.
2. If the model refused on safety grounds, refine the prompt (more concrete
   acceptance criteria, narrower scope) and retry.
3. If rate-limited, back off; consider switching `MODEL` to a smaller one.
4. If the run wrote partial changes, `git -C ... restore .` before retrying.

## Token Usage & Cost Reporting

The wrapper distils per-run usage into `workspace/tmp/codex-runs/<ts>/usage.json`
and appends a record to `workspace/dev-knowledge/memory/codex-runs/_ledger.jsonl`:

```jsonl
{"runs":1,"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122,"ts":"...","repo":"frontend","mode":"write","model":"gpt-5-codex","exit":0}
```

Reporting recipes:

```bash
# Total tokens this week
jq -s '
  map(select(.ts > "'$(date -u -d "7 days ago" +%Y%m%dT%H%M%SZ)'"))
  | {input: (map(.input_tokens)|add), output: (map(.output_tokens)|add), runs: length}
' workspace/dev-knowledge/memory/codex-runs/_ledger.jsonl

# Group by model
jq -s 'group_by(.model)[] | {model: .[0].model, runs: length, output_tokens: (map(.output_tokens)|add)}' \
   workspace/dev-knowledge/memory/codex-runs/_ledger.jsonl
```

Optional budget cap: `CODEX_MAX_TOKENS=N` in env. (Implementation hook — v1
records the cap in `meta.json` but does not enforce; enforcement is a planned
follow-up that watches `events.jsonl` and SIGTERMs Codex when the running
output-token total crosses N.)

## Anti-Patterns (every one of these is a violation of this skill)

- ❌ Invoking `codex exec` directly without the wrapper.
- ❌ Passing `--dangerously-bypass-approvals-and-sandbox` anywhere.
- ❌ Calling the wrapper with a `MODE` other than `read`/`write`.
- ❌ Adding `--add-dir` to widen Codex's writable root beyond the target repo.
- ❌ Re-enabling `network_access` outside an explicitly approved task variant.
- ❌ Using a model not on the wrapper allowlist.
- ❌ Letting Codex run `git commit`, `git push`, `git tag`, `gh`, or any HTTP
  call to a forge.
- ❌ Inlining prompts on the command line (always go through a prompt file).
- ❌ Reusing my agent's own `OPENAI_API_KEY` for Codex — always source
  `CODEX_OPENAI_API_KEY` separately.
- ❌ Running two Codex sessions in parallel against different repos. Single
  task at a time, mirroring `task_queue.md` discipline.
- ❌ Ignoring exit 99 and retrying the same prompt.

## Threat Model — Quick Reference

| Threat | Primary control | Secondary |
|---|---|---|
| T1: writes outside repo | `--cd <repo>` + `--sandbox workspace-write` + `writable_roots=[]` | post-run `find -newer` audit → exit 99 |
| T2: secret/identity exfil | env redaction + `shell_environment_policy.exclude` | `network_access=false` |
| T3: trojaned global install | shell tools confined to repo cwd; `~/.persist`, `~/.home` covered by audit | manual review of postinstall hooks before merging the PR |
| T4: network exfil | `network_access=false` by default | future opt-in `write+net` mode behind explicit user approval |
| T5: malicious AGENTS.md/.rules | `--ignore-rules` + system prompt overrides | repo-side `AGENTS.md` review during PR |
| T6: self-elevation via config | `--ignore-user-config` + `--ephemeral` + `~/.codex` audit | reset `~/.codex` before each run |
| T7: git/GitHub identity abuse | unset `GH_TOKEN`/`GITHUB_TOKEN` + `GIT_CONFIG_*=/dev/null` | post-run HEAD audit; I own all commits/PRs |

## Validation — Definition of Done

The skill is healthy when each of these holds:

- [ ] `bash -n workspace/dev-knowledge/skills/codex/codex-run.sh` exits 0 (syntax clean).
- [ ] `shellcheck workspace/dev-knowledge/skills/codex/codex-run.sh` passes (when shellcheck
      is available).
- [ ] Calling the wrapper with REPO=`bogus` exits 2.
- [ ] Calling the wrapper with MODE=`yolo` exits 2.
- [ ] Calling the wrapper with MODEL=`gpt-3.5` exits 2.
- [ ] Calling the wrapper without `CODEX_OPENAI_API_KEY` exits 2.
- [ ] **Smoke test (read mode)** asks Codex to enumerate files; produces no
      filesystem mutations anywhere outside `workspace/tmp/codex-runs/<ts>/`.
- [ ] **Smoke test (write mode)** appends one line to a CHANGELOG entry on a
      throwaway branch; only the target repo is dirty afterward.
- [ ] Adversarial prompt asking Codex to edit `workspace/dev-knowledge/skills/foo.md` is
      blocked: either by Codex's logical sandbox refusing, or by the post-run
      audit returning exit 99.
- [ ] Adversarial prompt asking Codex to `git commit` results in exit 99 due
      to the HEAD-moved check.
- [ ] `usage.json` and `_ledger.jsonl` both contain a record after every
      successful run.

## References

- Proposal v3 (background, threat model, decisions): `workspace/dev-knowledge/skills/codex/architecture/proposal_v3.md`
- Architecture diagram: `workspace/dev-knowledge/skills/codex/architecture/architecture_v3.png`
- Codex CLI docs: `codex --help`, `codex exec --help`.
- Related skills: `task_queue.md`, `planning_workflow.md`, `pr_title_description.md`,
  `pr_code_review.md`, `pr_code_review_fix.md`, `known_repos.md`.

## Status & Versioning

- **v1.2** (2026-05-07) — Linux-sandbox compatibility + self-heal:
  - **NEW** `workspace/dev-knowledge/skills/codex/preflight.sh`: idempotent self-heal
    sourced by the wrapper on every run. Installs missing codex CLI + `jq`,
    refreshes auth.json, probes bwrap with `codex sandbox linux -- /bin/sh -lc 'true'`,
    caches result at `~/.codex/.preflight/sandbox_mode` (TTL 1h).
  - **Wrapper** picks sandbox flags based on probe result. When the kernel
    blocks unprivileged user namespaces (the xpander Kubernetes default),
    the wrapper appends `--dangerously-bypass-approvals-and-sandbox` and
    drops `-s` so codex doesn't try to invoke bwrap. Native bwrap is still
    used wherever available (laptops, looser containers, future migration).
  - **Mid-run safety net**: post-run grep for
    `bwrap: No permissions to create a new namespace` in `events.jsonl`
    forces `CODEX_EXIT=99` and invalidates the sandbox cache. Without this,
    codex 0.128 can return exit 0 while every shell call inside the turn
    silently failed and the model fabricated output from prompt context
    (the misleading "smoke test green" claim in v1.1 was this exact bug).
  - **System prompt** strengthened: explicit no-fabrication rule ("if a
    shell command fails, report verbatim and stop — do not invent file
    contents from prior knowledge or AGENTS.md"), and the operating-environment
    paragraph now spells out that bypass mode means the rules are the only
    thing keeping codex out of trouble.
  - **End-to-end smoke** verified on `frontend` (read mode, `gpt-5.5`,
    bypass mode): codex enumerated `.github/workflows/`, ran rg/git/sed/find,
    produced a real CI map with token usage 202k in / 6.8k out, audit clean,
    HEAD unchanged. Self-heal validated by hiding `/agent/data/.persist/npm/bin/codex`
    — next preflight invocation reinstalled it via npm in ~2.4s.
  - Operator workflow unchanged: `bash workspace/dev-knowledge/skills/codex/codex-run.sh REPO MODE PROMPT_FILE [MODEL]`.
    The fallback is automatic; nothing to opt into.

- **v1.1** (2026-05-07) — first end-to-end live run; smoke test green on
  `xpander-mono` (read mode, `gpt-5.5`, exit 0). Changes vs v1:
  - Wrapper now auto-sources `workspace/dev-knowledge/memory/secrets/codex.env` for key,
    default model, and `CODEX_NETWORK` toggle.
  - Idempotent `codex login --with-api-key` pre-flight before the audit
    `.start` marker (fixes 401 on `/v1/responses` WSS handshake in 0.128).
  - Approval policy switched from non-existent `--ask-for-approval never` to
    `-c approval_policy="never"` (the v0.128 way).
  - MODEL allowlist expanded to the full GPT-5.x / GPT-5.x-codex / o3 / o4
    family (verified against `GET /v1/models`).
  - `CODEX_NETWORK=1` opt-in maps to `sandbox_workspace_write.network_access=true`
    (defaulted on per workspace policy; off in `read` mode regardless).
  - Audit allowlists transient `~/.codex/.tmp/`, `installation_id`,
    `shell_snapshots/`, `memories/`, `skills/`, `tmp/`, `log/` and uses
    `find -prune` for `tmp/codex-runs/` and `memory/codex-runs/` so the
    wrapper's own ledger writes don't trip exit 99.
  - Audit still flags any new `~/.codex/auth.json` / `config.toml` /
    `AGENTS.md` / `sessions/*` written DURING a run (pre-flight login is
    safe because it precedes the `.start` marker).
- **v1** (2026-05-07) — initial skill, derived from proposal v3.
  - Wrapper enforces REPO/MODE/MODEL allowlists, env redaction,
    `--ignore-user-config`/`--ignore-rules`/`--ephemeral`, post-run audit,
    HEAD-moved check, cross-repo dirty-tree check.
  - Token usage captured per run + appended to ledger.
  - Budget cap (`CODEX_MAX_TOKENS`) recorded but not yet enforced.

Update this file (and bump the version) whenever wrapper behaviour, allowlists,
or the system prompt change. Snapshot to `workspace/local/backups/` before
each edit per `MUST_READ.md` §5a.
