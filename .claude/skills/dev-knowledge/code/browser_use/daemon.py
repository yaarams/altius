"""Long-lived browser daemon — runs obscura/chromium in the background so
many agent calls (across processes / sessions) can attach to it.

State is kept in a tiny runtime dir (default: $XDG_RUNTIME_DIR/browser_use/<name>):
    pid       — obscura PID
    port      — CDP port the daemon is listening on
    binary    — path to engine binary used
    engine    — "obscura" | "chromium"
    started   — epoch start time

CLI:
    python3 -m browser_use.daemon start [--engine obscura] [--name default] [--port 0] [--stealth]
    python3 -m browser_use.daemon status [--name default]
    python3 -m browser_use.daemon stop   [--name default]
    python3 -m browser_use.daemon ws-url [--name default]

Programmatic:
    daemon = BrowserDaemon(name="default")
    await daemon.ensure_started(engine="obscura")
    print(daemon.ws_url)             # ws://127.0.0.1:<port>/devtools/browser
    daemon.stop()
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .engine import get_engine
from .browser_subprocess import _free_port


def _runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.expanduser("~/.cache")
    p = Path(base) / "browser_use"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class DaemonState:
    name: str
    pid: int
    port: int
    binary: str
    engine: str
    started: float

    @classmethod
    def load(cls, name: str) -> Optional["DaemonState"]:
        path = _runtime_dir() / f"{name}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return cls(**data)
        except Exception:
            return None

    def save(self) -> None:
        path = _runtime_dir() / f"{self.name}.json"
        path.write_text(json.dumps(self.__dict__))

    @staticmethod
    def remove(name: str) -> None:
        path = _runtime_dir() / f"{name}.json"
        if path.exists():
            path.unlink()

    def is_running(self) -> bool:
        try:
            os.kill(self.pid, 0)
        except OSError:
            return False
        # Cheap health check: TCP connect to port
        with socket.socket() as s:
            s.settimeout(0.2)
            try:
                s.connect(("127.0.0.1", self.port))
                return True
            except OSError:
                return False


class BrowserDaemon:
    def __init__(self, name: str = "default") -> None:
        self.name = name

    @property
    def state(self) -> Optional[DaemonState]:
        return DaemonState.load(self.name)

    @property
    def ws_url(self) -> Optional[str]:
        st = self.state
        if st is None or not st.is_running():
            return None
        # Engine-aware: chromium publishes the WS path via /json/version,
        # obscura uses the fixed /devtools/browser path.
        from .engine import ENGINES
        engine_cls = ENGINES.get(st.engine)
        if engine_cls is None:
            return f"ws://127.0.0.1:{st.port}/devtools/browser"
        try:
            return engine_cls.ws_endpoint("127.0.0.1", st.port, timeout=2.0)
        except Exception:
            return None

    async def ensure_started(self, engine: str = "obscura",
                             port: int = 0, stealth: bool = False,
                             binary: Optional[str] = None,
                             startup_timeout: float = 15.0) -> DaemonState:
        st = self.state
        if st is not None and st.is_running():
            return st
        DaemonState.remove(self.name)

        engine_cls = get_engine(engine)
        cfg = engine_cls.resolve(binary)
        if port == 0:
            port = _free_port()

        if engine == "obscura":
            argv = [cfg.binary, "serve", "--port", str(port)]
            if stealth:
                argv.append("--stealth")
        elif engine == "chromium":
            # Stability flags mirror BrowserSubprocess._argv() chromium branch.
            # Critical: --disable-dev-shm-usage prevents renderer crashes on
            # heavy SPAs in containers with 64 MB /dev/shm. See investigation
            # notes in workspace/dev-knowledge/memory/browser_use_renderer_crash_fix.md.
            argv = [
                cfg.binary,
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
                # Always boot at 1920x1080 — desktop FHD baseline. See
                # browser_subprocess.py for rationale. Per-tab
                # Emulation.setDeviceMetricsOverride in pool.py reinforces.
                "--window-size=1920,1080",
                # NOTE on remote fonts: chrome-headless-shell can hit a
                # NOTREACHED assertion in remote_font_face_source.cc:365 when
                # loading remote web fonts. The fix is to ensure SYSTEM fonts
                # exist (apt install fonts-liberation fonts-dejavu-core
                # fontconfig). Do NOT add --disable-remote-fonts here — it
                # pushes Chromium into a different Skia FATAL when no system
                # fonts are installed. Skill setup must install the fonts.
                "--font-render-hinting=none",
                f"--remote-debugging-port={port}",
                f"--user-data-dir=/tmp/browser_use_chromium_profile_{self.name}",
            ]
        else:
            raise ValueError(f"unknown engine: {engine}")

        log_path = _runtime_dir() / f"{self.name}.log"
        log_fd = open(log_path, "ab", buffering=0)
        proc = subprocess.Popen(
            argv,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
            close_fds=True,
        )
        st = DaemonState(name=self.name, pid=proc.pid, port=port,
                         binary=cfg.binary, engine=engine, started=time.time())
        st.save()

        deadline = time.monotonic() + startup_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                DaemonState.remove(self.name)
                raise RuntimeError(f"daemon exited early; see {log_path}")
            with socket.socket() as s:
                s.settimeout(0.25)
                try:
                    s.connect(("127.0.0.1", port))
                    return st
                except OSError:
                    await asyncio.sleep(0.1)
        # Timed out
        self.stop()
        raise TimeoutError(f"daemon did not bind 127.0.0.1:{port} within {startup_timeout}s")

    def stop(self) -> bool:
        st = self.state
        if st is None:
            return False
        try:
            os.killpg(os.getpgid(st.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        # Wait briefly for clean exit
        for _ in range(20):
            try:
                os.kill(st.pid, 0)
            except OSError:
                break
            time.sleep(0.1)
        else:
            try:
                os.killpg(os.getpgid(st.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        DaemonState.remove(self.name)
        return True


# ---------------------------------------------------------------- CLI
def _cli() -> int:
    ap = argparse.ArgumentParser(prog="browser_use.daemon")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "stop", "status", "ws-url"):
        sp = sub.add_parser(name)
        sp.add_argument("--name", default="default")
        if name == "start":
            sp.add_argument("--engine", default="obscura", choices=["obscura", "chromium"])
            sp.add_argument("--port", type=int, default=0)
            sp.add_argument("--stealth", action="store_true")
            sp.add_argument("--binary", default=None)
    args = ap.parse_args()
    d = BrowserDaemon(args.name)

    if args.cmd == "start":
        st = asyncio.run(d.ensure_started(
            engine=args.engine, port=args.port,
            stealth=args.stealth, binary=args.binary))
        print(json.dumps(st.__dict__, indent=2))
        return 0
    if args.cmd == "stop":
        ok = d.stop()
        print(json.dumps({"stopped": ok, "name": args.name}))
        return 0
    if args.cmd == "status":
        st = d.state
        if st is None:
            print(json.dumps({"running": False, "name": args.name}))
            return 1
        running = st.is_running()
        out = {"running": running, **st.__dict__,
               "ws_url": d.ws_url if running else None}
        print(json.dumps(out, indent=2))
        return 0 if running else 2
    if args.cmd == "ws-url":
        url = d.ws_url
        if url is None:
            print("", end="")
            return 2
        print(url)
        return 0
    return 1

if __name__ == "__main__":
    sys.exit(_cli())
