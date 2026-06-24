# codex_runner — Skill Proposal (DRAFT, not yet created)

## Status
- **State**: drafting — proposal only, no skill file created yet
- **Owner**: Gilfoyle (xpander.ai dev agent)
- **Requested by**: moriel@xpander.ai
- **Created**: 2026-05-07
- **Last updated**: 2026-05-07 12:05 Asia/Jerusalem (v3 — explicit identity rules + token usage capture + configurable model)
- **Ticket**: not assigned — please open one if we move to implementation (e.g. `PRO-XXXX`)
- **Related artifacts**: architecture diagram (Mermaid + PNG, link in cover email)

## Context
User ask (verbatim):
> install Codex, OpenAI Codex CLI, and research it and investigate how to use it programmatically. So you will learn how to use it for coding tasks by making sure that it follows your instructions and your guidelines and guardrails and your skills and everything. And he cannot touch, alter, or change your settings or your skills. It can only work with code and run commands and such things. I want you to learn about it and how you can do this and propose me a new skill, but don't create it yet.

Intent — let me (Gilfoyle) **delegate self-contained coding subtasks** to OpenAI Codex CLI as a sub-agent inside my own workspace, while keeping it strictly fenced to repository code: it can read/write inside `/agent/data/dev/<repo>` and run shell commands there, but it must NOT see, mutate, or impersonate my skills/memory/context/queue.

## Research / Findings — Codex CLI 0.128.0

**Install**: `npm i -g @openai/codex` → binary at `/agent/data/.persist/npm/bin/codex` (verified, persisted across sessions).

**Auth**: `codex login` (device-code OAuth) OR `OPENAI_API_KEY` env var OR `printenv OPENAI_API_KEY | codex login --with-api-key`. Currently no key in env — adding one is a prerequisite when we move to implementation.

**Subcommands relevant to programmatic use**:
| Cmd | Purpose |
|---|---|
| `codex exec [PROMPT]` | Non-interactive run. Returns when the model finishes. Primary delegation surface. |
| `codex review` | Code-review-only run against current repo. |
| `codex sandbox linux -- <cmd>` | Run a single bare command under Landlock+seccomp (no model). Useful for guarded shell wrappers. |
| `codex mcp-server` | Expose Codex itself as an MCP server (potential future xpander integration). |
| `codex apply` | Apply latest produced diff via `git apply`. |

**`codex exec` flags I will rely on** (verified from `codex exec --help`):
- `-C, --cd <DIR>` — working root, the only directory Codex *thinks* of as its workspace.
- `-s, --sandbox <read-only|workspace-write|danger-full-access>` — model-side write policy.
- `-a, --ask-for-approval <untrusted|on-request|never>` — when escalation is allowed.
- `--add-dir <DIR>` — whitelist additional writable roots (we will ALWAYS pass empty / curated allowlist).
- `--ignore-user-config` — refuse `~/.codex/config.toml` so user config can't loosen our policy at runtime.
- `--ignore-rules` — refuse `.rules` execpolicy files inside the target repo (Codex normally lets repos relax policy via these — we suppress that).
- `--ephemeral` — do not persist session rollout files in `~/.codex` (no chat history left behind).
- `--json` — JSONL event stream to stdout (machine-readable progress + tool calls).
- `-o, --output-last-message <FILE>` — final natural-language summary.
- `--skip-git-repo-check` — needed only if we ever target a non-git directory; we will normally NOT pass this.
- `--dangerously-bypass-approvals-and-sandbox` — **forbidden by skill**, wrapper must reject it.
- `--enable/--disable <FEATURE>` — feature-flag toggles; locked to a curated allowlist.
- `-c key=value` runtime overrides — locked to a curated allowlist.

**Sandbox knobs** (`~/.codex/config.toml` keys, also overridable with `-c`):
- `sandbox_mode = "read-only" | "workspace-write" | "danger-full-access"`
- `sandbox_workspace_write.network_access` (bool) — default off; we keep it off unless task needs network.
- `sandbox_workspace_write.writable_roots` (string[]) — extra writable paths. We default to `[]`.
- `sandbox_workspace_write.exclude_slash_tmp`, `exclude_tmpdir_env_var` — tighten further by removing `/tmp` from writable roots when not needed.
- `shell_environment_policy.exclude` (string[]) — glob patterns of env vars to strip before running shell tools. We use this to redact xpander-specific secrets.

