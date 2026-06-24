"""Spawn / supervise the headless browser as an isolated subprocess.

The agent's main loop never blocks on browser work: this module owns the
Process and a healthcheck task; everything else talks to it via CDP WS.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class SubprocessHandle:
    proc: subprocess.Popen
    port: int
    cmd: List[str]


class BrowserSubprocess:
    """Owns the browser process. Use as an async context manager.

    Attributes
    ----------
    binary : path to the engine binary (obscura) or the launcher (chromium
             via Playwright — in which case `argv` is built differently).
    extra_args : passed verbatim after the subcommand.
    port : if 0 (default), pick a free one.
    stealth : pass `--stealth` (obscura) or skip for chromium.
    """

    def __init__(self,
                 binary: str,
                 mode: str = "obscura",   # "obscura" | "chromium"
                 port: int = 0,
                 stealth: bool = False,
                 extra_args: Optional[List[str]] = None,
                 startup_timeout: float = 15.0) -> None:
        if not shutil.which(binary) and not os.path.isabs(binary):
            raise FileNotFoundError(f"binary not on PATH: {binary}")
        self.binary = binary
        self.mode = mode
        self.port = port or _free_port()
        self.stealth = stealth
        self.extra_args = list(extra_args or [])
        self.startup_timeout = startup_timeout
        self._handle: Optional[SubprocessHandle] = None

    # ------------------------------------------------------------------ argv
    def _argv(self) -> List[str]:
        if self.mode == "obscura":
            argv = [self.binary, "serve", "--port", str(self.port)]
            if self.stealth:
                argv.append("--stealth")
        elif self.mode == "chromium":
            # Direct chrome-headless-shell flags. Caller must point `binary`
            # at the headless shell. (Playwright engine wraps this in engine.py.)
            #
            # STABILITY FLAGS (added 2026-04 after renderer-crash investigation):
            # - `--disable-dev-shm-usage`: containers ship a 64 MB /dev/shm by
            #   default. Modern SPAs (xpander.ai, google.com) blow past that
            #   and Chromium crashes the renderer (Inspector.targetCrashed),
            #   leaving Runtime.evaluate hung forever. This flag puts the
            #   shared memory in /tmp instead.
            # - `--disable-features=...`: turn off heavy renderer features
            #   that don't work in headless and just consume RAM.
            # - `--no-zygote --single-process` are NOT used: they reduce
            #   isolation and cause more crashes, not fewer.
            argv = [
                self.binary,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-software-rasterizer",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=Translate,BackForwardCache,AcceptCHFrame,MediaRouter,OptimizationHints,IsolateOrigins,site-per-process",
                "--metrics-recording-only",
                "--mute-audio",
                "--no-first-run",
                "--no-default-browser-check",
                "--hide-scrollbars",
                "--enable-automation",
                "--password-store=basic",
                "--use-mock-keychain",
                "--js-flags=--max-old-space-size=4096",
                # Always boot at 1920x1080 — desktop FHD baseline. Pages that
                # care about layout (xpander.ai, app.xpander.ai admin UIs)
                # render their desktop breakpoint at this size. Per-page
                # Emulation.setDeviceMetricsOverride in pool.py reinforces
                # this for each tab so it survives renderer recycles.
                "--window-size=1920,1080",
                # NOTE on remote fonts: chrome-headless-shell can hit a
                # NOTREACHED assertion in remote_font_face_source.cc:365 when
                # loading remote web fonts. The fix is to ensure SYSTEM fonts
                # exist (apt install fonts-liberation fonts-dejavu-core
                # fontconfig). Do NOT add --disable-remote-fonts here — it
                # pushes Chromium into a different Skia FATAL when no system
                # fonts are installed. Skill setup must install the fonts.
                "--font-render-hinting=none",
                f"--remote-debugging-port={self.port}",
                "--user-data-dir=/tmp/browser_use_chromium_profile",
            ]
        else:
            raise ValueError(f"unknown mode: {self.mode}")
        argv.extend(self.extra_args)
        return argv

    # ----------------------------------------------------------- lifecycle
    async def __aenter__(self) -> "BrowserSubprocess":
        await self.start()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.stop()

    async def start(self) -> None:
        if self._handle is not None:
            return
        argv = self._argv()
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,    # isolated process group
        )
        self._handle = SubprocessHandle(proc=proc, port=self.port, cmd=argv)
        try:
            await self._wait_for_listening(self.port, self.startup_timeout)
        except TimeoutError:
            await self.stop()
            raise

    async def stop(self) -> None:
        h = self._handle
        if h is None:
            return
        self._handle = None
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(h.proc.pid), signal.SIGTERM)
        try:
            await asyncio.get_event_loop().run_in_executor(None, h.proc.wait, 5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(h.proc.pid), signal.SIGKILL)

    @staticmethod
    async def _wait_for_listening(port: int, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with socket.socket() as s:
                s.settimeout(0.25)
                try:
                    s.connect(("127.0.0.1", port))
                    return
                except (ConnectionRefusedError, socket.timeout, OSError):
                    await asyncio.sleep(0.1)
        raise TimeoutError(f"browser did not bind 127.0.0.1:{port} within {timeout}s")

    # ---------------------------------------------------------------- info
    @property
    def ws_url(self) -> str:
        # Obscura-specific path. For chromium, callers MUST use
        # ChromiumEngine.ws_endpoint() to discover the real WS URL via
        # /json/version. Kept here for obscura back-compat / debug only.
        return f"ws://127.0.0.1:{self.port}/devtools/browser"

    @property
    def is_alive(self) -> bool:
        return self._handle is not None and self._handle.proc.poll() is None
