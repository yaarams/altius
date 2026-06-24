# Skill: Browser Use — Headless Browser as a Subprocess

## Goal

Drive a real, JavaScript-capable browser from any xpander.ai agent **without blocking the main agent loop**. The browser runs as an isolated subprocess; the agent talks to it over the **Chrome DevTools Protocol (CDP)** WebSocket. Subprocess crashes do not crash the agent; many concurrent tasks can share one browser via per-task `Target` (tab) sessions.

## When to use

- Scraping JS-rendered pages (SPAs, Framer/Webflow/Next.js sites).
- Filling forms, clicking buttons, evaluating arbitrary JS in a real DOM.
- Capturing screenshots / PDFs / DOM-to-Markdown.
- Long-running flows (e.g. "watch this dashboard for changes") where the agent must keep doing other work.

Do **not** use it for things `requests` / `httpx` already handle (static HTML, JSON APIs).

---

## Engines (CDP-compatible — pick one)

| Engine | Binary size | Mem | Notes |
|---|---|---|---|
| **`obscura`** (default) | ~71 MB | ~30 MB | Rust + V8 single binary. Fastest cold-start. **Some Framer/Next.js scripts hit unimplemented browser APIs and warn** — DOM still rendered. Stealth available via `--features stealth` build. |
| **`chromium`** (fallback) | ~170 MB (headless-shell) | ~200 MB | Real Chromium via Playwright. Highest compatibility. Use this when obscura logs JS errors that affect functionality. |

The skill is engine-agnostic — same Python API for both.

---

## Install

### Option A — obscura prebuilt binary (preferred when GLIBC ≥ 2.39)

```bash
curl -LO https://github.com/h4ckf0r0day/obscura/releases/latest/download/obscura-x86_64-linux.tar.gz
tar xzf obscura-x86_64-linux.tar.gz
mv obscura /usr/local/bin/   # or anywhere on PATH
obscura --help
```

> ⚠️ **Debian 12 / Ubuntu 22.04 sandboxes ship GLIBC 2.36** — prebuilt binary fails with `GLIBC_2.38 not found`. Use Option B.

### Option B — build obscura from source (works on GLIBC 2.36)

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
. "$HOME/.cargo/env"
rustup default stable    # need rustc ≥ 1.88 for the `time` crate; stable on this image is 1.95

git clone https://github.com/h4ckf0r0day/obscura.git
cd obscura
cargo build --release          # ~1m 12s on a typical agent sandbox
mv target/release/obscura /usr/local/bin/
# Optional: stealth + tracker blocking
# cargo build --release --features stealth
```

### Option C — chromium fallback engine

```bash
pip install playwright websockets
python3 -m playwright install chromium
python3 -m playwright install-deps chromium    # apt deps; requires sudo or root

# REQUIRED: system fonts. chrome-headless-shell hits a Skia FATAL when no
# system fonts are installed AND a NOTREACHED in remote_font_face_source.cc
# when remote web fonts (Framer / Google Fonts) are downloaded without a
# fontconfig setup. Install at least one TTF family + fontconfig:
sudo apt-get install -y --no-install-recommends \
    fonts-liberation fonts-dejavu-core fontconfig
