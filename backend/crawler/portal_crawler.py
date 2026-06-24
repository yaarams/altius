"""
Portal Crawler — T1.3, T1.4, T1.5

Playwright chromium login + APIRequestContext enumeration + idempotent presigned download.

Usage:
    python -m backend.crawler.portal_crawler   # full sync, headless
    HEADLESS=0 python -m backend.crawler.portal_crawler   # watch the browser

Exposes async functions for T1.6 (orchestrator/SSE):
    - run(progress_callback) -> CrawlResult
    - PortalCrawler (class)

ADR-002: Playwright login + context.request for the JSON API (cookie auto-shared).
ADR-007: Idempotency key = external_file_id (stable integer). file_url NOT a key.
ADR-011: POST /api/v0.0.2/deals-list -> deal ids; GET /api/v0.0.3/deals/{id}/files -> files.

SECURITY: credentials are never logged or printed.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
from playwright.async_api import (
    APIRequestContext,
    BrowserContext,
    Page,
    async_playwright,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import File
from backend.db.session import get_session_factory

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FILES_DIR = Path(__file__).parent.parent.parent / "data" / "files"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LoginError(Exception):
    """Raised when login fails (bad credentials, unexpected redirect, etc.)."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FileRecord:
    """Lightweight struct mirroring the portal JSON API file shape."""
    external_file_id: int
    deal_id: int
    file_name: str
    portal_doc_type: str | None
    file_url: str
    size_in_bytes: int | None = None
    doc_type_raw: dict | None = None