**Linux sandbox backend caveat (this workspace)**:
- Kernel: 6.12, `CONFIG_SECURITY_LANDLOCK=y` → Landlock available.
- `bwrap` (bubblewrap) is **not installed** AND unprivileged user namespaces are disabled (`bwrap: No permissions to create a new namespace`).
- Effect: `codex sandbox linux` and `codex exec`'s in-process kernel sandbox cannot fully engage. Codex still enforces its **logical** sandbox (path checks in the Rust runtime around `apply_patch` and tool calls), but kernel-level filesystem isolation is unavailable in this container.
- Mitigation: the **wrapper script is the real policy enforcer** — see Threat Model and Wrapper Spec below. Codex's own sandbox is treated as defense-in-depth, not the primary control.

**Files Codex reads automatically**:
- `~/.codex/config.toml` (suppressed via `--ignore-user-config`).
- `~/.codex/AGENTS.md` (global) — we will NOT place one; user-level guidance must come from the per-run pinned prompt.
- `<cwd>/AGENTS.md` and nested `AGENTS.md` files inside the repo — Codex follows these as repo-specific instructions. **Good**: we want Codex to honour the repo's own `AGENTS.md` (e.g. `frontend/AGENTS.md`) so the sub-agent inherits the same conventions I do per `MUST_READ.md` §8.
- `.rules` files inside the repo (suppressed via `--ignore-rules` to prevent a malicious or stale repo file from loosening sandbox policy mid-run).

## Threat Model — What “cannot touch my settings” means concretely

Assets to protect, ordered by sensitivity:
1. `workspace/dev-knowledge/skills/**` — my behaviour. Tampering = silent policy change.
2. `workspace/dev-knowledge/memory/**` — my decisions/lessons. Tampering = corrupted continuity.
3. `workspace/local/**` — plans/specs. Tampering = wrong implementation downstream.
4. `task_queue` (local SQLite) — my work-tracking spine.
5. `~/.codex/config.toml`, `~/.codex/sessions/**` — if Codex itself can rewrite these, a future run could be quietly relaxed.
6. `~/.config/gh/hosts.yml` — my GitHub identity.
7. `~/.gitconfig` — my commit identity.
8. xpander runtime env vars (`XPANDER_*`, agent token, OPENAI_API_KEY of the host).

Threats Codex could (naïvely) pose:
- **T1**: Model writes/patches files outside the target repo (e.g. modifies `workspace/dev-knowledge/skills/foo.md`).
- **T2**: Model runs shell commands that exfiltrate or rewrite secrets/identity files.
- **T3**: Model installs packages globally that ship trojaned hooks (npm postinstall, pip).
- **T4**: Model uses network egress to leak repo contents or my prompts.
- **T5**: A malicious `AGENTS.md` / `.rules` already inside the cloned repo loosens Codex's policy mid-run.
- **T6**: Codex writes to its own session/config and quietly self-elevates next run.
- **T7**: Codex impersonates me on git/GitHub via inherited credentials.

## Wrapper Spec — `bin/codex-run.sh` (lives in workspace, owned by skill)

The skill's enforcement core. Codex is **never invoked directly**; only via this wrapper. Pseudocode:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ---- args ----
REPO="$1"          # e.g. frontend | xpander-mono | xpander-sdk
MODE="$2"          # one of: read | write
PROMPT_FILE="$3"   # path to prompt; never inline so we audit prompts
shift 3
EXTRA_ALLOWED_DIRS=("$@")  # optional, must each pass repo-relative check

# ---- canonicalize + allowlist repo ----
DEV_ROOT=/agent/data/dev
case "$REPO" in frontend|xpander-mono|xpander-sdk|docs) ;; *) echo "REPO not allowlisted: $REPO" >&2; exit 2;; esac
REPO_DIR="$DEV_ROOT/$REPO"
[[ -d "$REPO_DIR/.git" ]] || { echo "$REPO_DIR is not a git repo" >&2; exit 2; }

# ---- mode → sandbox + approval ----
case "$MODE" in
  read)  SANDBOX=read-only       APPROVAL=never ;;
  write) SANDBOX=workspace-write APPROVAL=never ;;
  *) echo "MODE must be read|write" >&2; exit 2 ;;
esac