```

> **Why fonts matter:** without `fontconfig` + at least one TTF family,
> Chromium's renderer crashes on font-heavy SPAs (xpander.ai, google.com,
> github.com). The crash surfaces as `Inspector.targetCrashed` and was
> the root cause of intermittent `bu eval` hangs before this skill update.
> See **Reliability fixes** at the bottom of this file.

---

## Viewport — always 1920x1080 (enforced)

**Rule:** every browser tab opened through this skill renders at **1920x1080**
(desktop FHD baseline). This is the layout most xpander.ai surfaces
(`xpander.ai`, `app.xpander.ai`, `docs.xpander.ai`) target for desktop
breakpoints, and matches what reviewers see when checking screenshots.

Enforcement is layered so it survives renderer recycles, daemon restarts,
and engine swaps:

1. **Chromium argv** — `--window-size=1920,1080` is now hard-wired into
   `BrowserSubprocess._argv()` (`browser_subprocess.py`) and the daemon
   chromium argv (`daemon.py`). The OS window itself boots at FHD.
2. **Per-tab CDP override** — `BrowserPool._apply_viewport(session_id)`
   issues `Emulation.setDeviceMetricsOverride` (width=1920, height=1080,
   deviceScaleFactor=1, mobile=False) immediately after every
   `Target.attachToTarget`, in both `new_page()` and `attach_to_target()`.
   This works for **both engines** (obscura + chromium) and is what
   makes `window.innerWidth` / `screen.width` actually report 1920.
3. **Default constant** — `BrowserPool.DEFAULT_VIEWPORT = (1920, 1080)`.
   Override only when there is a concrete reason (e.g. mobile-emulation
   testing) via the ctor `viewport=(w,h)` kwarg or env
   `BROWSER_USE_VIEWPORT=WxH` (e.g. `BROWSER_USE_VIEWPORT=375x812`).

**Verification (run after any browser code change):**

```bash
bu navigate https://example.com
bu eval 'JSON.stringify({w:innerWidth,h:innerHeight,sw:screen.width,sh:screen.height,dpr:devicePixelRatio})'
# expect: {"w":1920,"h":1080,"sw":1920,"sh":1080,"dpr":1}
```

**If you see something other than 1920x1080:**
- Confirm the daemon was restarted after the code change
  (`bu stop && pkill -9 chrome-headless-shell && bu start`).
- Confirm `pgrep -af chrome-headless-shell` argv contains
  `--window-size=1920,1080`.
- Confirm no caller is passing `viewport=...` or setting
  `BROWSER_USE_VIEWPORT` to override the default.

---

## Quick start — generic `bu` CLI (preferred for agents)

> **Always use the `bu` CLI for browser actions.** Do NOT write one-off Python
> scripts that import `BrowserPool` and hard-code each step — every step
> rewrites the same boilerplate, every script is fragile against API drift,
> and the agent loses turn-by-turn observability. The CLI is the supported
> agent interface; the Python API is for tools that build on top of it.

The `bu` shim lives at `/agent/data/.persist/bin/bu` (already on `PATH`) and
dispatches one action per call against a long-lived browser daemon. State
(active daemon + active tab) is persisted under
`$XDG_RUNTIME_DIR/browser_use/`, so consecutive calls share the same tab.
Default engine is `chromium` (override with `--engine obscura|auto` or
`BROWSER_USE_ENGINE`). The `--engine` flag is accepted in BOTH positions:
as a global flag before the subcommand, and as a `start`-subcommand flag.

```bash
# 1. Boot a daemon (idempotent — reuses the running one).
# Both forms work and are equivalent:
bu start --engine chromium
bu --engine chromium start

# 2. Open a tab and inspect the page (returns JSON: title, headings, inputs, clickables, forms)
bu navigate https://app.xpander.ai/signup
bu inspect | jq '.inputs[] | {name, type, label}'

# 3. Drive the form using CSS selectors — NO custom JS needed
bu type   'input[name=first_name]' 'Diana'
bu type   'input[name=last_name]'  'Ford'
bu type   'input[name=email]'      'demo@xpander.ai'
bu click  'button[type=submit]'

# 4. Wait for the next page state, snapshot, read text, etc.
bu wait   'h1'  --timeout 15
bu screenshot workspace/tmp/screenshots/after_submit.png
bu text   'main'
bu cookies
bu eval   'document.querySelector("input[name=otp]")?.outerHTML'
```

### Full command reference

| Command | Purpose | Example |
|---|---|---|
| `bu start [--engine chromium\|obscura\|auto]` | Start (or reuse) the browser daemon | `bu start --engine chromium` |
| `bu stop` | Kill daemon, clear active tab | `bu stop` |
| `bu status` | Daemon + active tab info as JSON | `bu status` |
| `bu new-page [URL]` | Open new tab and set it active | `bu new-page https://example.com` |
| `bu tabs` | List tabs (active flag included) | `bu tabs` |
| `bu use <targetId>` | Switch active tab | `bu use 631AC95F…` |
| `bu close-tab` | Close the active tab | `bu close-tab` |
| `bu navigate <URL>` | Active tab → URL (waits for load) | `bu navigate https://app.xpander.ai/login` |
| `bu inspect` | Title, headings, inputs, clickables, forms | `bu inspect` |
| `bu eval '<JS>'` | `Runtime.evaluate` (IIFE-wrapped, returns value) | `bu eval 'document.title'` |
| `bu click '<sel>'` | Scroll into view + click | `bu click 'button[type=submit]'` |
| `bu type '<sel>' '<text>' [--submit] [--no-clear]` | Focus + set value + dispatch input/change | `bu type '#email' 'a@b.c' --submit` |
| `bu select '<sel>' '<value>'` | `<select>` change | `bu select '#country' 'US'` |
| `bu press <Key>` | `Input.dispatchKeyEvent` | `bu press Enter` |
| `bu wait '<sel>' [--timeout S] [--visible]` | Poll for selector (optionally visible) | `bu wait '#otp' --timeout 30` |
| `bu text [<sel>]` | innerText (whole page or one element) | `bu text 'main'` |
| `bu html [<sel>]` | outerHTML | `bu html '#root'` |
| `bu url` / `bu title` | Active tab URL / title | `bu url` |
| `bu cookies` | Cookie jar (CDP `Storage.getCookies`) | `bu cookies` |
| `bu screenshot [path]` | PNG; default `workspace/tmp/screenshots/<ts>.png` | `bu screenshot` |

