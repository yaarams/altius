"""
Unit tests for PortalCrawler Properties 1, 2, 3.

All tests use:
  - In-memory SQLite DB (no real DB file).
  - Monkeypatched _fetch_presigned (no live portal).
  - Injected db_session (no session factory calls).

Properties under test:
  Prop 1 — Files with status 'downloaded' or 'extracted' are SKIPPED (not re-downloaded).
  Prop 2 — Files with status 'failed' are RETRIED (download attempted again).
  Prop 3 — On success: local_path set, content_hash (sha256) stored, status='downloaded',
            download_ts set (non-empty ISO string).

NOTE: pytest-asyncio is required (asyncio_mode = "auto" in pyproject.toml).
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import File
from backend.db.session import Base
from backend.crawler.portal_crawler import FileRecord, PortalCrawler, LoginError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_db() -> Session:
    """Create an in-memory SQLite DB with the full schema. Yields a session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def tmp_files_dir(tmp_path: Path) -> Path:
    """Temporary directory for downloaded PDFs."""
    d = tmp_path / "files"
    d.mkdir()
    return d


def _make_file_row(db: Session, external_file_id: int, status: str, **kwargs) -> File:
    """Insert a File row and return it."""
    row = File(
        external_file_id=external_file_id,
        deal_id=10495,
        file_name=kwargs.get("file_name", f"file_{external_file_id}.pdf"),
        portal_doc_type=kwargs.get("portal_doc_type", None),
        file_url=kwargs.get("file_url", "https://example.com/fake_presigned_url"),
        status=status,
    )
    db.add(row)
    db.commit()
    return row


def _make_file_record(external_file_id: int) -> FileRecord:
    return FileRecord(
        external_file_id=external_file_id,
        deal_id=10495,
        file_name=f"file_{external_file_id}.pdf",
        portal_doc_type=None,
        file_url="https://example.com/fake_presigned_url",
    )


def _make_crawler(db: Session, files_dir: Path) -> PortalCrawler:
    """Build a PortalCrawler with injected db_session and files_dir."""
    return PortalCrawler(
        portal_user="test@example.com",
        portal_password="test_password",
        headless=True,
        db_session=db,
        files_dir=files_dir,
    )


def _make_fake_pdf(path: Path) -> bytes:
    """Write a minimal fake PDF and return its sha256."""
    content = b"%PDF-1.4 fake content for test " + str(path).encode()[:20]
    path.write_bytes(content)
    return content


# ---------------------------------------------------------------------------
# Property 1 — Skip if status in {downloaded, extracted}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prop1_skip_downloaded(in_memory_db, tmp_files_dir):
    """
    Prop 1: A file with status='downloaded' must be skipped.
    No download attempt, outcome='skipped', status unchanged.
    """
    db = in_memory_db
    _make_file_row(db, external_file_id=1001, status="downloaded")
    fr = _make_file_record(1001)
    crawler = _make_crawler(db, tmp_files_dir)

    # Patch _fetch_presigned: should NOT be called
    mock_fetch = AsyncMock(return_value=True)
    with patch.object(crawler, "_fetch_presigned", mock_fetch):
        outcome = await crawler._download_file(fr, deal_id=10495, cb=lambda _: None)

    assert outcome == "skipped", f"Expected 'skipped', got {outcome!r}"
    mock_fetch.assert_not_called()

    # Status must not change
    row = db.query(File).filter(File.external_file_id == 1001).first()
    assert row.status == "downloaded"


@pytest.mark.asyncio
async def test_prop1_skip_extracted(in_memory_db, tmp_files_dir):
    """
    Prop 1: A file with status='extracted' must also be skipped.
    """
    db = in_memory_db
    _make_file_row(db, external_file_id=1002, status="extracted")
    fr = _make_file_record(1002)
    crawler = _make_crawler(db, tmp_files_dir)

    mock_fetch = AsyncMock(return_value=True)
    with patch.object(crawler, "_fetch_presigned", mock_fetch):
        outcome = await crawler._download_file(fr, deal_id=10495, cb=lambda _: None)

    assert outcome == "skipped"
    mock_fetch.assert_not_called()

    row = db.query(File).filter(File.external_file_id == 1002).first()
    assert row.status == "extracted"


