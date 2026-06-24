"""
"Sync only the diff" — incremental re-sync tests.

Requirement: a second sync must fetch ONLY the delta (new / missing files),
never re-download files already present. The guarantee is enforced by:
  - files.external_file_id UNIQUE                      (dedup key, ADR-007 / Prop 13)
  - PortalCrawler._prerecord_files: existing rows only refresh the rotating URL,
    status/hash left untouched
  - PortalCrawler._download_file, Prop 1: skip if status in {downloaded, extracted}

These tests drive the real pre-record + download path over a *batch* of files
(the single-file idempotency props live in test_crawler_idempotency.py).

Scenario under test = "delete a file, then run sync again":
  Run 1: files {1,2,3} downloaded.
  Between runs: file 2 is deleted from our store, and a new file 4 appears.
  Run 2: enumeration yields {1,2,3,4} → only {2,4} are fetched; {1,3} are skipped
         and their rows are left byte-for-byte untouched.

NOTE: pytest-asyncio required (asyncio_mode = "auto" in pyproject.toml).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.db.models import File
from backend.db.session import Base
from backend.crawler.portal_crawler import FileRecord, PortalCrawler


# ---------------------------------------------------------------------------
# Fixtures (self-contained — mirror test_crawler_idempotency.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_db() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def tmp_files_dir(tmp_path: Path) -> Path:
    d = tmp_path / "files"
    d.mkdir()
    return d


def _make_record(external_file_id: int) -> FileRecord:
    return FileRecord(
        external_file_id=external_file_id,
        deal_id=10495,
        file_name=f"file_{external_file_id}.pdf",
        portal_doc_type=None,
        file_url=f"https://example.com/presigned/{external_file_id}",
    )


def _make_crawler(db: Session, files_dir: Path) -> PortalCrawler:
    return PortalCrawler(
        portal_user="test@example.com",
        portal_password="test_password",
        headless=True,
        db_session=db,
        files_dir=files_dir,
    )


def _fetcher(fetched: list[int]):
    """
    Build a fake _fetch_presigned that records which external_file_id it was
    asked to download (parsed from the dest filename "{id}_{name}") and writes
    a tiny PDF so the real sha256/local_path bookkeeping runs.
    """
    async def fake_fetch(url: str, dest: Path) -> bool:
        ext_id = int(dest.name.split("_", 1)[0])
        fetched.append(ext_id)
        dest.write_bytes(b"%PDF-1.4 content for " + str(ext_id).encode())
        return True

    return fake_fetch


async def _run_sync(crawler: PortalCrawler, db: Session, records: list[FileRecord],
                    fetched: list[int]) -> dict[int, str]:
    """
    Simulate one sync pass over `records`: pre-record (upsert) then attempt a
    download for each. Returns {external_file_id: outcome}.
    """
    crawler._prerecord_files(db, records)
    outcomes: dict[int, str] = {}
    from unittest.mock import patch
    with patch.object(crawler, "_fetch_presigned", side_effect=_fetcher(fetched)):
        for fr in records:
            outcomes[fr.external_file_id] = await crawler._download_file(
                fr, deal_id=10495, cb=lambda _: None
            )
    return outcomes


# ---------------------------------------------------------------------------
# Test: re-sync downloads only the diff (delete a file, then sync)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resync_only_downloads_diff(in_memory_db, tmp_files_dir):
    db = in_memory_db
    crawler = _make_crawler(db, tmp_files_dir)

    # --- Run 1: full sync of files {1, 2, 3} ---
    run1_records = [_make_record(1), _make_record(2), _make_record(3)]
    fetched_run1: list[int] = []
    outcomes1 = await _run_sync(crawler, db, run1_records, fetched_run1)

    assert sorted(fetched_run1) == [1, 2, 3]
    assert all(o == "downloaded" for o in outcomes1.values())

    # Snapshot the rows that must NOT be touched again (1 and 3).
    row1, row3 = (
        db.query(File).filter(File.external_file_id == eid).first() for eid in (1, 3)
    )
    keep = {
        eid: (r.download_ts, r.content_hash, r.local_path)
        for eid, r in ((1, row1), (3, row3))
    }

    # --- Between runs: file 2 is deleted from our store; a new file 4 appears. ---
    db.delete(db.query(File).filter(File.external_file_id == 2).first())
    db.commit()
    assert db.query(File).filter(File.external_file_id == 2).first() is None

    # --- Run 2: enumeration now yields {1, 2, 3, 4} (2 resurfaces, 4 is new) ---
    run2_records = [_make_record(1), _make_record(2), _make_record(3), _make_record(4)]
    fetched_run2: list[int] = []
    outcomes2 = await _run_sync(crawler, db, run2_records, fetched_run2)

    # CORE ASSERTION: only the diff {2, 4} was fetched.
    assert sorted(fetched_run2) == [2, 4], (
        f"Re-sync fetched {sorted(fetched_run2)} — expected only the diff [2, 4]"
    )
    assert outcomes2 == {1: "skipped", 2: "downloaded", 3: "skipped", 4: "downloaded"}

    # Unchanged files must be byte-for-byte untouched (no re-write, no new ts).
    for eid, (ts, h, path) in keep.items():
        r = db.query(File).filter(File.external_file_id == eid).first()
        assert (r.download_ts, r.content_hash, r.local_path) == (ts, h, path), (
            f"File {eid} was modified on re-sync but should have been skipped"
        )

    # The restored + new files are now downloaded.
    for eid in (2, 4):
        r = db.query(File).filter(File.external_file_id == eid).first()
        assert r.status == "downloaded"
        assert r.content_hash == hashlib.sha256(
            b"%PDF-1.4 content for " + str(eid).encode()
        ).hexdigest()


# ---------------------------------------------------------------------------
# Test: documents that the diff is computed from DB state, not disk state.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_locally_deleted_file_is_not_refetched(in_memory_db, tmp_files_dir):
    """
    Design boundary: if the local PDF is deleted from disk but the DB row still
    says status='downloaded', the next sync SKIPS it (the diff is keyed on DB
    status, not on-disk presence).

    This asserts current behavior. If the requirement is "re-sync must restore a
    locally-deleted file", _download_file needs an extra guard (re-download when
    local_path is missing) — see the note returned with these tests.
    """
    db = in_memory_db
    crawler = _make_crawler(db, tmp_files_dir)

    fetched: list[int] = []
    await _run_sync(crawler, db, [_make_record(7)], fetched)
    assert fetched == [7]

    row = db.query(File).filter(File.external_file_id == 7).first()
    local = Path(row.local_path)
    assert local.exists()

    # Delete the file from disk; DB row still says 'downloaded'.
    local.unlink()
    assert not local.exists()

    fetched2: list[int] = []
    outcomes = await _run_sync(crawler, db, [_make_record(7)], fetched2)

    # Current behavior: DB is authoritative → skipped, no re-download.
    assert fetched2 == []
    assert outcomes == {7: "skipped"}