### Rules of thumb (read before doing browser work)

1. **Never write a per-step Python script** for browser automation. If you
   find yourself doing `python3 -c 'import asyncio; from browser_use …'`,
   stop and use `bu` instead.
2. **Each `bu` call is one action.** Use shell + `jq` (or just inline JSON
   reads) to chain actions in tool calls.
3. **Use `bu inspect` first** when arriving on an unknown page — it returns
   the structured DOM you need to pick a selector. No need to hand-craft
   `document.querySelectorAll(…)` JS.
4. **Selectors over coordinates.** `bu click 'button[type=submit]'` is the
   supported path; xy clicks via `Input.dispatchMouseEvent` are not exposed
   on purpose.
5. **One daemon per agent runtime.** `bu start` is idempotent — don't try to
   spin up multiple daemons; use `--name <other>` only when you genuinely
   need isolated cookie jars / tab sets.
6. **Use `bu eval` only for one-line introspection** (e.g. reading a
   computed style, hashing a value). For anything stateful, prefer the
   typed commands so failures show up as proper non-zero exit codes.
7. **Tab persistence is automatic.** `bu navigate` reuses the active tab.
   To work on a different tab use `bu use <targetId>` (get IDs from
   `bu tabs`).

---

## Underlying Python API (advanced — for building new commands)

When extending the skill itself (e.g. adding a `bu download` subcommand),
use the Python API directly. **Do not use this from agent task code — use
`bu` instead.**

### One-shot fetch (no skill code needed, just the obscura CLI)

```bash
obscura fetch https://xpander.ai/ --quiet --eval "document.title"
# -> xpander.ai — AI Agent Platform for Enterprises
```

### Pattern A — owned subprocess (single agent process)

Use this when one Python process drives the browser for the duration of one
task and tears it down afterwards. The browser lives for the lifetime of the
`async with` block.

```python
from browser_use import BrowserPool

# engine="auto" prefers obscura, falls back to chromium if missing.
# Use "obscura" or "chromium" explicitly to pin one.
async with BrowserPool(engine="auto") as pool:
    page = await pool.new_page()
    await page.navigate("https://xpander.ai/")
    info = await page.evaluate("({title:document.title, h1:document.querySelector('h1')?.innerText})")
    print(info)
# browser subprocess auto-killed here
```

### Pattern B — persistent daemon (browser stays open across calls / processes) ⭐

Use this when you want the **same browser instance to stay alive between
requests, scripts, or agent invocations** — e.g. log in once, then run many
actions over hours, or share one browser across N agent tasks. Cookies,
open tabs, and JS state persist.

```bash
# Terminal / process #1 — boot the daemon (idempotent: returns existing one if already running)
python3 -m browser_use.daemon start --engine obscura --name default
# {
#   "name": "default",
#   "pid": 12345,
#   "port": 54367,
#   "engine": "obscura",
#   ...
# }

python3 -m browser_use.daemon status   # is it up?
python3 -m browser_use.daemon ws-url    # ws://127.0.0.1:54367/devtools/browser
python3 -m browser_use.daemon stop      # tear it down (only when you're really done)
```

```python
# From any process / agent task — attach to the long-lived daemon
from browser_use import BrowserPool, BrowserDaemon

d = BrowserDaemon(name="default")
state = await d.ensure_started(engine="obscura")     # idempotent: reuses if alive
pool  = await BrowserPool.attach(d.ws_url)            # connect, do NOT spawn

page = await pool.new_page()
await page.navigate("https://app.xpander.ai/login")
await page.evaluate("document.querySelector('#email').value='me@xpander.ai'")
# ...do many things over many calls; tabs and cookies stay alive...

# Detach (browser keeps running):
await pool._cdp.close()
```

