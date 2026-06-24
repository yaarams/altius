"""browser_use — a CDP-based headless browser skill for xpander.ai agents.

Public API:
    BrowserPool   — spawn/manage a long-lived browser subprocess (obscura/chromium)
    Page          — a per-task tab session driven over CDP
    BrowserEvent  — dataclass for events emitted on the local event bus

See workspace/dev-knowledge/skills/browser_use.md for the full skill doc.
"""
from .pool import BrowserPool, Page  # noqa: F401
from .events import BrowserEvent, EventBus  # noqa: F401
from .daemon import BrowserDaemon, DaemonState  # noqa: F401

__all__ = ["BrowserPool", "Page", "BrowserEvent", "EventBus",
           "BrowserDaemon", "DaemonState"]
