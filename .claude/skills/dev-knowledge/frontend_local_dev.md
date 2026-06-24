# Skill — Frontend Local Dev + Browser Use + OTP + Screenshots

> **Scope:** running `xpander-mono/frontend` (Next.js) locally, signing in via OTP/magic
> link, driving the live UI with `bu` (browser_use CLI), and capturing feature
> screenshots for PR evidence. Consolidates lessons that previously lived only in
> chat memory across PRO-1049, PRO-1051, and the agent-wizard work.

**Trigger phrases** (case-insensitive):
- "run the frontend locally" / "spin up the FE" / "local next dev"
- "sign in to the local app" / "log in with OTP" / "get the magic link"
- "take a screenshot of the feature" / "add screenshots to the PR" / "before/after shots"
- "drive the live UI" / "open the app in the browser" / "verify the UI change"

When any of these arrive, follow this skill — don't improvise local-dev or auth flows.

> **Pair this skill with `workspace/dev-knowledge/skills/xpander_design_system.md` for any UI change.**
> That skill enforces the existing token system and gates new-token additions behind
> user approval. Never invent colors, variants, or typography sizes.

---

## Why this skill exists

Three adjacent activities that always come up together:

1. **Running the frontend** — `pnpm dev` against staging Supabase using `.env.local`.
2. **Logging in** — staging Supabase ships an **email OTP** (6-digit code), not a
   click-through magic link in this environment. The agent has no inbox; the user
   must paste the code (or redirect Supabase auth emails to a controllable address).
3. **Capturing screenshots** — every UI-affecting PR needs before/after shots
   attached. We use `bu screenshot` at a fixed 1920x1080 viewport so reviewers see
   exactly the same layout the agent produced.

Doing them ad-hoc each time leads to: stale Next caches, wrong env files, OTP
requests sent into the void, screenshots at the wrong viewport, and renderer
crashes mid-flow. This skill is the deterministic recipe.

---

## Prerequisites

- `frontend` repo cloned at `/agent/data/dev/frontend` (see `known_repos.md`).
- `.env.local` populated via `frontend_env_sync.md` skill.
- `bu` CLI on PATH (`workspace/dev-knowledge/skills/browser_use.md`). Daemon running on chromium engine.
- System fonts + fontconfig installed (see browser_use.md → Reliability fixes).

Verify in one shot:

```bash
cd /agent/data/dev/frontend
test -f .env.local && echo ".env.local OK" || echo "MISSING .env.local — run frontend_env_sync first"
which bu && bu status | jq -r '.engine // "not running"'
# Fontconfig is REQUIRED — /agents SPA crashes the renderer without it.
# See workspace/dev-knowledge/memory/browser_use_renderer_crash_fix.md (2026-05-03 addendum).
FC=$(fc-list 2>/dev/null | wc -l)
if [ "$FC" -gt 0 ] && [ -f /etc/fonts/fonts.conf ]; then
  echo "fonts OK ($FC families)"
else
  echo "FONTS MISSING — run: sudo apt-get install -y fontconfig fonts-liberation fonts-dejavu-core"
fi
```

**Confirmed 2026-05-03**: with fontconfig + 22 font families installed, login
flow `/login → /login/otp → /agents` lands cleanly with renderer alive.
Without it, /agents triggers `NOTREACHED at remote_font_face_source.cc:365`
followed by renderer crash (Stigg/Framer remote fonts).


---

## Workflow A — Spin up the dev server

```bash
cd /agent/data/dev/frontend
pnpm install --frozen-lockfile      # first time / lockfile changes
pnpm dev > workspace/tmp/frontend-dev.log 2>&1 &
echo $! > workspace/tmp/frontend-dev.pid
# Wait for the "ready" line — Next prints a port (default 3000, falls back if busy)
for i in $(seq 1 60); do
  grep -E 'Local:|ready in' workspace/tmp/frontend-dev.log && break
  sleep 1
done
LOCAL_URL=$(grep -oE 'http://localhost:[0-9]+' workspace/tmp/frontend-dev.log | head -1)
echo "FE running at $LOCAL_URL"
```

**Stop:** `kill "$(cat workspace/tmp/frontend-dev.pid)" && rm workspace/tmp/frontend-dev.pid`.

### Compile vs build vs dev — pick the right verb

| Verb | When | Cost | What it gives |
|---|---|---|---|
| `pnpm dev` | Manual UI verification, screenshots, OTP login flow | High RAM (~1–2 GB), but live | HMR, source maps, real auth |
| `pnpm compile` | CI-style type check during PR validation | Low | `tsc --noEmit` only — **safe in this environment** |
| `pnpm build` | **NEVER** in this environment | Crushes the box | Don't. (See `lessons_learned.md` → "Frontend Repo — Compile, Never Build".) |