**What persists between attaches**
- All open tabs (`Target.getTargets` returns them on reconnect).
- All cookies (HTTP + `document.cookie`) for the browser's lifetime.
- localStorage, sessionStorage, IndexedDB.
- JS state of any tab you don't close.
- Network state (in-flight requests, intercepted patterns) is tab-scoped.

**Verified behaviour** (against `xpander.ai/` on 2026-04-26): a session-1 Python
process set `document.cookie = 'xp_demo=hello-from-session1'` on the home page
and navigated to `/pricing`; a separate session-2 Python process attached 90 s
later, listed the still-open tabs (`/pricing`, `docs/`), re-attached to tab 1,
and read back the same cookie + same URL. Daemon stayed alive across both.

> Obscura **does not expose** the standard Chrome HTTP discovery endpoint `/json/version`. Connect to the WebSocket path directly: `ws://127.0.0.1:<port>/devtools/browser`. The daemon helper writes the URL and PID to `~/.cache/browser_use/<name>.json` so other processes can locate it without env vars.

---

## Architecture

```
   ┌──────────────────┐         ┌──────────────────────────────────┐
   │  Agent main loop  │         │  obscura serve --port 9222   │
   │ (xpander handler) │  CDP WS │   (subprocess, isolated PG)  │
   │                   │◄───────►│  • V8 + DOM                  │
   │  BrowserPool      │         │  • multi-Target (tabs)       │
   │   └ Session/tab   │         │  • lives across tasks        │
   └────────┬─────────┘         └───────────────────────────────────┘
            │ emits BrowserEvent
            ▼
     event_bus / SDK callback   (page.loaded, network.response, page.error…)
```

- **One subprocess per `BrowserPool`** — you almost always want a single pool per agent process.
- **One `Target` (tab) per concurrent task** — attach via `Target.attachToTarget` to get a `sessionId`, then route every command through that `sessionId`.
- **Async I/O only** — the WS client never blocks; the agent's main loop keeps ticking.
- **Crashed renderer? No problem.** The pool detects `Inspector.targetCrashed` and recycles the tab; the subprocess itself is supervised and respawned on exit.

---

## Reference implementation

Lives at `workspace/dev-knowledge/skills/code/browser_use/`:

```
browser_use/
  __init__.py          # public API: BrowserPool, Page, BrowserEvent, BrowserDaemon
  __main__.py          # python3 -m browser_use <cmd> → cli.main
  browser_subprocess.py # spawn/stop obscura or chromium, pick free port, healthcheck
  cdp_client.py        # async CDP WS client (send, attach, recv-router)
  pool.py              # BrowserPool + Page (now: navigate/evaluate/inspect/click/type/wait_for_selector/select/press/screenshot/cookies/text/html/url/title)
  engine.py            # ObscuraEngine / ChromiumEngine adapters
  events.py            # asyncio.Queue event bus + xpander-sdk publisher hook
  daemon.py            # BrowserDaemon: persistent cross-process supervisor + CLI
  cli.py               # generic agent-facing CLI: start/stop/status/new-page/tabs/use/navigate/inspect/eval/click/type/select/press/wait/text/html/url/title/cookies/screenshot/close-tab
  smoke.py             # python3 -m browser_use.smoke <engine> <url>

The `bu` shim (`/agent/data/.persist/bin/bu`) just sets `PYTHONPATH` and execs
`python3 -m browser_use` so commands are available globally.
```

All dependencies are stdlib + `websockets` (and `playwright` only when engine=chromium).

---

## Skill rules (when adding code that uses this)

