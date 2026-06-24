#!/usr/bin/env python3
"""Smoke test — spawn obscura, navigate xpander.ai, print structured info.

Usage:
    python3 -m browser_use.smoke [obscura|chromium] [URL]
"""
import asyncio, json, sys

from . import BrowserPool, BrowserEvent, EventBus  # type: ignore

DEFAULT_URL = "https://xpander.ai/"
EXTRACT_JS = """({
  title:    document.title,
  h1:       Array.from(document.querySelectorAll('h1,h2')).slice(0,5).map(e => e.innerText.trim()).filter(Boolean),
  navLinks: Array.from(document.querySelectorAll('nav a, header a')).slice(0,8).map(a => ({t: a.innerText.trim(), h: a.href})).filter(x => x.t),
  url:      location.href,
  bodyLen:  (document.body && document.body.innerHTML.length) || 0,
})"""

async def main(engine: str, url: str) -> int:
    bus = EventBus()
    events_seen = []

    async def tap(evt: BrowserEvent) -> None:
        events_seen.append({"type": evt.type, "page_id": evt.page_id})

    bus._external_publisher = tap  # type: ignore[attr-defined]

    async with BrowserPool(engine=engine, bus=bus) as pool:
        page = await pool.new_page()
        await page.navigate(url, timeout=30)
        info = await page.evaluate(EXTRACT_JS)
        print(json.dumps({
            "engine": engine,
            "url": url,
            "info": info,
            "events": events_seen,
        }, indent=2, ensure_ascii=False))
        await page.close()
    return 0

if __name__ == "__main__":
    engine = sys.argv[1] if len(sys.argv) > 1 else "obscura"
    url = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_URL
    sys.exit(asyncio.run(main(engine, url)))