### Stale-cache trap

If the UI shows old code after edits, kill the dev server and delete `.next/`:

```bash
kill "$(cat workspace/tmp/frontend-dev.pid)" 2>/dev/null
rm -rf /agent/data/dev/frontend/.next
# then re-run pnpm dev
```

This catches ~80% of "my change didn't apply" reports.

### Env precedence (Next.js)

Next loads in this order (later wins): `.env` → `.env.local` → `.env.<NODE_ENV>` → `.env.<NODE_ENV>.local`.
`NEXT_PUBLIC_*` vars are baked at **build time**; changes require a dev-server restart
(HMR does NOT pick up env changes). Always restart after editing `.env.local`.

---

## Workflow B — Sign in via OTP

**Important reality:** xpander.ai staging uses Supabase's **email-OTP** flow:
the user enters their email, Supabase sends a 6-digit numeric code, and the user
types it on the next screen. The agent **cannot read the user's inbox**. There
are three viable paths:

### Path 1 — Paste-event injection into the 6-cell form ⭐ **PROVEN 2026-05-03 (PRO-1111)**

xpander.ai's `OTPVerification` component renders **six** `<input maxLength={1} inputmode="numeric">` cells with an `onPaste` handler on the wrapper that splits pasted text into digits and fills all cells in one shot. The auto-submit `useEffect` then fires `verifyOTP(...)` the moment the joined string reaches length 6.

**Paste-event injection is the cleanest path** — single `bu eval` call, no per-cell typing, no focus juggling.

#### Recipe (verified end-to-end against `localhost:3000` on 2026-05-03)

```bash
EMAIL='moriel+devagent1@xpander.ai'   # standard test email per Moriel

# 1. Drive to /login (route is /login; OTP screen is /login/otp NOT /login/with-otp)
bu navigate "$LOCAL_URL/login"
bu type 'input#email' "$EMAIL"
bu screenshot workspace/tmp/screenshots/${TICKET}/01-login-email-filled.png

# 2. Submit. Cloudflare Turnstile in 'managed' mode passes silently for headless
bu click 'button[type=submit]'
sleep 4   # Supabase round-trip + redirect

# 3. Confirm OTP screen (path is /login/otp, not /login/with-otp)
bu eval 'JSON.stringify({path:location.pathname,otpInputs:document.querySelectorAll("input[maxlength=\"1\"][inputmode=\"numeric\"]").length})'
# expect: {"path":"/login/otp","otpInputs":6}
bu screenshot workspace/tmp/screenshots/${TICKET}/02-otp-prompt.png

# 4. Ask the user for the code (xpask_for_information). Codes expire in ~5 min —
#    stage UI BEFORE asking; submit IMMEDIATELY on receipt.

# 5. Inject via simulated paste event. Write JS to a file to avoid bash escape hell.
cat > workspace/tmp/otp-inject.js <<'JS'
(() => {
  const code = '__CODE__';
  const cells = document.querySelectorAll('input[maxlength="1"][inputmode="numeric"]');
  if (cells.length !== 6) return JSON.stringify({ok:false, err:'expected 6 cells, got ' + cells.length});
  const wrapper = cells[0].parentElement;
  const dt = new DataTransfer();
  dt.setData('text', code);
  wrapper.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
  return JSON.stringify({ok:true, cells: cells.length});
})()
JS
sed -i "s/__CODE__/${OTP_CODE}/" workspace/tmp/otp-inject.js
JS=$(cat workspace/tmp/otp-inject.js); bu eval "$JS"
# expect: {"ok":true,"cells":6}
```

#### Verification (don't rely on `/agents` rendering)

Protected routes (`/agents`, `/a2a`, etc.) are heavy SPAs that **crash the headless renderer** on this 64 MB /dev/shm container even with the hardening flags from `browser_use_renderer_crash_fix.md`. Don't verify login by navigating to a protected route — **read localStorage directly** on a lightweight page (`/login` is public and lightweight):