@dataclass
class CrawlResult:
    deals: list[int] = field(default_factory=list)
    enumerated: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0

    def __str__(self) -> str:
        return (
            f"deals={len(self.deals)} enumerated={self.enumerated} "
            f"downloaded={self.downloaded} skipped={self.skipped} failed={self.failed}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    """Convert a file name to a filesystem-safe slug (keep extension)."""
    stem = Path(name).stem
    suffix = Path(name).suffix or ".pdf"
    safe = re.sub(r"[^\w\-.]", "_", stem)[:80]
    return safe + suffix


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# PortalCrawler
# ---------------------------------------------------------------------------

class PortalCrawler:
    """
    Async crawler for fo1.altius.finance.

    Life cycle: _login -> _enumerate_deals -> per-deal _enumerate_files + _download_file.

    Args:
        portal_user:    Override PORTAL_USER (for testing with bad creds).
        portal_password: Override PORTAL_PASSWORD (for testing with bad creds).
        headless:       Whether to run Chromium in headless mode.
        db_session:     Inject a custom Session (for unit tests; else a real one is created).
        files_dir:      Directory to save downloaded PDFs.
        http_client:    Inject an httpx.AsyncClient (for unit tests).
    """

    def __init__(
        self,
        portal_user: str | None = None,
        portal_password: str | None = None,
        headless: bool | None = None,
        db_session: Session | None = None,
        files_dir: Path = FILES_DIR,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        # Credentials: accept override (test injection) or fall back to settings.
        # NEVER log credential values.
        self._user: str = portal_user if portal_user is not None else settings.PORTAL_USER
        self._password: str = (
            portal_password if portal_password is not None else settings.PORTAL_PASSWORD
        )
        # Headless: accept override or fall back to settings
        self._headless = headless if headless is not None else settings.PORTAL_HEADLESS
        self._external_db_session = db_session
        self._files_dir = files_dir
        self._external_http_client = http_client

        # Portal URLs and configuration from settings
        self._portal_base_url = settings.PORTAL_BASE_URL
        self._portal_api_base_url = settings.PORTAL_API_BASE_URL
        self._portal_login_path = settings.PORTAL_LOGIN_PATH
        self._max_login_retries = settings.PORTAL_MAX_LOGIN_RETRIES

        self._files_dir.mkdir(parents=True, exist_ok=True)

        # Set during run()
        self._page: Page | None = None
        self._context: BrowserContext | None = None
        self._login_attempts = 0

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> CrawlResult:
        """
        Full sync: login → enumerate deals → enumerate + pre-record files → download.

        Args:
            progress_callback: Optional callable receiving event dicts like
                {"stage": "Crawling", "event": "file_downloaded", "file_name": "..."}

        Returns:
            CrawlResult with counts.
        """
        result = CrawlResult()
        cb = progress_callback or (lambda _: None)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            self._context = await browser.new_context()
            self._page = await self._context.new_page()

            try:
                # T1.3 — Login
                cb({"stage": "Crawling", "event": "login_start"})
                await self._login()
                cb({"stage": "Crawling", "event": "login_ok"})

                # T1.4 — Enumerate deals
                deal_ids = await self._enumerate_deals()
                result.deals = deal_ids
                cb({"stage": "Crawling", "event": "deals_found", "count": len(deal_ids)})

                # Per deal: enumerate files → pre-record → download
                for deal_id in deal_ids:
                    cb({"stage": "Crawling", "event": "deal_start", "deal_id": deal_id})

                    # Check mid-crawl session expiry
                    if await self._is_session_expired():
                        await self._relogin()

                    try:
                        file_records = await self._enumerate_files(deal_id)
                    except Exception as exc:
                        logger.warning("Deal %s enumeration failed: %s", deal_id, exc)
                        cb({"stage": "Crawling", "event": "deal_error", "deal_id": deal_id, "error": str(exc)})
                        continue

                    result.enumerated += len(file_records)

                    # Pre-record into DB before downloading (R2.3)
                    db = self._get_session()
                    try:
                        self._prerecord_files(db, file_records)
                    finally:
                        if self._external_db_session is None:
                            db.close()

                    # Download each file
                    for fr in file_records:
                        try:
                            outcome = await self._download_file(fr, deal_id, cb)
                            if outcome == "skipped":
                                result.skipped += 1
                            elif outcome == "downloaded":
                                result.downloaded += 1
                                cb({
                                    "stage": "Crawling",
                                    "event": "file_downloaded",
                                    "file_name": fr.file_name,
                                    "external_file_id": fr.external_file_id,
                                })
                            elif outcome == "failed":
                                result.failed += 1
                        except Exception as exc:
                            logger.error(
                                "Unexpected error downloading file %s: %s",
                                fr.external_file_id, exc,
                            )
                            result.failed += 1
                            self._mark_failed(fr.external_file_id, str(exc))

            finally:
                await browser.close()

        return result

    # ------------------------------------------------------------------
    # T1.3 — Login
    # ------------------------------------------------------------------

    async def _login(self) -> None:
        """
        Navigate to /login, fill credentials, submit, assert redirect.

        Raises LoginError on bad credentials or unexpected state.
        NEVER logs credential values.
        """
        assert self._page is not None

        self._login_attempts += 1
        logger.info("Navigating to login page (attempt %d)", self._login_attempts)

        login_url = f"{self._portal_base_url}{self._portal_login_path}"
        await self._page.goto(login_url, wait_until="networkidle")

        # Fill Email textbox
        email_input = self._page.get_by_label("Email", exact=False)
        if not await email_input.count():
            email_input = self._page.locator('input[type="email"], input[name="email"], input[placeholder*="mail" i]').first
        await email_input.fill(self._user)

        # Fill Password textbox
        pw_input = self._page.get_by_label("Password", exact=False)
        if not await pw_input.count():
            pw_input = self._page.locator('input[type="password"]').first
        await pw_input.fill(self._password)

        # Click Login button — use exact "Login" to avoid matching "Easy Login" / "SSO Login"
        login_btn = self._page.get_by_role("button", name="Login", exact=True)
        if not await login_btn.count():
            login_btn = self._page.locator('button[type="submit"]').first
        await login_btn.click()

        # Wait for navigation away from /login
        try:
            await self._page.wait_for_url(
                lambda url: "/login" not in url,
                timeout=15_000,
            )
        except Exception:
            current_url = self._page.url
            # Never include credential values in the error message
            raise LoginError(
                f"Login failed: still at {current_url!r}. "
                "Check PORTAL_USER and PORTAL_PASSWORD in .env."
            )

        current_url = self._page.url
        if "/login" in current_url:
            raise LoginError(
                f"Login failed: redirected back to login page ({current_url!r}). "
                "Credentials may be incorrect."
            )

        logger.info("Login successful — landed at: %s", current_url)
        self._login_attempts = 0  # reset counter on success

    async def _is_session_expired(self) -> bool:
        """Check if the current page has been redirected back to /login."""
        if self._page is None:
            return False
        return "/login" in self._page.url

    async def _relogin(self) -> None:
        """Re-login up to max retries (R1.3)."""
        if self._login_attempts >= self._max_login_retries:
            raise LoginError(
                f"Session expired and re-login failed after {self._max_login_retries} attempts."
            )
        logger.warning(
            "Session expired (redirected to /login). Re-logging in (attempt %d/%d)...",
            self._login_attempts + 1,
            self._max_login_retries,
        )
        await self._login()

    # ------------------------------------------------------------------
    # T1.4 — Enumerate deals via JSON API
    # ------------------------------------------------------------------

    async def _enumerate_deals(self) -> list[int]:
        """
        POST /api/v0.0.2/deals-list to get deal ids.

        Falls back to DOM scraping of /main/my-deals if the API fails.
        """
        assert self._page is not None

        # Primary: JSON API
        try:
            deals_list_url = f"{self._portal_api_base_url}/api/v0.0.2/deals-list"
            response = await self._page.request.post(
                deals_list_url,
                data="{}",
                headers={"Content-Type": "application/json"},
                timeout=30_000,
            )
            if response.ok:
                body = await response.json()
                deal_ids = self._parse_deals_response(body)
                if deal_ids:
                    logger.info("Deals API returned %d deals: %s", len(deal_ids), deal_ids)
                    return deal_ids
                logger.warning("Deals API returned empty list; trying DOM fallback.")
            else:
                logger.warning(
                    "Deals API returned HTTP %d; trying DOM fallback.",
                    response.status,
                )
        except Exception as exc:
            logger.warning("Deals API call failed (%s); trying DOM fallback.", exc)

        # Fallback: parse /main/my-deals for deal links
        return await self._enumerate_deals_from_dom()

    def _parse_deals_response(self, body: Any) -> list[int]:
        """Extract deal ids from various known response shapes."""
        deal_ids: list[int] = []

        if isinstance(body, dict):
            # Shape: {"data": [{id: ...}, ...]} or {"data": {"deals": [...]}}
            data = body.get("data") or body.get("deals") or body.get("results") or []

            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        for key in ("id", "deal_id", "dealId"):
                            if key in item:
                                try:
                                    deal_ids.append(int(item[key]))
                                except (TypeError, ValueError):
                                    pass
                                break
            elif isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, dict):
                        for id_key in ("id", "deal_id"):
                            if id_key in val:
                                try:
                                    deal_ids.append(int(val[id_key]))
                                except (TypeError, ValueError):
                                    pass
                                break

        elif isinstance(body, list):
            for item in body:
                if isinstance(item, dict):
                    for key in ("id", "deal_id"):
                        if key in item:
                            try:
                                deal_ids.append(int(item[key]))
                            except (TypeError, ValueError):
                                pass
                            break

        return list(dict.fromkeys(deal_ids))  # deduplicate, preserve order

    async def _enumerate_deals_from_dom(self) -> list[int]:
        """Fallback: navigate to /main/my-deals and scrape deal links."""
        assert self._page is not None

        logger.info("DOM fallback: navigating to /main/my-deals")
        await self._page.goto(f"{self._portal_base_url}/main/my-deals", wait_until="networkidle")

        # Find links matching /main/deal/{id}
        hrefs = await self._page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.getAttribute('href'))",
        )
        deal_ids: list[int] = []
        for href in hrefs:
            m = re.search(r"/main/deal/(\d+)", href or "")
            if m:
                did = int(m.group(1))
                if did not in deal_ids:
                    deal_ids.append(did)

        logger.info("DOM fallback found %d deals: %s", len(deal_ids), deal_ids)
        return deal_ids

    # ------------------------------------------------------------------
    # T1.4 — Enumerate files per deal + pre-record (R2.3)
    # ------------------------------------------------------------------

    async def _enumerate_files(self, deal_id: int) -> list[FileRecord]:
        """
        GET /api/v0.0.3/deals/{deal_id}/files and return FileRecord list.

        Raises on non-OK response (caller should log + skip).
        """
        assert self._page is not None

        url = f"{self._portal_api_base_url}/api/v0.0.3/deals/{deal_id}/files"
        response = await self._page.request.get(url, timeout=30_000)

        if not response.ok:
            raise RuntimeError(
                f"Files API for deal {deal_id} returned HTTP {response.status}"
            )

        body = await response.json()
        data = body.get("data", {})

        records: list[FileRecord] = []
        for _file_id_str, fdata in data.items():
            try:
                ext_id = int(fdata["id"])
                name = fdata.get("name") or f"file_{ext_id}.pdf"
                file_url = fdata.get("file_url", "")
                doc_type = fdata.get("document_type")  # portal label (eval only)
                size = fdata.get("size_in_bytes")

                records.append(FileRecord(
                    external_file_id=ext_id,
                    deal_id=deal_id,
                    file_name=name,
                    portal_doc_type=doc_type,
                    file_url=file_url,
                    size_in_bytes=size,
                ))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed file entry in deal %s: %s", deal_id, exc)

        logger.info("Deal %s: enumerated %d files", deal_id, len(records))
        return records

    def _prerecord_files(self, db: Session, records: list[FileRecord]) -> None:
        """
        UPSERT File rows keyed on external_file_id BEFORE downloading (R2.3).

        New files → status='pending'. Existing files → update file_url only
        (url rotates; don't overwrite status/hash).
        """
        for fr in records:
            existing = (
                db.query(File)
                .filter(File.external_file_id == fr.external_file_id)
                .first()
            )
            if existing is None:
                row = File(
                    external_file_id=fr.external_file_id,
                    deal_id=fr.deal_id,
                    file_name=fr.file_name,
                    portal_doc_type=fr.portal_doc_type,
                    file_url=fr.file_url,
                    status="pending",
                )
                db.add(row)
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    logger.debug(
                        "Race condition on external_file_id=%s — already inserted",
                        fr.external_file_id,
                    )
            else:
                # Refresh the rotating URL; leave status/hash untouched
                existing.file_url = fr.file_url
                db.commit()
                logger.debug(
                    "Pre-record: existing file %s (%s) — refreshed url",
                    fr.external_file_id, fr.file_name,
                )

    # ------------------------------------------------------------------
    # T1.5 — Idempotent presigned download
    # ------------------------------------------------------------------

    async def _download_file(
        self,
        fr: FileRecord,
        deal_id: int,
        cb: Callable[[dict], None],
    ) -> str:
        """
        Download a single file idempotently.

        Returns: 'skipped' | 'downloaded' | 'failed'

        Properties enforced:
          Prop 1 — skip if status in {downloaded, extracted}
          Prop 2 — retry if status == 'failed'
          Prop 3 — on success: local_path + content_hash + download_ts + status='downloaded'
        """
        db = self._get_session()
        try:
            row = (
                db.query(File)
                .filter(File.external_file_id == fr.external_file_id)
                .first()
            )
            if row is None:
                logger.warning(
                    "File %s not pre-recorded — skipping.", fr.external_file_id
                )
                return "failed"

            # Prop 1 — skip already downloaded/extracted
            if row.status in ("downloaded", "extracted"):
                logger.debug(
                    "Skipping file %s (%s) — status=%s",
                    fr.external_file_id, fr.file_name, row.status,
                )
                cb({"stage": "Crawling", "event": "file_skipped", "file_name": fr.file_name})
                return "skipped"

            # Prop 2 — retry failed files (fall through to download)
            if row.status == "failed":
                logger.info(
                    "Retrying previously-failed file %s (%s)",
                    fr.external_file_id, fr.file_name,
                )

            # Attempt download
            url_to_use = row.file_url or fr.file_url  # use DB url (refreshed on pre-record)
            dest = self._files_dir / f"{fr.external_file_id}_{_safe_name(fr.file_name)}"

            success = await self._fetch_presigned(url_to_use, dest)

            if not success:
                # 403 / expiry — re-fetch files list for a fresh URL, retry once
                logger.info(
                    "Download 403/error for file %s — refreshing URL and retrying.",
                    fr.external_file_id,
                )
                try:
                    fresh_records = await self._enumerate_files(deal_id)
                    fresh_map = {r.external_file_id: r for r in fresh_records}
                    if fr.external_file_id in fresh_map:
                        fresh_url = fresh_map[fr.external_file_id].file_url
                        # Update DB url
                        row.file_url = fresh_url
                        db.commit()
                        success = await self._fetch_presigned(fresh_url, dest)
                except Exception as refresh_exc:
                    logger.warning("URL refresh failed for file %s: %s", fr.external_file_id, refresh_exc)

            if success:
                content_hash = _sha256(dest)
                row.local_path = str(dest)
                row.content_hash = content_hash
                row.status = "downloaded"
                row.download_ts = _utcnow_iso()
                db.commit()
                logger.info(
                    "Downloaded file %s -> %s (sha256=%s...)",
                    fr.external_file_id, dest.name, content_hash[:12],
                )
                return "downloaded"
            else:
                row.status = "failed"
                db.commit()
                logger.error("Failed to download file %s (%s)", fr.external_file_id, fr.file_name)
                return "failed"

        except Exception as exc:
            try:
                row = (
                    db.query(File)
                    .filter(File.external_file_id == fr.external_file_id)
                    .first()
                )
                if row:
                    row.status = "failed"
                    db.commit()
            except Exception:
                db.rollback()
            logger.error(
                "Exception downloading file %s: %s", fr.external_file_id, exc, exc_info=True
            )
            return "failed"
        finally:
            if self._external_db_session is None:
                db.close()

    async def _fetch_presigned(self, url: str, dest: Path) -> bool:
        """
        GET a presigned S3 URL and stream to dest.

        Returns True on success (2xx), False on failure (4xx/5xx/network error).
        """
        try:
            if self._external_http_client is not None:
                client = self._external_http_client
                async with client.stream("GET", url, follow_redirects=True) as response:
                    if response.status_code == 403:
                        return False
                    if not (200 <= response.status_code < 300):
                        logger.warning("Presigned GET returned HTTP %d", response.status_code)
                        return False
                    with open(dest, "wb") as f:
                        async for chunk in response.aiter_bytes(1 << 16):
                            f.write(chunk)
            else:
                async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
                    async with client.stream("GET", url) as response:
                        if response.status_code == 403:
                            return False
                        if not (200 <= response.status_code < 300):
                            logger.warning("Presigned GET returned HTTP %d", response.status_code)
                            return False
                        with open(dest, "wb") as f:
                            async for chunk in response.aiter_bytes(1 << 16):
                                f.write(chunk)
            return True
        except Exception as exc:
            logger.error("HTTP error fetching presigned URL: %s", exc)
            if dest.exists():
                dest.unlink(missing_ok=True)
            return False

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _get_session(self) -> Session:
        """Return the injected session or create a new one from the factory."""
        if self._external_db_session is not None:
            return self._external_db_session
        factory = get_session_factory()
        return factory()

    def _mark_failed(self, external_file_id: int, reason: str) -> None:
        """Update file status to 'failed' by external_file_id."""
        db = self._get_session()
        try:
            row = db.query(File).filter(File.external_file_id == external_file_id).first()
            if row:
                row.status = "failed"
                db.commit()
        except Exception as exc:
            logger.error("Could not mark file %s as failed: %s", external_file_id, exc)
            db.rollback()
        finally:
            if self._external_db_session is None:
                db.close()


# ---------------------------------------------------------------------------
# Convenience async entry point (for T1.6 and tests)
# ---------------------------------------------------------------------------

async def run(
    progress_callback: Callable[[dict], None] | None = None,
    portal_user: str | None = None,
    portal_password: str | None = None,
    headless: bool = True,
) -> CrawlResult:
    """
    Top-level async function for T1.6 orchestrator to call.

    Args:
        progress_callback: Receives event dicts:
            {"stage": "Crawling", "event": "file_downloaded", "file_name": ..., ...}
        portal_user: Override PORTAL_USER (for testing bad creds).
        portal_password: Override PORTAL_PASSWORD (for testing bad creds).
        headless: Whether to run Chromium headless.
    """
    crawler = PortalCrawler(
        portal_user=portal_user,
        portal_password=portal_password,
        headless=headless,
    )
    return await crawler.run(progress_callback=progress_callback)


# ---------------------------------------------------------------------------
# Module CLI: python -m backend.crawler.portal_crawler
# ---------------------------------------------------------------------------

async def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    headless = os.environ.get("HEADLESS", "1") != "0"
    events: list[dict] = []

    def cb(event: dict) -> None:
        events.append(event)
        stage = event.get("stage", "")
        evt = event.get("event", "")
        if evt == "file_downloaded":
            print(f"  [+] Downloaded: {event.get('file_name', '')}")
        elif evt == "file_skipped":
            print(f"  [-] Skipped:    {event.get('file_name', '')}")
        elif evt in ("login_ok", "deals_found", "deal_start"):
            print(f"  [*] {stage} / {evt}: {event}")

    print(f"Starting portal crawl (headless={headless}) ...")
    result = await run(progress_callback=cb, headless=headless)

    print()
    print("=" * 60)
    print("Crawl complete:")
    print(f"  Deals:      {len(result.deals)} ({result.deals})")
    print(f"  Enumerated: {result.enumerated}")
    print(f"  Downloaded: {result.downloaded}")
    print(f"  Skipped:    {result.skipped}")
    print(f"  Failed:     {result.failed}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(_main())
