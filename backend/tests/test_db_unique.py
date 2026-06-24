"""
Property 13: DB Uniqueness Constraint on external_file_id.

For any attempt to insert two File records with the same external_file_id,
the second insert SHALL raise a unique constraint violation (IntegrityError).

Feature: investor-document-platform, Property 13: DB uniqueness constraint on external_file_id
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.db.session import Base
from backend.db.models import File

# ---------------------------------------------------------------------------
# In-memory SQLite engine for tests — isolated per session
# ---------------------------------------------------------------------------

def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Enable foreign keys
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def _fk(conn, _rec):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session()


# ---------------------------------------------------------------------------
# Example-based test (deterministic)
# ---------------------------------------------------------------------------

def test_duplicate_external_file_id_raises_integrity_error():
    """Inserting two File rows with the same external_file_id must raise IntegrityError."""
    db = _make_session()
    try:
        f1 = File(external_file_id=42, file_name="alpha.pdf", status="pending")
        f2 = File(external_file_id=42, file_name="beta.pdf", status="pending")
        db.add(f1)
        db.commit()

        db.add(f2)
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.close()


def test_distinct_external_file_ids_are_allowed():
    """Two File rows with DIFFERENT external_file_ids must both be insertable."""
    db = _make_session()
    try:
        f1 = File(external_file_id=1, file_name="alpha.pdf", status="pending")
        f2 = File(external_file_id=2, file_name="beta.pdf", status="pending")
        db.add_all([f1, f2])
        db.commit()  # must not raise
        assert db.query(File).count() == 2
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Hypothesis property-based test (≥ 100 examples)
# Feature: investor-document-platform, Property 13: DB uniqueness constraint on external_file_id
# ---------------------------------------------------------------------------

h_settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=5000,
)
h_settings.load_profile("ci")


@given(
    ext_id=st.integers(min_value=1, max_value=10_000_000),
    name1=st.text(min_size=1, max_size=80).filter(lambda s: "\x00" not in s),
    name2=st.text(min_size=1, max_size=80).filter(lambda s: "\x00" not in s),
)
@h_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=5000)
def test_hypothesis_dup_external_file_id_raises(ext_id: int, name1: str, name2: str):
    """
    For any external_file_id, inserting a second row with the same id raises IntegrityError.
    """
    db = _make_session()
    try:
        f1 = File(external_file_id=ext_id, file_name=name1, status="pending")
        db.add(f1)
        db.commit()

        f2 = File(external_file_id=ext_id, file_name=name2, status="pending")
        db.add(f2)
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()
