"""browser_use.cli — generic, agent-friendly browser commands.

The whole point of this module is so the agent NEVER has to write a one-off
Python script just to click a button or read a form. Every action is a
single subcommand that prints a JSON result on stdout.

State (active daemon + active tab) is persisted under
``$XDG_RUNTIME_DIR/browser_use/<name>.active.json`` so consecutive CLI calls
share the same tab and the agent can build up a flow over many turns.

Usage (always one action per call):

    bu start [--engine chromium|obscura|auto] [--name default]
    bu stop  [--name default]
    bu status
    bu new-page [URL]                 # opens new tab, sets it active
    bu tabs                           # list tabs
    bu use <targetId>                 # switch active tab
    bu navigate <URL>                 # active tab → URL
    bu inspect [--max-buttons 40] [--max-inputs 40]
    bu eval '<JS expression>'
    bu click '<css selector>'
    bu type '<css selector>' '<text>' [--submit] [--no-clear]
    bu select '<css selector>' '<value>'
    bu press <Key>                    # e.g. Enter, Tab
    bu wait '<css selector>' [--timeout 15] [--visible]
    bu text [<css selector>]          # innerText (whole page or one element)
    bu html [<css selector>]
    bu url
    bu title
    bu cookies
    bu screenshot [<path>]            # default workspace/tmp/screenshots/<ts>.png
    bu close-tab

Exit code is non-zero on failure; stderr carries the human-readable error.
All commands implicitly ensure the daemon is running and that an active tab
exists (auto-creating ``about:blank`` if not).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .daemon import BrowserDaemon, _runtime_dir
from .pool import BrowserPool, Page


DEFAULT_ENGINE = os.environ.get("BROWSER_USE_ENGINE", "chromium")


# ------------------------------------------------------------ active state
def _active_path(name: str) -> Path:
    return _runtime_dir() / f"{name}.active.json"


def _load_active(name: str) -> Optional[str]:
    p = _active_path(name)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text()).get("targetId")
    except Exception:
        return None


def _save_active(name: str, target_id: Optional[str]) -> None:
    p = _active_path(name)
    if target_id is None:
        if p.exists():
            p.unlink()
        return
    p.write_text(json.dumps({"targetId": target_id, "saved": time.time()}))


# ----------------------------------------------------------- daemon helper
async def _ensure_pool(name: str, engine: str) -> tuple[BrowserDaemon, BrowserPool]:
    d = BrowserDaemon(name=name)
    await d.ensure_started(engine=engine)
    pool = await BrowserPool.attach(d.ws_url)
    return d, pool


async def _ensure_active_page(pool: BrowserPool, name: str,
                              auto_create: bool = True) -> Page:
    target_id = _load_active(name)
    if target_id:
        # Verify it still exists
        targets = await pool.list_targets()
        if any(t.get("targetId") == target_id for t in targets):
            return await pool.attach_to_target(target_id)
    # No valid active tab — reuse first 'page' target if any, else create.
    targets = await pool.list_targets()
    if targets:
        target_id = targets[0]["targetId"]
        page = await pool.attach_to_target(target_id)
        _save_active(name, target_id)
        return page
    if not auto_create:
        raise RuntimeError("No active tab. Run: bu new-page [URL]")
    page = await pool.new_page()
    _save_active(name, page.target_id)
    return page


# --------------------------------------------------------------- output
def _print(value: Any) -> None:
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print(value)


# --------------------------------------------------------------- commands
async def cmd_start(args) -> int:
    # Allow --engine after the subcommand too, e.g. `bu start --engine chromium`.
    # Subcommand-level value (engine_sub) takes precedence over the global flag
    # so users can override per-call without re-typing `--name`.
    engine = getattr(args, "engine_sub", None) or args.engine
    d = BrowserDaemon(name=args.name)
    st = await d.ensure_started(engine=engine, port=args.port,
                                stealth=args.stealth, binary=args.binary)
    out = dict(st.__dict__)
    out["ws_url"] = d.ws_url
    _print(out)
    return 0


async def cmd_stop(args) -> int:
    d = BrowserDaemon(name=args.name)
    ok = d.stop()
    _save_active(args.name, None)
    _print({"stopped": ok, "name": args.name})
    return 0


async def cmd_status(args) -> int:
    d = BrowserDaemon(name=args.name)
    st = d.state
    if st is None:
        _print({"running": False, "name": args.name})
        return 1
    out = {"running": st.is_running(), **st.__dict__,
           "ws_url": d.ws_url, "active_target": _load_active(args.name)}
    _print(out)
    return 0


async def cmd_new_page(args) -> int:
    _, pool = await _ensure_pool(args.name, args.engine)
    try:
        page = await pool.new_page(url=args.url or "about:blank")
        _save_active(args.name, page.target_id)
        info = {"targetId": page.target_id, "sessionId": page.session_id,
                "url": args.url or "about:blank"}
        _print(info)
        return 0
    finally:
        await pool._cdp.close()


async def cmd_tabs(args) -> int:
    _, pool = await _ensure_pool(args.name, args.engine)
    try:
        targets = await pool.list_targets()
        active = _load_active(args.name)
        for t in targets:
            t["active"] = (t.get("targetId") == active)
        _print(targets)
        return 0
    finally:
        await pool._cdp.close()


async def cmd_use(args) -> int:
    _, pool = await _ensure_pool(args.name, args.engine)
    try:
        targets = await pool.list_targets()
        if not any(t.get("targetId") == args.target_id for t in targets):
            print(f"target not found: {args.target_id}", file=sys.stderr)
            return 2
        _save_active(args.name, args.target_id)
        _print({"active": args.target_id})
        return 0
    finally:
        await pool._cdp.close()


async def _with_active_page(args, op):
    _, pool = await _ensure_pool(args.name, args.engine)
    try:
        page = await _ensure_active_page(pool, args.name)
        return await op(page)
    finally:
        await pool._cdp.close()


async def cmd_navigate(args) -> int:
    async def op(page):
        await page.navigate(args.url, timeout=args.timeout)
        info = await page.evaluate("({url:location.href, title:document.title})")
        _print({**info, "targetId": page.target_id})
        return 0
    return await _with_active_page(args, op)


async def cmd_inspect(args) -> int:
    async def op(page):
        data = await page.inspect(max_buttons=args.max_buttons,
                                  max_inputs=args.max_inputs)
        _print(data)
        return 0
    return await _with_active_page(args, op)


async def cmd_eval(args) -> int:
    async def op(page):
        try:
            value = await page.evaluate(args.expression, timeout=args.timeout)
        except Exception as e:
            print(f"eval error: {e}", file=sys.stderr)
            return 3
        _print(value)
        return 0
    return await _with_active_page(args, op)


async def cmd_click(args) -> int:
    async def op(page):
        try:
            r = await page.click(args.selector, timeout=args.timeout)
        except Exception as e:
            print(f"click error: {e}", file=sys.stderr); return 3
        _print(r); return 0
    return await _with_active_page(args, op)


async def cmd_type(args) -> int:
    async def op(page):
        try:
            r = await page.type(args.selector, args.text, clear=not args.no_clear,
                                submit=args.submit, timeout=args.timeout)
        except Exception as e:
            print(f"type error: {e}", file=sys.stderr); return 3
        _print(r); return 0
    return await _with_active_page(args, op)


async def cmd_select(args) -> int:
    async def op(page):
        try:
            r = await page.select(args.selector, args.value, timeout=args.timeout)
        except Exception as e:
            print(f"select error: {e}", file=sys.stderr); return 3
        _print(r); return 0
    return await _with_active_page(args, op)


async def cmd_press(args) -> int:
    async def op(page):
        r = await page.press(args.key)
        _print(r); return 0
    return await _with_active_page(args, op)


async def cmd_wait(args) -> int:
    async def op(page):
        ok = await page.wait_for_selector(args.selector, timeout=args.timeout,
                                          visible=args.visible)
        _print({"found": ok, "selector": args.selector})
        return 0 if ok else 4
    return await _with_active_page(args, op)


async def cmd_text(args) -> int:
    async def op(page):
        v = await page.text(args.selector)
        if v is None:
            print("selector not found", file=sys.stderr); return 4
        # Print raw (don't quote-encode large text blobs).
        sys.stdout.write(str(v))
        if not str(v).endswith("\n"):
            sys.stdout.write("\n")
        return 0
    return await _with_active_page(args, op)


async def cmd_html(args) -> int:
    async def op(page):
        v = await page.html(args.selector)
        if v is None:
            print("selector not found", file=sys.stderr); return 4
        sys.stdout.write(str(v))
        if not str(v).endswith("\n"):
            sys.stdout.write("\n")
        return 0
    return await _with_active_page(args, op)


async def cmd_url(args) -> int:
    async def op(page):
        _print(await page.url()); return 0
    return await _with_active_page(args, op)


async def cmd_title(args) -> int:
    async def op(page):
        _print(await page.title()); return 0
    return await _with_active_page(args, op)


async def cmd_cookies(args) -> int:
    async def op(page):
        _print(await page.cookies()); return 0
    return await _with_active_page(args, op)


async def cmd_screenshot(args) -> int:
    async def op(page):
        png = await page.screenshot()
        path = args.path
        if not path:
            ts = time.strftime("%Y%m%d-%H%M%S")
            path = f"workspace/tmp/screenshots/{ts}.png"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(png)
        _print({"path": path, "bytes": len(png)})
        return 0
    return await _with_active_page(args, op)


async def cmd_close_tab(args) -> int:
    _, pool = await _ensure_pool(args.name, args.engine)
    try:
        target_id = _load_active(args.name)
        if not target_id:
            print("no active tab", file=sys.stderr); return 1
        page = await pool.attach_to_target(target_id)
        await page.close()
        _save_active(args.name, None)
        _print({"closed": target_id})
        return 0
    finally:
        await pool._cdp.close()


# --------------------------------------------------------------- argparse
def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bu", description="browser_use CLI")
    ap.add_argument("--name", default="default", help="daemon name")
    ap.add_argument("--engine", default=DEFAULT_ENGINE, choices=["obscura", "chromium", "auto"])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start");  sp.add_argument("--port", type=int, default=0); sp.add_argument("--stealth", action="store_true"); sp.add_argument("--binary", default=None); sp.add_argument("--engine", dest="engine_sub", default=None, choices=["obscura", "chromium", "auto"], help="engine override (also accepted as global flag before subcommand)"); sp.set_defaults(func=cmd_start)
    sp = sub.add_parser("stop");   sp.set_defaults(func=cmd_stop)
    sp = sub.add_parser("status"); sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("new-page"); sp.add_argument("url", nargs="?", default=None); sp.set_defaults(func=cmd_new_page)
    sp = sub.add_parser("tabs");     sp.set_defaults(func=cmd_tabs)
    sp = sub.add_parser("use");      sp.add_argument("target_id"); sp.set_defaults(func=cmd_use)
    sp = sub.add_parser("close-tab"); sp.set_defaults(func=cmd_close_tab)

    sp = sub.add_parser("navigate"); sp.add_argument("url"); sp.add_argument("--timeout", type=float, default=30); sp.set_defaults(func=cmd_navigate)
    sp = sub.add_parser("inspect");  sp.add_argument("--max-buttons", type=int, default=40); sp.add_argument("--max-inputs", type=int, default=40); sp.set_defaults(func=cmd_inspect)
    sp = sub.add_parser("eval");     sp.add_argument("expression"); sp.add_argument("--timeout", type=float, default=30); sp.set_defaults(func=cmd_eval)
    sp = sub.add_parser("click");    sp.add_argument("selector"); sp.add_argument("--timeout", type=float, default=10); sp.set_defaults(func=cmd_click)
    sp = sub.add_parser("type");     sp.add_argument("selector"); sp.add_argument("text"); sp.add_argument("--no-clear", action="store_true"); sp.add_argument("--submit", action="store_true"); sp.add_argument("--timeout", type=float, default=10); sp.set_defaults(func=cmd_type)
    sp = sub.add_parser("select");   sp.add_argument("selector"); sp.add_argument("value"); sp.add_argument("--timeout", type=float, default=10); sp.set_defaults(func=cmd_select)
    sp = sub.add_parser("press");    sp.add_argument("key"); sp.set_defaults(func=cmd_press)
    sp = sub.add_parser("wait");     sp.add_argument("selector"); sp.add_argument("--timeout", type=float, default=15); sp.add_argument("--visible", action="store_true"); sp.set_defaults(func=cmd_wait)
    sp = sub.add_parser("text");     sp.add_argument("selector", nargs="?", default=None); sp.set_defaults(func=cmd_text)
    sp = sub.add_parser("html");     sp.add_argument("selector", nargs="?", default=None); sp.set_defaults(func=cmd_html)
    sp = sub.add_parser("url");      sp.set_defaults(func=cmd_url)
    sp = sub.add_parser("title");    sp.set_defaults(func=cmd_title)
    sp = sub.add_parser("cookies");  sp.set_defaults(func=cmd_cookies)
    sp = sub.add_parser("screenshot"); sp.add_argument("path", nargs="?", default=None); sp.set_defaults(func=cmd_screenshot)
    return ap


def main(argv: Optional[list] = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)
    try:
        return asyncio.run(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