# ---- pre-flight: snapshot timestamps for audit ----
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG_DIR="workspace/tmp/codex-runs/$TS"
mkdir -p "$LOG_DIR"
touch "$LOG_DIR/.start"   # marker for `find -newer`

# ---- redact env: only what Codex needs ----
export HOME=/agent/data/.home
unset XPANDER_API_KEY XPANDER_AGENT_ID XPANDER_AGENT_TOKEN GH_TOKEN GITHUB_TOKEN
export OPENAI_API_KEY="${CODEX_OPENAI_API_KEY:?CODEX_OPENAI_API_KEY must be set in skill secrets}"

# ---- run codex with locked flags ----
codex exec \
  --cd "$REPO_DIR" \
  --sandbox "$SANDBOX" \
  --ask-for-approval "$APPROVAL" \
  --ignore-user-config \
  --ignore-rules \
  --ephemeral \
  --skip-git-repo-check=false \
  --json \
  --output-last-message "$LOG_DIR/last_message.txt" \
  -c sandbox_workspace_write.network_access=false \
  -c sandbox_workspace_write.writable_roots='[]' \
  -c sandbox_workspace_write.exclude_slash_tmp=true \
  -c shell_environment_policy.exclude='["XPANDER_*","GH_*","GITHUB_*","AWS_*","AGENT_*"]' \
  - < "$PROMPT_FILE" \
  | tee "$LOG_DIR/events.jsonl"

# ---- post-flight audit (defense-in-depth) ----
VIOLATIONS=$(find /agent/data/workspace /agent/data/.home/.codex /agent/data/.home/.config /agent/data/.home/.gitconfig \
               -newer "$LOG_DIR/.start" \
               ! -path "$LOG_DIR/*" \
               2>/dev/null | head -20)
if [[ -n "$VIOLATIONS" ]]; then
  echo "❌ GUARDRAIL VIOLATION: Codex modified protected paths:" >&2
  echo "$VIOLATIONS" >&2
  exit 99
fi

