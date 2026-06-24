"""BrowserPool — a single browser subprocess hosting many per-task Pages.

   async with BrowserPool(engine="obscura") as pool:
       page = await pool.new_page()
       await page.navigate("https://xpander.ai/")
       data = await page.evaluate("document.title")
       await page.close()

A Page is a CDP target (tab) with its own sessionId. Multiple Pages share
the same WebSocket connection (one CDPClient per pool) but are isolated
from each other at the session level.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from .browser_subprocess import BrowserSubprocess
from .cdp_client import CDPClient, CDPError, RendererCrashed
from .engine import get_engine, EngineConfig
from .events import BrowserEvent, EventBus


class Page:
    """A single tab. One sessionId, one URL at a time."""

    def __init__(self, pool: "BrowserPool", target_id: str, session_id: str) -> None:
        self._pool = pool
        self.target_id = target_id
        self.session_id = session_id

    # ----------------------------------------------------- navigation
    async def navigate(self, url: str, timeout: float = 30.0) -> Dict[str, Any]:
        try:
            await self._pool._cdp.send("Page.enable", session_id=self.session_id, timeout=5)
        except CDPError:
            pass
        # Subscribe to lifecycle BEFORE navigating so we don't miss the load
        # event on fast pages.
        load_waiter = asyncio.create_task(self._wait_event("Page.loadEventFired"))
        try:
            result = await self._pool._cdp.send(
                "Page.navigate", {"url": url},
                session_id=self.session_id, timeout=timeout)
            try:
                await asyncio.wait_for(load_waiter, timeout=timeout)
            except asyncio.TimeoutError:
                # Navigation succeeded but load event didn't fire within
                # the budget (heavy SPA). That's not a fatal error; the
                # caller can still drive the page.
                pass
        except RendererCrashed as e:
            # Surface a clear, actionable error instead of hanging.
            await self._pool.bus.publish(
                BrowserEvent("page.crashed", self.target_id, {"url": url, "reason": str(e)}))
            raise
        finally:
            if not load_waiter.done():
                load_waiter.cancel()
                try:
                    await load_waiter
                except (asyncio.CancelledError, Exception):
                    pass
        await self._pool.bus.publish(BrowserEvent("page.loaded", self.target_id, {"url": url}))
        return result

    async def url(self) -> str:
        return await self.evaluate("location.href")

    async def title(self) -> str:
        return await self.evaluate("document.title")

    # ------------------------------------------------------- evaluate
    async def evaluate(self, expression: str, *, return_by_value: bool = True,
                       await_promise: bool = True, timeout: float = 30.0) -> Any:
        # Wrap in IIFE so multi-line / statement expressions work and the last
        # value is returned.
        wrapped = f"(()=>{{ return ({expression}); }})()"
        try:
            result = await self._pool._cdp.send(
                "Runtime.evaluate",
                {"expression": wrapped,
                 "returnByValue": return_by_value,
                 "awaitPromise": await_promise,
                 # Chrome-side timeout (ms) — defends against await_promise
                 # hanging on a never-resolving JS promise.
                 "timeout": int(max(1.0, timeout - 0.5) * 1000)},
                session_id=self.session_id, timeout=timeout)
        except RendererCrashed:
            await self._pool.bus.publish(
                BrowserEvent("page.crashed", self.target_id, {"expression": expression[:120]}))
            raise
        details = result.get("exceptionDetails")
        if details is not None:
            text = details.get("text", "JS error")
            await self._pool.bus.publish(
                BrowserEvent("page.error", self.target_id, {"details": details}))
            raise CDPError(-32000, text, details)
        return result.get("result", {}).get("value")

    # -------------------------------------------------- DOM helpers
    async def inspect(self, *, max_buttons: int = 40, max_inputs: int = 40) -> Dict[str, Any]:
        """Return a structured summary of the current page — useful for the agent
        to decide what to click/type next without hand-writing JS each time."""
        expr = """(() => {
            const trim = (s, n=120) => (s||'').toString().trim().slice(0,n);
            const inputs = [...document.querySelectorAll('input,textarea,select')]
                .slice(0, %(MI)d)
                .map(e => ({tag:e.tagName.toLowerCase(), type:e.type||'', name:e.name||'', id:e.id||'',
                            placeholder:e.placeholder||'', required:!!e.required,
                            label:(e.labels && e.labels[0] ? trim(e.labels[0].innerText,60) : ''),
                            value:trim(e.value,60), visible:!!(e.offsetWidth||e.offsetHeight)}));
            const clickables = [...document.querySelectorAll('button,a,[role=\"button\"]')]
                .slice(0, %(MB)d)
                .map(e => ({tag:e.tagName.toLowerCase(), text:trim(e.innerText,80),
                            href:e.getAttribute('href')||'', type:e.getAttribute('type')||'',
                            id:e.id||'', name:e.getAttribute('name')||'',
                            visible:!!(e.offsetWidth||e.offsetHeight)}));
            const headings = [...document.querySelectorAll('h1,h2,h3')]
                .slice(0,12).map(e => ({tag:e.tagName.toLowerCase(), text:trim(e.innerText,120)}));
            const forms = [...document.querySelectorAll('form')]
                .map(f => ({action:f.action||'', method:f.method||'',
                            fields:[...f.elements].slice(0,10).map(x=>x.name||x.id||x.type||'')}));
            return {url:location.href, title:document.title,
                    bodyLen: document.body ? document.body.innerText.length : 0,
                    headings, inputs, clickables, forms};
        })()""" % {"MB": max_buttons, "MI": max_inputs}
        return await self.evaluate(expr)

    async def text(self, selector: Optional[str] = None) -> str:
        if selector is None:
            return await self.evaluate("document.body ? document.body.innerText : ''")
        sel_json = json.dumps(selector)
        return await self.evaluate(
            f"(() => {{ const el=document.querySelector({sel_json}); return el? el.innerText : null; }})()")

    async def html(self, selector: Optional[str] = None) -> str:
        if selector is None:
            return await self.evaluate("document.documentElement.outerHTML")
        sel_json = json.dumps(selector)
        return await self.evaluate(
            f"(() => {{ const el=document.querySelector({sel_json}); return el? el.outerHTML : null; }})()")

    # ------------------------------------------ interactions (selector based)
    async def wait_for_selector(self, selector: str, *, timeout: float = 15.0,
                                visible: bool = False, poll: float = 0.25) -> bool:
        import time as _t
        sel_json = json.dumps(selector)
        deadline = _t.monotonic() + timeout
        check = ("!!document.querySelector(" + sel_json + ")" if not visible
                 else "(() => {const el=document.querySelector(" + sel_json + ");"
                      " return !!(el && (el.offsetWidth||el.offsetHeight));})()")
        while _t.monotonic() < deadline:
            try:
                ok = await self.evaluate(check)
                if ok:
                    return True
            except CDPError:
                pass
            await asyncio.sleep(poll)
        return False

    async def click(self, selector: str, *, timeout: float = 10.0) -> Dict[str, Any]:
        if not await self.wait_for_selector(selector, timeout=timeout):
            raise RuntimeError(f"click: selector not found: {selector}")
        sel_json = json.dumps(selector)
        return await self.evaluate(
            "(() => {"
            f"const el=document.querySelector({sel_json});"
            " if(!el) return {ok:false,reason:'missing'};"
            " el.scrollIntoView({block:'center'});"
            " const r=el.getBoundingClientRect();"
            " el.click();"
            " return {ok:true, tag:el.tagName.toLowerCase(), text:(el.innerText||'').trim().slice(0,80),"
            "         x:r.x|0, y:r.y|0};"
            "})()")

    async def type(self, selector: str, text: str, *, clear: bool = True,
                   submit: bool = False, timeout: float = 10.0) -> Dict[str, Any]:
        if not await self.wait_for_selector(selector, timeout=timeout):
            raise RuntimeError(f"type: selector not found: {selector}")
        sel_json = json.dumps(selector)
        text_json = json.dumps(text)
        return await self.evaluate(
            "(() => {"
            f"const el=document.querySelector({sel_json});"
            " if(!el) return {ok:false,reason:'missing'};"
            " el.focus();"
            f" if({str(clear).lower()}) {{ el.value=''; }}"
            f" const v={text_json};"
            " const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value')"
            "               || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value');"
            " if(setter && setter.set) setter.set.call(el, (el.value||'')+v); else el.value=(el.value||'')+v;"
            " el.dispatchEvent(new Event('input',{bubbles:true}));"
            " el.dispatchEvent(new Event('change',{bubbles:true}));"
            f" if({str(submit).lower()} && el.form) {{ el.form.requestSubmit ? el.form.requestSubmit() : el.form.submit(); }}"
            " return {ok:true, value:(el.value||'').slice(0,120)};"
            "})()")

    async def select(self, selector: str, value: str, *, timeout: float = 10.0) -> Dict[str, Any]:
        if not await self.wait_for_selector(selector, timeout=timeout):
            raise RuntimeError(f"select: selector not found: {selector}")
        sel_json = json.dumps(selector); val_json = json.dumps(value)
        return await self.evaluate(
            "(() => {"
            f"const el=document.querySelector({sel_json});"
            " if(!el) return {ok:false,reason:'missing'};"
            f" el.value={val_json};"
            " el.dispatchEvent(new Event('input',{bubbles:true}));"
            " el.dispatchEvent(new Event('change',{bubbles:true}));"
            " return {ok:true, value:el.value};"
            "})()")

    async def press(self, key: str, *, selector: Optional[str] = None) -> Dict[str, Any]:
        """Dispatch a synthetic keyboard event. For real key delivery use Input.dispatchKeyEvent."""
        params = {"type": "keyDown", "key": key}
        await self._pool._cdp.send("Input.dispatchKeyEvent", params,
                                   session_id=self.session_id, timeout=5)
        await self._pool._cdp.send("Input.dispatchKeyEvent", {**params, "type": "keyUp"},
                                   session_id=self.session_id, timeout=5)
        return {"ok": True, "key": key}

    # --------------------------------------------------------- screenshot
    async def screenshot(self, *, format: str = "png", timeout: float = 30.0) -> bytes:
        import base64
        result = await self._pool._cdp.send(
            "Page.captureScreenshot", {"format": format},
            session_id=self.session_id, timeout=timeout)
        return base64.b64decode(result.get("data", ""))

    # ---------------------------------------------------------- cookies
    async def cookies(self) -> List[Dict[str, Any]]:
        result = await self._pool._cdp.send(
            "Storage.getCookies", {}, session_id=self.session_id, timeout=10)
        return result.get("cookies", [])

    async def close(self) -> None:
        try:
            await self._pool._cdp.send(
                "Target.closeTarget", {"targetId": self.target_id})
        finally:
            self._pool._pages.pop(self.target_id, None)

    # ----------------------------------------------------- helpers
    async def _wait_event(self, method: str) -> None:
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _handler(msg: Dict[str, Any]) -> None:
            if msg.get("sessionId") == self.session_id and not future.done():
                future.set_result(None)

        self._pool._cdp.on_event(method, _handler)
        try:
            await future
        finally:
            self._pool._cdp._event_handlers.pop(method, None)  # type: ignore[attr-defined]


class BrowserPool:
    # Default viewport for every page. Always 1920x1080 (desktop FHD baseline)
    # unless explicitly overridden via ctor or env BROWSER_USE_VIEWPORT=WxH.
    # Applied per-tab via Emulation.setDeviceMetricsOverride in new_page() and
    # attach_to_target() so it works for both obscura and chromium and
    # survives renderer recycles. Chromium argv also carries
    # --window-size=1920,1080 as a belt-and-braces hint to the OS window.
    DEFAULT_VIEWPORT: tuple = (1920, 1080)

    def __init__(self,
                 engine: str = "obscura",
                 *,
                 binary: Optional[str] = None,
                 port: int = 0,
                 stealth: bool = False,
                 bus: Optional[EventBus] = None,
                 viewport: Optional[tuple] = None) -> None:
        self.engine_name = engine
        self._engine_cls = get_engine(engine)
        self._cfg: EngineConfig = self._engine_cls.resolve(binary)
        from .engine import ENGINES as _ENGINES
        self._concrete_engine_cls = _ENGINES.get(self._cfg.name, self._engine_cls)
        self._port = port
        self._stealth = stealth
        self.bus = bus or EventBus()
        self._sub: Optional[BrowserSubprocess] = None
        self._cdp: Optional[CDPClient] = None
        self._pages: Dict[str, Page] = {}
        # Resolve viewport: ctor arg → env override → class default.
        import os as _os
        env_vp = _os.environ.get("BROWSER_USE_VIEWPORT")
        if viewport is not None:
            self.viewport = tuple(viewport)
        elif env_vp and "x" in env_vp.lower():
            try:
                w, h = env_vp.lower().split("x", 1)
                self.viewport = (int(w), int(h))
            except ValueError:
                self.viewport = self.DEFAULT_VIEWPORT
        else:
            self.viewport = self.DEFAULT_VIEWPORT

    # --------------------------------------------------------- lifecycle
    async def __aenter__(self) -> "BrowserPool":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    async def start(self) -> None:
        self._sub = self._engine_cls.make_subprocess(
            self._cfg, port=self._port, stealth=self._stealth)
        await self._sub.start()
        loop = asyncio.get_event_loop()
        ws_url = await loop.run_in_executor(
            None,
            lambda: self._concrete_engine_cls.ws_endpoint(
                "127.0.0.1", self._sub.port))
        self._cdp = CDPClient(ws_url)
        await self._cdp.connect()
        self._cdp.on_event("Inspector.targetCrashed", self._on_target_crashed)

    @classmethod
    async def attach(cls, ws_url: str, *,
                     bus: Optional[EventBus] = None,
                     viewport: Optional[tuple] = None) -> "BrowserPool":
        """Connect to a long-running browser daemon (no subprocess spawned)."""
        self = cls.__new__(cls)
        self.engine_name = "attached"
        self._engine_cls = None      # type: ignore[assignment]
        self._cfg = None             # type: ignore[assignment]
        self._port = 0
        self._stealth = False
        self.bus = bus or EventBus()
        self._sub = None
        self._cdp = CDPClient(ws_url)
        self._pages = {}
        # Resolve viewport (default 1920x1080) — mirrors __init__ logic.
        import os as _os
        env_vp = _os.environ.get("BROWSER_USE_VIEWPORT")
        if viewport is not None:
            self.viewport = tuple(viewport)
        elif env_vp and "x" in env_vp.lower():
            try:
                w, h = env_vp.lower().split("x", 1)
                self.viewport = (int(w), int(h))
            except ValueError:
                self.viewport = cls.DEFAULT_VIEWPORT
        else:
            self.viewport = cls.DEFAULT_VIEWPORT
        await self._cdp.connect()
        self._cdp.on_event("Inspector.targetCrashed", self._on_target_crashed)
        return self

    async def stop(self) -> None:
        for page in list(self._pages.values()):
            try:
                await page.close()
            except Exception:
                pass
        if self._cdp is not None:
            await self._cdp.close()
            self._cdp = None
        if self._sub is not None:
            await self._sub.stop()
            self._sub = None

    # ------------------------------------------------------------- API
    async def new_page(self, *, url: str = "about:blank") -> Page:
        assert self._cdp is not None
        created = await self._cdp.send("Target.createTarget", {"url": url})
        target_id = created["targetId"]
        attached = await self._cdp.send(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = attached["sessionId"]
        page = Page(self, target_id, session_id)
        self._pages[target_id] = page
        await self._apply_viewport(session_id)
        return page

    async def attach_to_target(self, target_id: str) -> Page:
        """Attach to an existing target (tab) by id and return a Page."""
        assert self._cdp is not None
        if target_id in self._pages:
            return self._pages[target_id]
        attached = await self._cdp.send(
            "Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = attached["sessionId"]
        page = Page(self, target_id, session_id)
        self._pages[target_id] = page
        await self._apply_viewport(session_id)
        return page

    async def _apply_viewport(self, session_id: str) -> None:
        """Force every new/attached tab to the configured viewport.

        Default 1920x1080. Uses Emulation.setDeviceMetricsOverride which
        works identically across obscura and chromium and survives renderer
        recycles. Failures are non-fatal — a missing emulation domain on a
        minimal engine should not break the whole tab attach.
        """
        w, h = self.viewport
        try:
            await self._cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": int(w),
                    "height": int(h),
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
                session_id=session_id, timeout=5)
        except CDPError:
            # Engine doesn't support emulation — the --window-size argv flag
            # is the fallback. Don't raise.
            pass

    async def list_targets(self, *, kind: str = "page") -> List[Dict[str, Any]]:
        """List open browser targets. kind='page' returns only tabs."""
        assert self._cdp is not None
        result = await self._cdp.send("Target.getTargets", {})
        targets = result.get("targetInfos", [])
        if kind:
            targets = [t for t in targets if t.get("type") == kind]
        return targets

    async def _on_target_crashed(self, msg: Dict[str, Any]) -> None:
        """Inspector.targetCrashed handler.

        Critical: when a renderer crashes, every in-flight CDP request
        bound to its sessionId would otherwise hang forever (Chromium
        never responds, so `await fut` in CDPClient never resolves).
        We must:
          1. Look up the sessionId for the crashed targetId.
          2. Tell CDPClient to fail all pending requests for that session.
          3. Drop the page from our pool so callers know to recreate it.
          4. Publish a `target.crashed` bus event for observers.

        This handler is registered both on `start()` (owned subprocess)
        and `attach()` (daemon mode), so it runs in every flow.
        """
        params = msg.get("params", {})
        target_id = params.get("targetId")
        # Inspector.targetCrashed itself doesn't carry sessionId in params,
        # but the wrapper message does (when flatten attach is used).
        session_id = msg.get("sessionId")
        reason = params.get("reason") or params.get("errorMessage") or "renderer crashed"

        # Resolve sessionId from our own page registry if the event didn't
        # carry it (older Chrome versions, or when a parent target dies).
        page = self._pages.get(target_id) if target_id else None
        if session_id is None and page is not None:
            session_id = page.session_id

        # Fail every in-flight request on that session so callers see a
        # RendererCrashed error instead of hanging.
        if self._cdp is not None and session_id:
            try:
                self._cdp.mark_session_crashed(session_id, target_id=target_id, reason=reason)
            except Exception:
                pass

        # Drop the page (caller must create a new one).
        if target_id and target_id in self._pages:
            self._pages.pop(target_id, None)

        # Notify observers.
        try:
            await self.bus.publish(
                BrowserEvent("target.crashed", target_id, {**params, "sessionId": session_id}))
        except Exception:
            pass
