"""Engine adapters — how to find / launch each backend.

ObscuraEngine: locates `obscura` binary (PATH, /usr/local/bin, workspace, env).
ChromiumEngine: locates Playwright's bundled chrome-headless-shell.

Both produce a configured BrowserSubprocess; the rest of the stack is
identical because both engines speak CDP. WS URL discovery differs:
  - obscura:  fixed at ws://host:port/devtools/browser (no HTTP discovery)
  - chromium: must hit http://host:port/json/version and read webSocketDebuggerUrl

See `ws_endpoint()` for the engine-specific WS URL resolver.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from .browser_subprocess import BrowserSubprocess


# Where ObscuraEngine looks for the binary, in order of preference.
# Override with $OBSCURA_BIN.
OBSCURA_SEARCH_PATHS: List[str] = [
    "/usr/local/bin/obscura",
    "/agent/data/workspace/tmp/obscura-src/target/release/obscura",
    os.path.expanduser("~/.local/bin/obscura"),
    "/opt/obscura/obscura",
]


@dataclass
class EngineConfig:
    name: str                  # "obscura" | "chromium"
    binary: str                # path to executable
    mode: str                  # forwarded to BrowserSubprocess
    stealth: bool = False


# --------------------------------------------------------------------------
# Obscura
# --------------------------------------------------------------------------
class ObscuraEngine:
    name = "obscura"

    @staticmethod
    def find_binary(binary: Optional[str] = None) -> Optional[str]:
        if binary and os.path.isfile(binary) and os.access(binary, os.X_OK):
            return binary
        env = os.environ.get("OBSCURA_BIN")
        if env and os.path.isfile(env) and os.access(env, os.X_OK):
            return env
        on_path = shutil.which("obscura")
        if on_path:
            return on_path
        for p in OBSCURA_SEARCH_PATHS:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
        return None

    @classmethod
    def resolve(cls, binary: Optional[str] = None) -> EngineConfig:
        path = cls.find_binary(binary)
        if not path:
            raise FileNotFoundError(
                "obscura binary not found. Tried: $OBSCURA_BIN, PATH, "
                + ", ".join(OBSCURA_SEARCH_PATHS)
                + ". Install per workspace/dev-knowledge/skills/browser_use.md."
            )
        return EngineConfig(name="obscura", binary=path, mode="obscura")

    @staticmethod
    def make_subprocess(cfg: EngineConfig, port: int = 0,
                        stealth: bool = False) -> BrowserSubprocess:
        return BrowserSubprocess(binary=cfg.binary, mode="obscura",
                                 port=port, stealth=stealth)

    @staticmethod
    def ws_endpoint(host: str, port: int, timeout: float = 10.0) -> str:
        """Obscura has NO /json/version endpoint — the WS path is fixed."""
        return f"ws://{host}:{port}/devtools/browser"


# --------------------------------------------------------------------------
# Chromium
# --------------------------------------------------------------------------
class ChromiumEngine:
    """Locate Playwright's bundled headless-shell chromium and run it directly.
    Avoids Playwright's own driver — we go straight to CDP.
    """
    name = "chromium"

    @staticmethod
    def find_binary(binary: Optional[str] = None) -> Optional[str]:
        if binary and os.path.isfile(binary) and os.access(binary, os.X_OK):
            return binary
        env = os.environ.get("CHROMIUM_BIN") or os.environ.get("CHROME_BIN")
        if env and os.path.isfile(env) and os.access(env, os.X_OK):
            return env
        # Real chrome/chromium on PATH (rare in sandboxes)
        for cand in ("chromium", "chrome", "google-chrome", "chrome-headless-shell"):
            p = shutil.which(cand)
            if p:
                return p
        # Playwright cache layout: ~/.cache/ms-playwright/chromium*-<rev>/...
        cache_roots = [
            os.path.expanduser("~/.cache/ms-playwright"),
            "/agent/data/.home/.cache/ms-playwright",
        ]
        for root in cache_roots:
            if not os.path.isdir(root):
                continue
            for entry in sorted(os.listdir(root), reverse=True):
                if not entry.startswith("chromium"):
                    continue
                # Try multiple folder names Playwright has used.
                for sub, exe in (
                    ("chrome-headless-shell-linux64", "chrome-headless-shell"),
                    ("chrome-linux", "chrome"),
                ):
                    cand = os.path.join(root, entry, sub, exe)
                    if os.path.isfile(cand) and os.access(cand, os.X_OK):
                        return cand
        return None

    @classmethod
    def resolve(cls, binary: Optional[str] = None) -> EngineConfig:
        path = cls.find_binary(binary)
        if not path:
            raise FileNotFoundError(
                "chromium binary not found. Set $CHROMIUM_BIN, install chromium, "
                "or run `pip install playwright && python3 -m playwright install chromium`."
            )
        return EngineConfig(name="chromium", binary=path, mode="chromium")

    @staticmethod
    def make_subprocess(cfg: EngineConfig, port: int = 0,
                        stealth: bool = False) -> BrowserSubprocess:
        return BrowserSubprocess(binary=cfg.binary, mode="chromium", port=port)

    @staticmethod
    def ws_endpoint(host: str, port: int, timeout: float = 10.0) -> str:
        """Chromium serves /json/version with the real webSocketDebuggerUrl.

        Polls until the endpoint is up (Chromium needs ~200-500 ms after
        bind to be ready to serve HTTP).
        """
        url = f"http://{host}:{port}/json/version"
        deadline = time.monotonic() + timeout
        last_err: Optional[Exception] = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode())
                ws = data.get("webSocketDebuggerUrl")
                if ws:
                    return ws
                last_err = RuntimeError(f"missing webSocketDebuggerUrl in {data!r}")
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                last_err = e
            time.sleep(0.2)
        raise TimeoutError(
            f"chromium /json/version not ready at {url} within {timeout}s: {last_err!r}"
        )


# --------------------------------------------------------------------------
# Registry + auto-fallback
# --------------------------------------------------------------------------
ENGINES = {"obscura": ObscuraEngine, "chromium": ChromiumEngine}


class _AutoEngine:
    """Pseudo-engine that picks the first available real engine.

    Order: obscura (lighter, faster) → chromium (heavier, max compat).
    Resolves by trying each engine's `find_binary`; first hit wins.
    """
    name = "auto"

    @staticmethod
    def resolve(binary: Optional[str] = None) -> EngineConfig:
        for engine_cls in (ObscuraEngine, ChromiumEngine):
            if engine_cls.find_binary() is not None:
                return engine_cls.resolve(binary)
        raise FileNotFoundError(
            "No browser engine found. Install obscura or chromium. "
            "See workspace/dev-knowledge/skills/browser_use.md."
        )

    @staticmethod
    def make_subprocess(cfg: EngineConfig, port: int = 0,
                        stealth: bool = False) -> BrowserSubprocess:
        return ENGINES[cfg.name].make_subprocess(cfg, port=port, stealth=stealth)

    @staticmethod
    def ws_endpoint(host: str, port: int, timeout: float = 10.0) -> str:
        # _AutoEngine is only used for resolve(); after that, BrowserPool
        # uses the concrete engine via ENGINES[cfg.name].
        raise NotImplementedError("_AutoEngine.ws_endpoint should never be called directly")


def get_engine(name: str):
    if name == "auto":
        return _AutoEngine
    if name not in ENGINES:
        raise ValueError(f"unknown engine '{name}'. Choose from {['auto'] + list(ENGINES)}")
    return ENGINES[name]