```bash
# Recover daemon if it crashed during a prior nav, then re-attach:
pkill -9 chrome-headless-shell 2>/dev/null; sleep 1; bu start --engine chromium
bu navigate "$LOCAL_URL/login"   # cookies persist on --user-data-dir profile

# Decode the Supabase JWT to confirm the authenticated email
cat > workspace/tmp/jwt-decode.js <<'JS'
(() => {
  const k0 = localStorage.getItem('sb-stg-auth-token.0') || '';
  const k1 = localStorage.getItem('sb-stg-auth-token.1') || '';
  const blob = (k0 + k1).replace(/^base64-/, '');
  let parsed; try { parsed = JSON.parse(atob(blob)); } catch (e) { return JSON.stringify({err:e.message}); }
  const at = parsed.access_token || '';
  let claims = null;
  if (at) {
    const p = at.split('.');
    if (p.length === 3) { try { claims = JSON.parse(atob(p[1].replace(/-/g,'+').replace(/_/g,'/'))); } catch(e){} }
  }
  return JSON.stringify({
    user_email: parsed.user && parsed.user.email,
    role: claims && claims.role,
    exp_iso: claims && claims.exp ? new Date(claims.exp * 1000).toISOString() : null
  });
})()
JS
JS=$(cat workspace/tmp/jwt-decode.js); bu eval "$JS"
# expect: {"user_email":"moriel+devagent1@xpander.ai","role":"authenticated",...}
```

If `user_email` matches and `role=="authenticated"`, login succeeded — even if a subsequent `bu navigate /agents` crashed the renderer.

#### Why this is reliable

- **Single CDP call** — one `bu eval`, not six type-and-focus calls.
- **Uses the component's own handler** — `OTPVerification.tsx` handles paste in production code; we're exercising the real path.
- **No focus dependence** — dispatching `ClipboardEvent('paste')` on the wrapper div doesn't require any cell to be focused.
- **Cookies survive renderer crashes** — `--user-data-dir=/tmp/browser_use_chromium_profile_default` persists across daemon restarts; only the WS connection is lost.

### Path 1b — Per-cell typing (legacy fallback)

If the paste event ever stops working (e.g. Supabase Auth UI changes):

```bash
CODE=123456
for i in 0 1 2 3 4 5; do
  bu type "input[maxlength='1'][inputmode='numeric']:nth-of-type($((i+1)))" "${CODE:$i:1}"
done
```

### Path 2 — Reuse a daemon session (no re-login per task) ⭐

After the first successful OTP login, the chromium daemon retains the
Supabase session cookie and `localStorage` JWT for the daemon's lifetime
(or until cookie expiry — typically 1h access + 7d refresh).

**Rule:** never call `bu stop` between tasks unless you genuinely need a fresh
session. The daemon is a long-lived login store. Subsequent tasks just `bu navigate`
straight to the protected URL and skip auth entirely.

Verify session is still alive:

```bash
bu navigate "$LOCAL_URL/agents"
bu eval 'location.pathname'    # if it returns /login, session expired — re-do Path 1
```

### Path 3 — Service-role override (LAST RESORT, never on prod)

If Moriel explicitly asks and we are pointed at **staging or a local Supabase**,
a service-role key can mint a session token directly. **Do not implement this
without explicit per-task approval** — there is no way to audit whose account got
logged into. If approved, the recipe is:

```bash
# Service role key from .env.local (NEVER echo)
SB_URL=$(grep -E '^NEXT_PUBLIC_SUPABASE_URL=' /agent/data/dev/frontend/.env.local | cut -d= -f2-)
# Use the admin endpoint to generate a magic link, then visit the verify URL.
# Code intentionally omitted — implement only with explicit approval.
```

**Forbidden:** running this against `xpander.ai` production keys, ever.

### OTP gotchas observed

- **Single-use codes** — if the agent pastes the code into the wrong tab/session,
  it's burned. Always confirm `bu status` shows the active tab is on `/login`
  before submitting.
- **Code expiry** — staging OTP codes expire in ~5 minutes. If `xpask_for_information`
  takes longer than that, request a fresh code (click "Resend") rather than submitting
  a stale one.
- **Numeric-only inputs** — the OTP input on Supabase auth UI uses
  `inputmode="numeric"` and rejects pasted alphabetic chars. `bu type` works because
  it dispatches keystrokes directly.
- **Multiple inputs (one per digit)** — some Supabase Auth UI variants render six
  separate `<input>` cells. Detect via `bu inspect` (count of `[autocomplete="one-time-code"]`);
  if >1, type each digit into each cell:
  ```bash
  CODE=123456
  for i in 0 1 2 3 4 5; do
    bu type "[data-index='$i'][autocomplete='one-time-code']" "${CODE:$i:1}"
  done
  ```

---

## Workflow C — Capture feature screenshots for PRs

Every UI-affecting PR (per `pr_title_description.md`) needs **before** and **after**
shots. Always shoot at the enforced 1920x1080 baseline (browser_use.md → Viewport).

### Recipe