# ---- repo-side check: only the target repo should be dirty ----
git -C "$REPO_DIR" status --porcelain > "$LOG_DIR/git_status.txt"
for other in "$DEV_ROOT"/*/.git; do
  od="${other%/.git}"
  [[ "$od" == "$REPO_DIR" ]] && continue
  if [[ -n "$(git -C "$od" status --porcelain 2>/dev/null)" ]]; then
    echo "❌ GUARDRAIL VIOLATION: $od has uncommitted changes after Codex run" >&2
    exit 99
  fi
done

echo "✅ codex-run complete. Logs: $LOG_DIR"
```

Key properties:
- **Allowlist-driven**: REPO must be one of the known repos from `known_repos.md`.
- **Mode-driven**: only `read` (read-only) or `write` (workspace-write). No third option, no `danger-full-access`.
- **Network off by default**: outbound network blocked unless an explicit subcommand variant is added later.
- **Env redaction**: xpander/GH/AWS/agent vars stripped before exec. Only `OPENAI_API_KEY` (sourced from a dedicated secret) is exposed.
- **Config locked**: `--ignore-user-config` + `--ignore-rules` neutralise T5/T6.
- **No persistence**: `--ephemeral` so Codex leaves no rollouts behind.
- **JSONL audit log**: every model action is captured in `workspace/tmp/codex-runs/<ts>/events.jsonl`.
- **Post-run filesystem audit** (`find -newer`) directly addresses T1, T2, T6 even if Codex's kernel sandbox cannot engage (bwrap absent).
- **Cross-repo audit**: any other repo dirty after the run ⇒ fail loudly.

## Threat → Control mapping

| Threat | Primary control | Secondary control |
|---|---|---|
| T1 writes outside repo | `--cd <repo>` + `--sandbox workspace-write` + `writable_roots=[]` | post-run `find -newer` audit |
| T2 secret/identity exfil/rewrite | env redaction + protected-path audit | `network_access=false` |
| T3 trojaned global install | shell tools confined to repo cwd; `npm/pip` global writes blocked by audit on `/agent/data/.persist`, `/agent/data/.home` | manual review of new postinstall hooks during PR |
| T4 network exfil | `network_access=false` by default | optional explicit `--mode write+net` variant gated behind user approval (future) |
| T5 malicious AGENTS.md/.rules | `--ignore-rules`; pinned system prompt overrides repo-side AGENTS.md when conflicting | code review of repo `AGENTS.md` before first delegation |
| T6 self-elevation via config | `--ignore-user-config` + `--ephemeral` + audit on `~/.codex/**` | reset `~/.codex` before each run (`rm -rf ~/.codex/sessions ~/.codex/config.toml`) |
| T7 git/GitHub identity abuse | unset `GH_TOKEN`/`GITHUB_TOKEN`; Codex runs without push capability; **no `gh auth` token in Codex env** | I (Gilfoyle) handle ALL commits/pushes/PRs from outside the wrapper; Codex only edits files |

## Skill Outline — `workspace/dev-knowledge/skills/codex_runner.md` (NOT YET CREATED)

The skill file, when we create it, will contain:

1. **When to use** — self-contained code edits where:
   - The change is well-specified (clear acceptance criteria + repo + branch).
   - It does not require xpander-runtime-aware reasoning (those stay with me).
   - It does not need to touch workspace/skills, memory, plans, or external services.
   - Examples: “implement function X per spec in <file>”, “refactor file Y to use the new helper”, “write tests for Z”, “resolve compile errors after dependency bump”.
2. **When NOT to use** — anything touching skills/memory/queue/identity, anything cross-repo, anything requiring my Notion/email/CDN tools, anything multi-PR, anything where a human signoff is required mid-task.
3. **Pre-flight checklist** — (a) `task_queue` shows the right `in_progress` task, (b) repo on the correct branch (per `MUST_READ.md` §7), (c) `CODEX_OPENAI_API_KEY` is set, (d) the prompt file exists in `workspace/tmp/codex-prompts/<run-id>.md`.
4. **Pinned system prompt** — prepended to every Codex run, in `workspace/dev-knowledge/skills/codex/system_prompt.md`, including:
   - You operate inside a wrapper-controlled cwd. Do NOT attempt to read/write outside this cwd.
   - You are NOT allowed to commit, push, or open PRs. Stop after producing the change.
   - Honor the repo's `AGENTS.md` and any nested ones. If conflicting with this prompt, this prompt wins.
   - Output a final summary listing every file you changed.
5. **Standard invocations** — documented one-liners for `read` (codebase scouting/Q&A) and `write` (apply changes).
6. **Result handling** — wrapper logs at `workspace/tmp/codex-runs/<ts>/`. After a successful run I (Gilfoyle) review `git diff`, run validations per repo conventions, then commit/push/PR myself per `MUST_READ.md` §2a.
7. **Failure modes** — how to react to exit 99 (guardrail violation), exit 2 (bad args), non-zero exit from Codex (model failure / rate limit). Each maps to a deterministic recovery (e.g. revert via `git restore`, re-prompt, escalate).
8. **Anti-patterns** — never bypass wrapper, never set `--dangerously-bypass-approvals-and-sandbox`, never re-enable `network_access` without an approved task, never let Codex commit on my behalf.
9. **Validation hooks** — the wrapper invokes the repo's standard checks afterward (`pnpm lint`, `pnpm test`, `pre-commit run -a`, etc.) inside the same sandbox, captured to `workspace/tmp/codex-runs/<ts>/validation.log`.
10. **Audit & retention** — runs older than 14 days pruned by a sweep run; key runs archived under `workspace/dev-knowledge/memory/codex-runs/<ticket>/<ts>/`.

## Operating Model — Orchestration Loop

Codex is **never** treated as a black box that swallows the whole task. It runs as one *step* in my own plan, and I retain control before, during, and after every invocation.

```
For each plan item P that needs Codex help:
  think(P)                              ← reason about prompt + acceptance criteria
  write workspace/tmp/codex-prompts/P.md
  start = now(); spawn:
      bin/codex-run.sh <repo> <mode> <prompt> | tee events.jsonl
  while running:
      tail -F events.jsonl                ← stream JSONL
      every N events / T seconds:
          status = parse_jsonl(events.jsonl)
          think(status)                   ← progress reflection
          if user_visible_milestone: email/notion update
          if budget_exceeded or stuck: kill + analyze
  on exit:
      analyze(exit_code, last_message, audit)
      if exit==0 and audit==clean:
          xpcomplete_agent_plan_items([P.id])
          append note to task_queue
      else:
          replan: add follow-up plan item, log decision in MD
final: review diff, run repo validation, commit + push + PR (me, not Codex)
```

### Tool calls I emit around every Codex run

| Phase | Tools |
|---|---|
| Pre-flight | `think` ("is this scoped right?"), `xpworkspace-file-write` (prompt file), `xpget_agent_plan` |
| In-flight (every checkpoint) | `xpworkspace-bash` `tail`/`wc -l events.jsonl`, `think` (status reflection), optional email for milestone updates |
| Post-flight (success) | `analyze`, `xpcomplete_agent_plan_items`, `xpworkspace-local-db-run-query` (queue note), `xpworkspace-bash` `git -C <repo> diff --stat` |
| Post-flight (failure) | `analyze`, `xpadd_new_agent_plan_item` (replan), `xpworkspace-bash` `git -C <repo> restore .` |

### Status checking pattern

The wrapper writes JSONL to `workspace/tmp/codex-runs/<ts>/events.jsonl`. While Codex is running I poll it from my parent loop:

```bash
# Cheap progress probe — last 3 events + line count
LOG=workspace/tmp/codex-runs/<ts>
wc -l "$LOG/events.jsonl"
tail -n 3 "$LOG/events.jsonl" | jq -r '.type + "  " + (.tool_call.name // .content // "")'
```

I feed the parsed snapshot into a `think` step ("Codex is on file X, just ran tests, 4 files changed so far") and reflect to the user via email when it is a milestone (tests green, refactor done, blocker hit). The wrapper itself never talks to me — reflection is always the parent agent’s job, using the same tools I use for any other work.

### Plan tracking discipline

- Each Codex `exec` corresponds to **exactly one** plan item (from `xpcreate_agent_plan` or added mid-flight via `xpadd_new_agent_plan_item`).
- I call `xpcomplete_agent_plan_items` only after the wrapper exits 0 *and* the audit passed *and* the diff matches expected scope.
- A failed run becomes a new plan item ("investigate Codex failure on P") plus a `notes` append to the queue row — never silently retried without acknowledgement.
- Long-running tasks self-schedule a wake-up via `xpschedule-create` if I want to re-check status after the current turn ends (avoids burning a turn idle-watching).

### High-level operating model

```
User request → Gilfoyle plans + grooms task
             ↓
  Decision: Is the next subtask self-contained code work?
             ↓ yes                                     ↓ no
   Write a tight prompt file under                  Do it myself with workspace tools
   workspace/tmp/codex-prompts/<id>.md
             ↓
   Invoke bin/codex-run.sh <repo> write <prompt>
             ↓ (orchestration loop above)
   Wrapper audits filesystem + cross-repo state
             ↓
   Gilfoyle reviews diff, runs repo validation, commits/pushes/PRs as the agent identity
             ↓
   Outcome logged under workspace/dev-knowledge/memory/codex-runs/<ticket>/<ts>/
```

I remain the **only entity** that:
- Talks to xpander tools (Notion/email/CDN/scheduler/local DB).
- Touches `workspace/**`.
- Signs commits and opens PRs.
- Updates the task queue and execution plan.

Codex is a **specialised hand**: it edits code in one repo and runs that repo's commands. Nothing else.

## Smoke Test (post-implementation)

Once skill is created and `CODEX_OPENAI_API_KEY` is set:

```bash
# 1. Read-only scouting
echo "List the top-level packages and summarise their purposes." \
  > workspace/tmp/codex-prompts/smoke-read.md
bin/codex-run.sh xpander-mono read workspace/tmp/codex-prompts/smoke-read.md

# 2. Verify no protected paths were touched
find /agent/data/workspace -newer workspace/tmp/codex-runs/*/.start ! -path '*/codex-runs/*' | head
# Expected: empty