1. **Always isolate.** Never run a browser in the agent's own event loop / process; use `BrowserPool`.
2. **Never share a `Page` (sessionId) across tasks.** Each parallel task gets its own `Target`.
3. **Always set timeouts** on `navigate` / `evaluate` / `wait_for_selector` (default 30 s).
4. **Always handle `BrowserEvent.page_error`** — obscura emits these for unhandled JS exceptions; logging-only is fine, but never silently retry forever.
5. **Auto-fallback** to `engine=chromium` if obscura returns a JS error code AND the page also has no usable DOM (`document.body == null`). Don't fall back on warnings alone.
6. **No long-lived global state in the browser.** Treat each `BrowserPool` as ephemeral; tear it down at the end of the agent task.
7. **Stealth flag is opt-in.** Default off. Only enable for explicitly authorised scraping work.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `obscura: GLIBC_2.38 not found` | Debian 12 / GLIBC 2.36 | Build from source (Option B). |
| `cargo: feature edition2024 not stabilized` | Rust < 1.85 | `rustup default stable` then re-run `cargo build`. |
| `time crate requires rustc 1.88` | Old stable | Same fix — `rustup default stable`. |
| `error while loading shared libraries: libglib-2.0.so.0` (Playwright) | Missing apt deps | `python3 -m playwright install-deps chromium` (root). |
| `[swan] domain not whitelisted` (obscura console) | Obscura's tracker block / network policy | Harmless on most pages; ignore in agent logs. |
| `TypeError: Cannot read properties of undefined (reading 'text')` | Obscura V8 missing some browser APIs (Framer, etc.) | Switch `engine=chromium` for that page. DOM is usually still rendered — check `document.body.innerHTML.length > 0` first. |
| `connect ECONNREFUSED ws://127.0.0.1:9222` | Obscura not started, or wrong port | `ps -ef | grep obscura serve`; restart; ensure port is free. |
| Tried `curl http://127.0.0.1:9222/json/version` and got nothing | Obscura has **no HTTP discovery endpoint** | Connect to `ws://127.0.0.1:<port>/devtools/browser` directly. |
| `websockets.exceptions.InvalidStatus: server rejected WebSocket connection: HTTP 404` on **chromium** | Used obscura's fixed WS path (`/devtools/browser`) against chromium | Chromium requires HTTP `/json/version` discovery. Use `BrowserPool(engine="chromium")` (it now calls `ChromiumEngine.ws_endpoint()` which polls `/json/version` for the real `webSocketDebuggerUrl`). Don't hand-construct chromium WS URLs. |
| `FileNotFoundError: obscura binary not found` even though I just built it | Source-built binary is at `target/release/obscura`, not on `$PATH` | Three options: (1) `cp target/release/obscura /usr/local/bin/`, (2) `export OBSCURA_BIN=/full/path/to/obscura`, or (3) drop it at one of the locations in `OBSCURA_SEARCH_PATHS` (see `engine.py`). The skill auto-detects the workspace source-build path. |
| Many `<defunct> chrome-headless-shell` zombies in `ps` | Daemon / pool stop didn't reap the chrome child | Run `pkill -9 chrome-headless-shell && pkill -9 obscura` and `rm ~/.cache/browser_use/*.json` before next run. The pool now uses `start_new_session=True` and process groups; this should be rare. |
| Daemon CLI emits `RuntimeWarning: 'browser_use.daemon' found in sys.modules after import of package 'browser_use'` | `python3 -m browser_use.daemon` triggers the package's `__init__` then re-imports the submodule | Cosmetic — safe to ignore. Suppress with `PYTHONWARNINGS=ignore::RuntimeWarning`. |
| `engine="auto"` ends up picking chromium even though obscura is installed | Obscura binary not on any path in `OBSCURA_SEARCH_PATHS`, or not executable | `chmod +x` the binary and either `export OBSCURA_BIN=...` or symlink it into `/usr/local/bin/`. Check with `python3 -c 'from browser_use.engine import ObscuraEngine; print(ObscuraEngine.find_binary())'`. |

---

## Lessons learned (incidents → fixes)

These are real bugs hit while building this skill — recorded so the next agent doesn't repeat them.

### 1. Obscura ≠ Chromium at the discovery layer
**Symptom:** `BrowserPool(engine="chromium")` crashed with `InvalidStatus: HTTP 404` on the WebSocket handshake.

**Root cause:** Obscura serves the WS directly at the well-known path `ws://host:port/devtools/browser`. Chromium serves an HTTP endpoint at `http://host:port/json/version` whose body contains the **real** `webSocketDebuggerUrl` (which includes a per-launch token, e.g. `ws://host:port/devtools/browser/abc123…`). The original `BrowserPool.start()` hard-coded the obscura path and used it for both engines.

**Fix:** Each engine class now exposes `ws_endpoint(host, port, timeout)`:
- `ObscuraEngine.ws_endpoint`: returns the fixed path immediately.
- `ChromiumEngine.ws_endpoint`: polls `/json/version` (chromium needs ~200–500 ms after `bind()` to serve HTTP) and reads the token-bearing URL.

`BrowserPool.start()` calls the engine-specific resolver instead of `self._sub.ws_url`. The daemon's `ws_url` property is also engine-aware now.