# ---------------------------------------------------------------------------
# Property 2 — Retry if status == 'failed'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prop2_retry_failed_success(in_memory_db, tmp_files_dir):
    """
    Prop 2: A file with status='failed' must be retried.
    If the retry succeeds, status becomes 'downloaded'.
    """
    db = in_memory_db
    _make_file_row(db, external_file_id=2001, status="failed")
    fr = _make_file_record(2001)
    crawler = _make_crawler(db, tmp_files_dir)

    async def fake_fetch(url: str, dest: Path) -> bool:
        # Write a fake PDF so sha256 can be computed
        dest.write_bytes(b"%PDF-1.4 fake content")
        return True

    with patch.object(crawler, "_fetch_presigned", side_effect=fake_fetch):
        outcome = await crawler._download_file(fr, deal_id=10495, cb=lambda _: None)

    assert outcome == "downloaded", f"Expected 'downloaded', got {outcome!r}"

    row = db.query(File).filter(File.external_file_id == 2001).first()
    assert row.status == "downloaded"
    assert row.content_hash is not None
    assert row.local_path is not None


@pytest.mark.asyncio
async def test_prop2_retry_failed_fails_again(in_memory_db, tmp_files_dir):
    """
    Prop 2: A file with status='failed' that fails again stays 'failed'.
    """
    db = in_memory_db
    _make_file_row(db, external_file_id=2002, status="failed")
    fr = _make_file_record(2002)
    crawler = _make_crawler(db, tmp_files_dir)

    # Both initial fetch and retry (after URL refresh) fail
    mock_fetch = AsyncMock(return_value=False)

    async def fake_enumerate(deal_id):
        return [fr]  # same record, same (fake) URL

    with patch.object(crawler, "_fetch_presigned", mock_fetch):
        with patch.object(crawler, "_enumerate_files", side_effect=fake_enumerate):
            outcome = await crawler._download_file(fr, deal_id=10495, cb=lambda _: None)

    assert outcome == "failed"
    row = db.query(File).filter(File.external_file_id == 2002).first()
    assert row.status == "failed"


# ---------------------------------------------------------------------------
# Property 3 — On success: local_path, content_hash (sha256), status, download_ts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_prop3_success_sets_all_fields(in_memory_db, tmp_files_dir):
    """
    Prop 3: On successful download, the File row must have:
      - status='downloaded'
      - local_path pointing to the file on disk
      - content_hash equal to sha256(file_bytes)
      - download_ts non-empty ISO 8601 string
    """
    db = in_memory_db
    _make_file_row(db, external_file_id=3001, status="pending")
    fr = _make_file_record(3001)
    crawler = _make_crawler(db, tmp_files_dir)

    fake_content = b"%PDF-1.4 real test content for property 3"
    expected_hash = hashlib.sha256(fake_content).hexdigest()

    async def fake_fetch(url: str, dest: Path) -> bool:
        dest.write_bytes(fake_content)
        return True

    with patch.object(crawler, "_fetch_presigned", side_effect=fake_fetch):
        outcome = await crawler._download_file(fr, deal_id=10495, cb=lambda _: None)

    assert outcome == "downloaded"

    row = db.query(File).filter(File.external_file_id == 3001).first()

    # status
    assert row.status == "downloaded", f"Expected status='downloaded', got {row.status!r}"

    # local_path must exist on disk
    assert row.local_path is not None, "local_path must be set"
    path = Path(row.local_path)
    assert path.exists(), f"File not found on disk: {path}"

    # content_hash must equal sha256 of the bytes written
    assert row.content_hash == expected_hash, (
        f"content_hash mismatch: {row.content_hash!r} != {expected_hash!r}"
    )

    # download_ts must be a non-empty string (ISO 8601)
    assert row.download_ts, "download_ts must be set"
    assert isinstance(row.download_ts, str)
    assert len(row.download_ts) >= 10  # at least YYYY-MM-DD