```bash
mkdir -p workspace/tmp/screenshots/${TICKET:-PRO-XXXX}

# 1. BEFORE — checkout develop (or the base branch), navigate, snap.
cd /agent/data/dev/frontend && git stash && git checkout develop && git pull
kill $(cat workspace/tmp/frontend-dev.pid) 2>/dev/null; rm -rf .next
pnpm dev > workspace/tmp/frontend-dev.log 2>&1 &
echo $! > workspace/tmp/frontend-dev.pid
# wait for ready (see Workflow A)
bu navigate "$LOCAL_URL/<feature-route>"
bu wait '<key-selector>' --timeout 20
bu screenshot "workspace/tmp/screenshots/${TICKET}/before-default.png"

# 2. AFTER — checkout your branch, restart dev, snap.
kill $(cat workspace/tmp/frontend-dev.pid); rm -rf .next
git checkout feature/develop/${TICKET}
git stash pop 2>/dev/null || true
pnpm dev > workspace/tmp/frontend-dev.log 2>&1 &
echo $! > workspace/tmp/frontend-dev.pid
bu navigate "$LOCAL_URL/<feature-route>"
bu wait '<key-selector>' --timeout 20
bu screenshot "workspace/tmp/screenshots/${TICKET}/after-default.png"

# 3. Variant shots if the feature has branches (BYOK, error state, empty, etc.)
bu screenshot "workspace/tmp/screenshots/${TICKET}/after-byok.png"
bu screenshot "workspace/tmp/screenshots/${TICKET}/after-empty.png"
```

### Attach to PR description

Use `xpworkspace-file-share` per screenshot to get a public URL, then embed in the
PR body in a comparison table (per `pr_title_description.md` → Screenshots section).
Standard layout:

```markdown
## Screenshots

| Before | After |
|---|---|
| ![before](URL_FROM_FILE_SHARE) | ![after](URL_FROM_FILE_SHARE) |

### Variants

| BYOK | Empty | Error |
|---|---|---|
| ![byok](...) | ![empty](...) | ![error](...) |
```

### Screenshot quality rules

1. **Always 1920x1080.** Browser_use enforces this via CDP override. Do not pass
   `viewport=` overrides for PR screenshots.
2. **Wait for content, not time.** Use `bu wait '<selector>' --timeout 20` —
   `sleep N` is unreliable on a loaded box.
3. **Hide ephemeral noise.** Toasts, tooltip tails, and hover states tend to
   appear mid-shot. Either:
   - Move the cursor off the element first: `bu eval 'document.body.dispatchEvent(new MouseEvent("mouseleave"))'`.
   - Take the shot, inspect, and reshoot if a tooltip leaked in.
4. **Same viewport, same theme, same data.** If staging data changed between
   before/after, capture both shots in the same dev session against the same DB.
5. **No PII in shots.** Open the file before sharing — if it contains real
   customer emails, names, or org names, blur them with imagemagick or pick a
   different account/route.
6. **File names tell a story.** `before-default.png`, `after-default.png`,
   `after-byok.png`, etc. Reviewers shouldn't have to guess.

---

## Workflow D — The iteration loop (probe → fix → re-probe)

When iterating on a UI change with the user watching:

```
1. bu inspect / bu screenshot           ← see current state
2. read code, edit                       ← in /agent/data/dev/frontend/src/...
3. (if env or globals changed)           ← restart pnpm dev + nuke .next
4. bu navigate <same URL>                ← refresh
5. bu wait <selector> + bu screenshot    ← new evidence
6. compare with previous shot            ← human or eyeballed by agent
7. commit when stable                    ← never commit speculative changes
```

**Anti-pattern:** running `pnpm build` between iterations to "make sure it compiles".
`pnpm compile` (`tsc --noEmit`) is what you want — see compile-not-build rule.

---

## Lessons learned (incidents → rules)

### 1. The browser daemon is a long-lived login session — treat it as one
**What happened:** Re-ran `bu start` on a new task and lost the OTP'd Supabase
session; had to wait on the user for a fresh code. The previous daemon was still
holding a valid session — calling `bu stop` had thrown it away.

**Rule:** Don't `bu stop` between agent tasks. Use `bu status` to confirm the
daemon is up; if it is, just `bu navigate` and inherit the session. Restart only
when genuinely necessary (engine swap, renderer truly stuck after 3 retries,
user asks for a fresh login).

### 2. Local frontend + remote Supabase is the default — avoid spinning up local Supabase
**What happened:** Tried to point `.env.local` at a local Supabase instance to
sidestep OTP. Cost: 30 minutes of Docker Compose, RLS migrations, seed data, and
the DB schema still didn't match staging. Local Supabase is rarely worth it.

**Rule:** Default to staging Supabase + accept the OTP friction. Only stand up
local Supabase if the work is specifically about Supabase schema/RLS migrations.