### 2. Binary discovery must look beyond `$PATH`
**Symptom:** `FileNotFoundError: obscura binary not found` after a successful `cargo build --release`.

**Root cause:** `shutil.which("obscura")` only searches `$PATH`. The source-built binary lives at `target/release/obscura`. Engineers (and agents) regularly forget to copy it into `/usr/local/bin/`.

**Fix:** `ObscuraEngine.find_binary()` now checks, in order: explicit `binary=` arg → `$OBSCURA_BIN` → `$PATH` → `OBSCURA_SEARCH_PATHS` (a hard-coded list including `~/.local/bin/obscura`, `/opt/obscura/obscura`, and the workspace source-build path `/agent/data/workspace/tmp/obscura-src/target/release/obscura`). `ChromiumEngine.find_binary()` mirrors this and additionally walks the Playwright cache layout (`~/.cache/ms-playwright/chromium*/chrome-headless-shell-linux64/chrome-headless-shell`).

### 3. Always provide an `auto` fallback
**Symptom:** Skill hard-failed on machines that had only chromium (or only obscura).

**Fix:** `engine="auto"` (new default in examples) tries Obscura first (lighter, faster cold-start), falls back to Chromium if its binary is missing. Internally it's a `_AutoEngine` whose `resolve()` returns the concrete `EngineConfig`; `BrowserPool` then uses the concrete engine's `ws_endpoint` and `make_subprocess`.

### 4. GLIBC ≥ 2.38 vs Debian 12
The upstream prebuilt obscura tarball is linked against GLIBC 2.38/2.39. Debian 12 (the agent sandbox) ships GLIBC 2.36. **Always assume the prebuilt won't run** and fall back to source build (Rust ≥ 1.88, ~75 s on a typical agent box).