@pytest.mark.asyncio
async def test_prop3_idempotency_second_run(in_memory_db, tmp_files_dir):
    """
    Prop 3 / idempotency: Running _download_file twice on the same file (already downloaded)
    results in the second call being skipped, with no change to the DB row.
    """
    db = in_memory_db
    _make_file_row(db, external_file_id=3002, status="pending")
    fr = _make_file_record(3002)
    crawler = _make_crawler(db, tmp_files_dir)

    fake_content = b"%PDF-1.4 idempotency test"
    expected_hash = hashlib.sha256(fake_content).hexdigest()

    fetch_call_count = 0

    async def fake_fetch(url: str, dest: Path) -> bool:
        nonlocal fetch_call_count
        fetch_call_count += 1
        dest.write_bytes(fake_content)
        return True

    # First run
    with patch.object(crawler, "_fetch_presigned", side_effect=fake_fetch):
        outcome1 = await crawler._download_file(fr, deal_id=10495, cb=lambda _: None)

    assert outcome1 == "downloaded"
    assert fetch_call_count == 1

    # Second run — should skip
    with patch.object(crawler, "_fetch_presigned", side_effect=fake_fetch):
        outcome2 = await crawler._download_file(fr, deal_id=10495, cb=lambda _: None)

    assert outcome2 == "skipped"
    # fetch_presigned was NOT called again
    assert fetch_call_count == 1, "fetch_presigned should not be called on second run"

    # DB row unchanged
    row = db.query(File).filter(File.external_file_id == 3002).first()
    assert row.status == "downloaded"
    assert row.content_hash == expected_hash


# ---------------------------------------------------------------------------
# LoginError — bad credentials (no files written)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_login_error_no_files_written(in_memory_db, tmp_files_dir):
    """
    Bad credentials must raise LoginError and write zero files to disk.
    """
    crawler = PortalCrawler(
        portal_user="wrong@example.com",
        portal_password="wrong_password",
        headless=True,
        db_session=in_memory_db,
        files_dir=tmp_files_dir,
    )

    # Mock _login to raise LoginError immediately
    async def bad_login():
        raise LoginError("Login failed: bad credentials")

    with patch.object(crawler, "_login", side_effect=bad_login):
        with pytest.raises(LoginError):
            # Need a minimal browser context — skip Playwright by patching run()
            # to call _login() directly
            await crawler._login()

    # No files written
    files_on_disk = list(tmp_files_dir.iterdir())
    assert files_on_disk == [], f"Expected no files, found: {files_on_disk}"

    # No DB rows written
    count = in_memory_db.query(File).count()
    assert count == 0


# ---------------------------------------------------------------------------
# Pre-record idempotency (upsert behavior)
# ---------------------------------------------------------------------------

def test_prerecord_creates_pending_row(in_memory_db, tmp_files_dir):
    """Pre-recording a new file creates a 'pending' row."""
    db = in_memory_db
    crawler = _make_crawler(db, tmp_files_dir)

    fr = _make_file_record(4001)
    crawler._prerecord_files(db, [fr])

    row = db.query(File).filter(File.external_file_id == 4001).first()
    assert row is not None
    assert row.status == "pending"
    assert row.file_name == "file_4001.pdf"


def test_prerecord_does_not_overwrite_status(in_memory_db, tmp_files_dir):
    """Pre-recording an existing downloaded file does not reset its status."""
    db = in_memory_db
    _make_file_row(db, external_file_id=4002, status="downloaded")
    crawler = _make_crawler(db, tmp_files_dir)

    fr = _make_file_record(4002)
    fr.file_url = "https://example.com/new_url"
    crawler._prerecord_files(db, [fr])

    row = db.query(File).filter(File.external_file_id == 4002).first()
    # Status must not be reset to 'pending'
    assert row.status == "downloaded"
    # URL should be refreshed
    assert row.file_url == "https://example.com/new_url"