### 3. Restart dev after every `.env.local` change — HMR does not reload env
**What happened:** Edited `NEXT_PUBLIC_API_URL` in `.env.local` mid-session;
browser kept hitting the old URL because Next bakes `NEXT_PUBLIC_*` at build time.

**Rule:** Any `.env*` change → kill `pnpm dev`, optionally `rm -rf .next`,
restart. Don't bother trying to invalidate HMR — restart is ~10 s.

### 4. Screenshots at the wrong viewport are immediately recognisable to reviewers
**What happened:** A PR shipped with screenshots taken at 1280x720 (a stale
browser_use default) — reviewer asked for re-shots because the layout looked
weirdly cramped vs production. We now enforce 1920x1080 in code (browser_use.md
→ Viewport) and in this skill's recipe. Don't override.

**Rule:** Never pass a custom viewport to `bu` for PR screenshots. The 1920x1080
baseline is the contract reviewers expect.

### 5. "Before" shots are non-negotiable for visual changes
**What happened:** Submitted a PR with only "after" screenshots. Reviewer
responded "can't tell what changed without seeing before". Cost: another round-trip.

**Rule:** For any UI-touching PR, capture **both** the base branch and the
feature branch state at the same route, same data, same viewport. Always.

### 6. OTP codes burn fast — stage the prompt before requesting the code
**What happened:** Asked the user for an OTP code, then took 4 minutes navigating
to the right route and filling the email field. Code expired before submission.

**Rule:** Drive `bu` all the way to the OTP-input screen first, **then** request
the code from the user, **then** submit immediately on receipt.

### 7. Six-input OTP cells need per-cell typing
**What happened:** `bu type 'input[autocomplete="one-time-code"]' '123456'` typed
all six digits into the first cell because Supabase Auth UI uses six
single-character inputs. The form rejected the submission.

**Rule:** `bu inspect` first; if there are multiple `one-time-code` inputs,
loop and type one char per cell (recipe in Workflow B).

### 8. `pnpm install --frozen-lockfile` saves 5 minutes when the lockfile is current
**What happened:** Default `pnpm install` re-resolves the dependency tree even
when `pnpm-lock.yaml` is committed and unchanged.

**Rule:** Use `--frozen-lockfile` unless you intentionally bumped a dep.

### 9. Always tail `frontend-dev.log` on start, not just `sleep`
**What happened:** Hard-coded `sleep 30` after `pnpm dev`. On a slow box dev wasn't
ready; navigated to localhost and got `ECONNREFUSED`. On a fast box wasted 25 s.

**Rule:** Poll the log for `Local:` or `ready in` (Workflow A's `for i in $(seq 1 60)` loop).

### 10. Renderer crashes during local dev are rarer but identical to remote crashes
**What happened:** Heavy SPA route + dev-mode source maps spiked memory; renderer
crashed with `Inspector.targetCrashed`. Same root cause as the remote-site crashes
in browser_use.md, same fix already applied.

**Rule:** If a `bu` command hangs for >30 s on a localhost route, check
`pgrep -af chrome-headless-shell` and `dmesg | tail`. If the renderer is dead,
`bu stop && pkill -9 chrome-headless-shell && bu start` and retry — but expect
to re-OTP. (See lesson #1 — try to avoid this.)

---

## Hard rules

1. **Never `pnpm build`** in this environment — `pnpm compile` instead.
2. **Never** commit `.env*.local` — `frontend_env_sync.md` Step 5 verification still applies.
3. **Never** echo OTP codes, JWTs, or env values in chat.
4. **Never** override the 1920x1080 viewport for PR screenshots.
5. **Never** `bu stop` between tasks unless explicitly required — preserves login.
6. **Always** include before AND after screenshots for UI-affecting PRs.
7. **Always** restart `pnpm dev` after `.env*` changes.
8. **Always** drive to the OTP-input screen before asking the user for the code.
9. **Always** save screenshots under `workspace/tmp/screenshots/${TICKET}/` and
   share via `xpworkspace-file-share` — never inline base64 into PR descriptions.

---

## See also

- **Browser CLI**: `workspace/dev-knowledge/skills/browser_use.md` (engine, viewport, Typeform, fonts)
- **Env files**: `workspace/dev-knowledge/skills/frontend_env_sync.md`
- **Compile rule**: `workspace/dev-knowledge/memory/lessons/lessons_learned.md` → "Frontend Repo — Compile, Never Build"
- **PR description format**: `workspace/dev-knowledge/skills/pr_title_description.md`
- **Repos overview**: `workspace/dev-knowledge/skills/known_repos.md`