### 5. Different engines render different DOMs
Obscura's V8 + custom DOM is faithful for static markup but stops short of fully executing some Framer/Next.js scripts. On `xpander.ai/`:
- Obscura returns `bodyLen=650175`, one `<h1>` ("xpand Agentic AI into your private stack"), full nav links.
- Chromium returns `bodyLen=336985`, **five** `<h1>`s ("Prebuilt AI Workforce…", "Your AI transformation starts here", "What builders say", "In the News", "FAQ"), no static nav links (they're rendered later by JS).

**Both are valid DOMs** depending on what you need. If you want "what a user sees", chromium. If you want "what's in the static markup", obscura is faster.

### 6. Don't forget process groups
Obscura's `serve` and chrome-headless-shell each spawn child processes. If the supervisor SIGTERMs only the parent, the children become orphans → defunct/zombies. `BrowserSubprocess` uses `start_new_session=True` and `os.killpg(os.getpgid(pid), SIGTERM)` to take down the whole group; without that, daemon restarts leak processes.

---

## Validated against xpander.ai

This skill was verified end-to-end on 2026-04-26 by the agent against `https://xpander.ai/` and `https://docs.xpander.ai/`:

- `obscura fetch … --eval "document.title"` returned `xpander.ai — AI Agent Platform for Enterprises`.
- Direct CDP WebSocket drive (`Target.createTarget` → `attachToTarget` → `Page.navigate` → `Runtime.evaluate`) returned the full DOM payload (title, H1 "xpand Agentic AI into your private stack", nav links).
- Playwright/Chromium fallback engine produced screenshots successfully.
- **All three smoke tests pass** end-to-end against `https://xpander.ai/`:
  - `python3 -m browser_use.smoke obscura  https://xpander.ai/` → exit 0, `bodyLen=650175`.
  - `python3 -m browser_use.smoke chromium https://xpander.ai/` → exit 0, `bodyLen=336985`, real WS URL discovered via `/json/version`.
  - `python3 -m browser_use.smoke auto     https://xpander.ai/` → exit 0, picks obscura (priority 1) on this box.
- **Persistent daemon**: a session-1 Python process set a cookie on `/` and navigated to `/pricing` + opened a second tab on `docs/`; a separate session-2 Python process attached 90 s later, listed both tabs still open, re-read the same cookie, and added a third tab on `/blog`. Daemon survived both clients.

See the plan: `workspace/local/plans/_unticketed/browser-use-skill-20260426.md` (rename once a ticket is assigned).

---

## See also

- **Plan**: `workspace/local/plans/_unticketed/browser-use-skill-20260426.md`
- **Reference code**: `workspace/dev-knowledge/skills/code/browser_use/`
- **Upstream**: <https://github.com/h4ckf0r0day/obscura>
- **CDP spec**: <https://chromedevtools.github.io/devtools-protocol/>

---

## Reliability fixes (2026-04-26)

**Symptom:** `bu eval` would hang indefinitely on a subset of sites
(xpander.ai, google.com, github.com, etc.) and finally print an empty
`error:` message. example.com and other simple pages worked fine.
100% reproducible on heavy SPAs / font-heavy sites.

**Root cause (3-layer bug):**

1. **Container `/dev/shm` is 64 MB** — Chrome's renderer maps shared GPU
   and IPC memory there. Modern SPAs blow past 64 MB and the kernel kills
   the renderer. Chromium emits `Inspector.targetCrashed`.
2. **Missing system fonts + fontconfig** — chrome-headless-shell on a
   bare Debian container has zero TTF fonts. When a page requests a remote
   web font (Framer, Google Fonts), Blink hits a `NOTREACHED` assertion
   in `remote_font_face_source.cc:365` and crashes the renderer.
3. **`Inspector.targetCrashed` was not surfaced** — after the renderer
   died, the browser-side stopped responding on the WebSocket. The
   in-flight `Runtime.evaluate` `await fut` never resolved — the CLI hung
   for `--timeout` seconds, then bubbled an empty `TimeoutError()` (whose
   `str(e)` is `''`) out of the exception handler.

**Fix (all three layers):**

1. **`browser_subprocess.py` + `daemon.py` chromium argv** — added
   `--disable-dev-shm-usage` (uses /tmp instead of /dev/shm), plus
   `--disable-features=...,IsolateOrigins,site-per-process` and
   `--js-flags=--max-old-space-size=4096` to lower memory pressure.
2. **System fonts** — `apt install fonts-liberation fonts-dejavu-core
   fontconfig` is now a documented prerequisite (see Setup → Option C).
3. **`cdp_client.py`** — new `RendererCrashed(CDPError)` exception,
   `mark_session_crashed()` API, and per-request `sessionId` tracking.
   When `Inspector.targetCrashed` fires for a session, every in-flight
   request bound to that session is failed with `RendererCrashed`
   immediately instead of hanging until timeout. The `pool.py`
   `_on_target_crashed` handler now wires the event into the CDPClient.
   Bare timeouts also wrap to `CDPError(-32001, "timeout after Ns waiting
   for METHOD")` so the user sees a clear error string.
4. **`pool.py` `Page.navigate` / `Page.evaluate`** — subscribe to
   `Page.loadEventFired` BEFORE sending `Page.navigate` (no missed
   events on fast pages); pass `timeout` to Chrome via
   `Runtime.evaluate.timeout` (Chrome-side hard cap on JS execution);
   propagate `RendererCrashed` with a `page.crashed` bus event.

**Validation (after fix):** 18 navigations across 6 sites × 3 rounds
(example.com, xpander.ai, google.com, docs.xpander.ai, github.com,
news.ycombinator.com) — **18/18 PASS, 0 FAIL.**

**If you still see crashes:**
- Check `fc-list | head` returns at least one TTF — if not, install fonts.
- Check `df -h /dev/shm` — if the daemon was started without
  `--disable-dev-shm-usage` (e.g. you have an old daemon running),
  `bu --engine chromium stop && pkill -9 chrome-headless-shell` and start
  again so the new flags take effect.
- `pgrep -af chrome-headless-shell | grep -v zygote` should show
  `--disable-dev-shm-usage --disable-features=...` in the argv.

---

## Cross-Origin Iframes — Drive Them in a New Tab (2026-04-26)

**Problem:** A page embeds a third-party form (Typeform, Calendly, Stripe Checkout) in an `<iframe>` whose `src` is a different origin. `bu eval` running in the parent page **cannot** reach `contentDocument` / `contentWindow` due to same-origin policy — `iframe.contentDocument` returns `null` and querying inputs returns nothing.

**Solution:** Open the iframe's `src` directly in a new tab and drive it as a top-level document.

```bash
# 1. From the parent, enumerate iframes to extract the embed URL
bu eval --target-id <PARENT_TAB> 'JSON.stringify([...document.querySelectorAll("iframe")].map(f=>({src:f.src,title:f.title})))'

# 2. Open the iframe URL as its own tab — sessionId is fresh, no cross-origin barrier
bu new-page <IFRAME_SRC>
# returns targetId=... sessionId=...

# 3. Drive normally with bu type / bu eval / bu screenshot
bu type --target-id <NEW_TAB> 'input[name="..."]' 'value'
```

**Real example:** xpander onboarding wizard embeds Typeform at `https://w6zhy2zvt0h.typeform.com/to/...`. Opening that URL in a new tab let us answer all 13 questions and submit. The parent page received the submission via Typeform's postMessage when the form completed.

---

## Typeform Quirks (2026-04-26)

When automating a Typeform questionnaire, these gotchas cost real time — bake them into the script up-front.

### 1. Per-section "OK" button gates focus on later inputs
After answering all visible questions in a section, you **must click the section's `button[data-qa="ok-button-visible"]`** before later-section inputs accept focus. Symptoms if you skip it: `bu type` reports the value was set but the field is read-only and Submit is disabled. The "OK" button advances Typeform's internal step state and unlocks the next block.

```js
const ok = document.querySelector('button[data-qa="ok-button-visible"]');
ok && ok.click();
```

### 2. Checkbox/option IDs are randomized per render
Multi-select option ids look stable (`checkbox-de47-c2c0-537-571c`) but they are **regenerated on every page render**. Same option ("LangChain") had id `c2c0` in one render and `c8af` after a reload. **Never cache the id** — always re-probe by visible text on each script run:

```js
const target = "LangChain";
const btn = [...document.querySelectorAll('[role="checkbox"], [role="option"]')]
  .find(el => el.innerText.trim() === target || el.getAttribute('aria-label') === target);
btn && btn.click();
```

Use `aria-checked="true"` to verify state after click — it's reliably set by Typeform's React tree.

### 3. Text input IDs ARE stable across renders
Unlike checkboxes, free-text input `id` attributes (e.g. `8e52d071-78c3-4519-a89a-bb92f81a0484` for "I work for") survive re-renders. Safe to capture once via `bu eval` and reuse for `bu type 'input[id="..."]' 'value'`.

### 4. Find the scroll container by walking ancestors
Typeform doesn't use `window.scroll`. The scrollable element is a nested div with `overflow-y: auto` and `scroll-height > client-height` — find it by walking up from any visible block:

```js
function findScroller(el) {
  while (el && el !== document.body) {
    const cs = getComputedStyle(el);
    if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) return el;
    el = el.parentElement;
  }
  return null;
}
```

In this session, the container was `div.grid__Grid-sc-jbfi1d-0` with `scrollHeight=2393`, `clientHeight=~900`.

### 5. React `_valueTracker` setter alone is insufficient when input rejects focus
The classic React-controlled-input trick:
```js
const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
setter.call(input, 'new value');
input.dispatchEvent(new Event('input', { bubbles: true }));
```
**fails silently** if the input is in a section that hasn't been activated yet (see gotcha #1). `document.activeElement` will be `body`, not the input. Fix: click the section's OK button first to grant focus, then `bu type` works normally — no need for the `_valueTracker` hack at all.

### 6. Probe before each script run
Typeform's question order, field ids, and option ids vary by URL parameters and A/B variants. Always start a Typeform automation session with a probe script that dumps `[data-qa-block]` elements and their inputs to JSON, then build the answer script from probe output — not from a guessed schema.

---

## Frontend local dev + OTP + PR screenshots (2026-04-26)

When `bu` is being used against a locally-running `frontend` (`pnpm dev`) for
feature work, OTP login, or capturing PR screenshots, the **deterministic recipe
lives in `workspace/dev-knowledge/skills/frontend_local_dev.md`**. Highlights relevant to this
skill:

- **Daemon = login session.** Don't `bu stop` between tasks — the chromium
  daemon's cookie jar + localStorage holds the Supabase session, and tearing it
  down means another OTP round-trip with the user.
- **Screenshots are always 1920x1080.** The Viewport section of this file already
  enforces it via CDP override. Don't pass `viewport=` overrides for PR shots.
- **Stage before asking.** Drive `bu` to the OTP-input screen first, then ask
  the user for the 6-digit code via `xpask_for_information` — staging codes
  expire in ~5 minutes.
- **Multi-cell OTP forms.** Some Supabase Auth UI variants render six
  single-character `<input>`s. `bu inspect` first; loop one digit per cell.
- **Save shots under `workspace/tmp/screenshots/${TICKET}/`** with descriptive
  names (`before-default.png`, `after-byok.png`, ...), share via
  `xpworkspace-file-share`, embed in the PR per `pr_title_description.md`.