# 3. Tiny write change (e.g. edit a CHANGELOG entry on a throwaway branch)
echo "Add a line '- chore: codex smoke test' under 'Unreleased' in CHANGELOG.md, nothing else." \
  > workspace/tmp/codex-prompts/smoke-write.md
git -C /agent/data/dev/xpander-mono switch -c chore/develop/codex-smoke
bin/codex-run.sh xpander-mono write workspace/tmp/codex-prompts/smoke-write.md
git -C /agent/data/dev/xpander-mono diff --stat
# Expected: only CHANGELOG.md modified
```

A failed smoke test (any modified file under `workspace/**`, `~/.codex/**`, `~/.config/**`, or another repo) blocks rollout.

## Out of Scope (this proposal)
- Streaming Codex events into the xpander activity log (would need a small adapter; deferred until skill v1 is stable).
- Exposing my agent as an MCP server to Codex via `codex mcp` (interesting but inverts the trust direction; out of scope for v1).
- Running multiple Codex agents in parallel — one repo / one Codex run at a time, mirroring the single-task queue discipline in `task_queue.md`.
- Letting Codex use `gh` / commit / push (deliberately denied; I keep PR ownership).

## Validation (definition of done for the future skill PR)
- [ ] `bin/codex-run.sh` exits 99 when run with a prompt that asks Codex to write outside `--cd`.
- [ ] Wrapper exits 99 if `~/.codex/config.toml` or `~/.codex/sessions/**` are touched mid-run.
- [ ] Wrapper exits 2 on disallowed REPO or MODE values.
- [ ] `--ignore-user-config` + `--ignore-rules` confirmed in invocation; checked via `--json` events showing the resolved policy.
- [ ] Read mode produces no filesystem mutations anywhere.
- [ ] Write mode produces mutations only inside `/agent/data/dev/<REPO>`.
- [ ] Network egress blocked unless an explicit allowlisted task variant is invoked.
- [ ] Smoke tests above pass on `frontend`, `xpander-mono`, and `xpander-sdk`.

## Open Questions (for moriel@xpander.ai)
1. **API key plumbing**: do we mount `CODEX_OPENAI_API_KEY` via xpander secrets, or pull from a managed secret in `workspace/dev-knowledge/memory/secrets/`? (Latter is simpler; former is cleaner long-term.)
2. **Network policy**: do you want a curated `write+net` mode for tasks that need `npm install` / pre-commit fetches, or do we always pre-warm the dependency cache outside Codex?
3. **Model default**: pin to `gpt-5-codex` (the default newer model) or let me choose per task? Cost/latency tradeoff.
4. **Budget caps**: should the wrapper enforce a max wall-clock or token budget per run (Codex doesn't expose token caps directly; we'd time-box via `timeout` and parse tokens from the JSONL summary)?
5. **Ticket convention**: do we want each Codex-assisted change in its own ticket (`PRO-XXXX-codex`), or rolled into the parent ticket?

## v3 Update — Identity, Token Usage, Configurable Model

After v2 you asked for three concrete tightenings. All three are folded into the wrapper + skill spec below.

### 1. Commits / branches / PRs are *exclusively* mine

Codex is a **read+edit hand**. It never:
- runs `git commit`, `git push`, `git switch -c`, `git tag`, or any history-mutating git verb,
- invokes the `gh` CLI, GitHub REST/GraphQL endpoints, or any auth’d HTTP that could open a PR,
- writes to `~/.gitconfig`, `~/.config/gh/**`, or any auth file.

Enforcement layers (defense-in-depth):

| Layer | Mechanism |
|---|---|
| Env redaction | wrapper `unset GH_TOKEN GITHUB_TOKEN GH_HOST GIT_AUTHOR_* GIT_COMMITTER_*` before `exec`; `shell_environment_policy.exclude=["GH_*","GITHUB_*","GIT_*_NAME","GIT_*_EMAIL"]` |
| Identity scrub | wrapper exports a throwaway `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_SYSTEM=/dev/null` so any `git commit` Codex tries inside `--cd` fails with `please tell me who you are` |
| Pinned system prompt | hard line: “You MUST NOT run `git commit`, `git push`, `git switch -c`, `git tag`, `gh`, or any HTTP call to git/GitHub. Stop after producing file changes and print a final summary listing every changed file.” |
| Post-run audit | wrapper checks `git -C $REPO log -1 --format=%H` against pre-flight HEAD; if HEAD moved → exit 99. Also checks `~/.config/gh/**` and `~/.gitconfig` newer-than-start → exit 99. |
| PR ownership | I (Gilfoyle) review the working-tree diff, run repo validations, then `git commit` + `git push` + `gh pr create` from outside the wrapper, under the agent identity per `MUST_READ.md` §2a. |

### 2. Token usage capture per run

`codex exec --json` already emits a `turn.completed` event with `usage`:

```json
{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122}}
```

Wrapper additions:

```bash
# After codex exec returns, distill usage from the JSONL stream.
jq -s '
  [.[] | select(.type=="turn.completed") | .usage] as $turns
  | {
      runs: ($turns | length),
      input_tokens:        ($turns | map(.input_tokens)        | add // 0),
      cached_input_tokens: ($turns | map(.cached_input_tokens) | add // 0),
      output_tokens:       ($turns | map(.output_tokens)       | add // 0)
    }
' "$LOG_DIR/events.jsonl" > "$LOG_DIR/usage.json"

# Append to a per-task ledger so we can roll up cost across a ticket.
jq -c --arg ts "$TS" --arg repo "$REPO" --arg model "$MODEL" \
   '. + {ts:$ts, repo:$repo, model:$model}' "$LOG_DIR/usage.json" \
   >> workspace/dev-knowledge/memory/codex-runs/_ledger.jsonl
```

Resulting artefacts per run:
- `workspace/tmp/codex-runs/<ts>/usage.json` — single-run summary
- `workspace/dev-knowledge/memory/codex-runs/_ledger.jsonl` — append-only history (input/output/cached + repo + model + ts)

Reporting: a one-liner roll-up by ticket / by day / by model (`jq` group-by) gives me cost insight without extra tooling. If we ever wire up a price table, multiplying tokens × model price gives an estimated $ per run.

Optional budget cap: wrapper accepts `--max-tokens N`; after each `turn.completed` it sums `output_tokens` and SIGTERMs Codex if the running total exceeds N. Off by default; opt-in per task.

### 3. Configurable model

The wrapper takes a fourth positional arg `MODEL`, with a sane default and an allowlist:

```bash
# bin/codex-run.sh <REPO> <MODE> <PROMPT_FILE> [MODEL]
MODEL="${4:-${CODEX_DEFAULT_MODEL:-gpt-5-codex}}"
case "$MODEL" in
  gpt-5-codex|gpt-5|o4-mini|o3) ;;
  *) echo "MODEL not allowlisted: $MODEL" >&2; exit 2 ;;
esac
codex exec --model "$MODEL" ...
```

Rules:
- Default model is set in skill config (`CODEX_DEFAULT_MODEL`), overridable per call.
- Allowlist prevents typos / accidental use of expensive or unavailable models.
- Model name is recorded in `events.jsonl`, `usage.json`, and the ledger so cost reporting can group by model.
- Switching models never relaxes sandboxing — all guardrails are model-agnostic.

### Skill outline updates

Add to `workspace/dev-knowledge/skills/codex_runner.md` when we build it:
- **§3 Pre-flight checklist** — add: “record pre-flight `git rev-parse HEAD` of `<repo>` for post-run audit”.
- **§4 Pinned system prompt** — add the explicit “no commit/push/PR/gh” line.
- **§6 Result handling** — add: “read `usage.json`, append to ledger, surface tokens in the queue note, decide whether to email a milestone update if `> N` tokens or wall-clock minutes”.
- **§8 Anti-patterns** — add: “never pass a model not on the allowlist”, “never rely on Codex to commit — the audit will fail you”.

## Decisions
- 2026-05-07 — Picked `codex_runner` as skill name; wrapper at `bin/codex-run.sh`; no skill file created yet (per user instruction).
- 2026-05-07 — Wrapper is the primary policy enforcer; Codex sandbox = defense-in-depth (bwrap unavailable in this container).
- 2026-05-07 — Codex never gets `GH_TOKEN`/`GITHUB_TOKEN`/`gh` auth; commits and PRs stay with me.
- 2026-05-07 (v3) — Identity controls hardened: env redaction + `GIT_CONFIG_*=/dev/null` + pinned-prompt prohibition + post-run HEAD/auth-file audit; HEAD movement ⇒ exit 99.
- 2026-05-07 (v3) — Token usage captured per run via `jq` over `events.jsonl`; per-run `usage.json` + append-only `workspace/dev-knowledge/memory/codex-runs/_ledger.jsonl`. Optional `--max-tokens N` budget cap, off by default.
- 2026-05-07 (v3) — Model is wrapper arg #4 (default `gpt-5-codex`, allowlist `gpt-5-codex|gpt-5|o4-mini|o3`); recorded in events/usage/ledger; never relaxes guardrails.

## Next Action
Review v3 changes (this section + diagram + HTML), then either (a) confirm ‘go’ to create the skill file + wrapper under a ticket, or (b) push back on any of the three v3 controls.
