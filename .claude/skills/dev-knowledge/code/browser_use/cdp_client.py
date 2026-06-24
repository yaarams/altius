"""Async CDP WebSocket client.

All commands return a future resolved by the recv loop. Events are routed
into an asyncio.Queue and (optionally) into the EventBus.

The protocol is simple JSON-RPC-like:
    request:  {id, method, params, sessionId?}
    response: {id, result?, error?, sessionId?}
    event:    {method, params, sessionId?}
"""
from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets

EventHandler = Callable[[Dict[str, Any]], Awaitable[None]]


class CDPError(RuntimeError):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"CDP {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class RendererCrashed(CDPError):
    """Raised when Inspector.targetCrashed fires for the session of an
    in-flight CDP request. Distinct from CDPError so callers can decide
    whether to recreate the tab."""
    def __init__(self, target_id: Optional[str] = None, reason: str = "renderer crashed") -> None:
        super().__init__(-32099, f"renderer crashed (targetId={target_id}): {reason}")
        self.target_id = target_id
        self.reason = reason


class CDPClient:
    def __init__(self, ws_url: str) -> None:
        self.ws_url = ws_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ids = itertools.count(1)
        # _pending maps request id -> (future, sessionId or None). sessionId
        # is tracked so we can fail in-flight requests when the renderer
        # for that session crashes (Inspector.targetCrashed).
        self._pending: Dict[int, tuple] = {}
        # sessions whose renderer has crashed; future sends fail fast.
        self._crashed_sessions: set = set()
        self._event_handlers: Dict[str, EventHandler] = {}
        self._recv_task: Optional[asyncio.Task] = None

    # --------------------------------------------------------- lifecycle
    async def connect(self) -> None:
        self._ws = await websockets.connect(self.ws_url, max_size=10 * 1024 * 1024)
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def close(self) -> None:
        if self._recv_task is not None:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws is not None:
            await self._ws.close()
        self._ws = None

    async def __aenter__(self) -> "CDPClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    # ------------------------------------------------------ public API
    def on_event(self, method: str, handler: EventHandler) -> None:
        """Register a coroutine to be called for every CDP event of `method`."""
        self._event_handlers[method] = handler

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None,
                   session_id: Optional[str] = None,
                   timeout: float = 30.0) -> Dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("CDPClient not connected")
        # Fast-fail if this session's renderer already crashed.
        if session_id is not None and session_id in self._crashed_sessions:
            raise RendererCrashed(reason=f"session {session_id} marked crashed")
        msg_id = next(self._ids)
        msg: Dict[str, Any] = {"id": msg_id, "method": method, "params": params or {}}
        if session_id is not None:
            msg["sessionId"] = session_id
        fut = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = (fut, session_id)
        await self._ws.send(json.dumps(msg))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as e:
            # Clearer error than the bare empty-string TimeoutError.
            raise CDPError(
                -32001,
                f"timeout after {timeout}s waiting for {method}"
                + (f" (session={session_id})" if session_id else ""),
            ) from e
        finally:
            self._pending.pop(msg_id, None)

    def mark_session_crashed(self, session_id: str, target_id: Optional[str] = None,
                             reason: str = "Inspector.targetCrashed") -> None:
        """Called by BrowserPool when Inspector.targetCrashed fires.
        Fails every in-flight request bound to this sessionId with a
        clear RendererCrashed error so callers don't hang."""
        self._crashed_sessions.add(session_id)
        for msg_id, (fut, sid) in list(self._pending.items()):
            if sid == session_id and not fut.done():
                fut.set_exception(RendererCrashed(target_id=target_id, reason=reason))

    # ------------------------------------------------------ internals
    async def _recv_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if "id" in msg:
                    entry = self._pending.get(msg["id"])
                    if entry is None:
                        continue
                    fut, _sid = entry
                    if fut.done():
                        continue
                    if "error" in msg:
                        err = msg["error"]
                        fut.set_exception(CDPError(err.get("code", -1),
                                                   err.get("message", ""),
                                                   err.get("data")))
                    else:
                        fut.set_result(msg.get("result", {}))
                else:
                    method = msg.get("method")
                    handler = self._event_handlers.get(method) if method else None
                    if handler:
                        try:
                            await handler(msg)
                        except Exception:
                            # Never let event handlers tear down recv loop.
                            pass
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass
        finally:
            # Fail any in-flight requests so callers don't hang forever.
            for fut, _sid in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError("CDP connection closed"))
            self._pending.clear()
