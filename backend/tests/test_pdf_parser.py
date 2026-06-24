"""
Tests for backend/pdf_parser/parser.py — T2.1 / R10 / Property 11.

Property 11 (round-trip / determinism): parsing the same PDF twice yields
identical text and table output.

Corpus PDFs are referenced by absolute path from data/files/.  If the
directory is absent (e.g. CI without the corpus), the corpus tests are
skipped gracefully.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "files"

# Representative PDFs: CAS, quarterly report, junk
_CAS_PDF = _DATA_DIR / "22056_fund_alpha_Q3_2025_CapitalAccount__1_.pdf"
_REPORT_PDF = _DATA_DIR / "22023_fund_alpha_Q1_2023_Update__1_.pdf"
_JUNK_PDF = _DATA_DIR / "16976_345.pdf"

_CORPUS_AVAILABLE = _DATA_DIR.is_dir() and _CAS_PDF.exists()

skip_no_corpus = pytest.mark.skipif(
    not _CORPUS_AVAILABLE,
    reason="Corpus not available at data/files/; skipping corpus-dependent tests",
)


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from backend.pdf_parser.parser import ParsedPdf, PdfParseError, parse_pdf  # noqa: E402


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _assert_valid_parsed_pdf(result: ParsedPdf, path: Path) -> None:
    """Common structural assertions on a ParsedPdf result."""
    assert isinstance(result, ParsedPdf)
    assert result.path == str(path.resolve())
    assert isinstance(result.n_pages, int)
    assert result.n_pages > 0
    assert isinstance(result.text, str)
    assert isinstance(result.pages, tuple)
    assert len(result.pages) == result.n_pages
    assert isinstance(result.tables, tuple)
    # Each table is a tuple of rows; each row is a tuple of cells
    for table in result.tables:
        assert isinstance(table, tuple)
        for row in table:
            assert isinstance(row, tuple)
            for cell in row:
                assert cell is None or isinstance(cell, str)


# ---------------------------------------------------------------------------
# Corpus tests
# ---------------------------------------------------------------------------

@skip_no_corpus
def test_parse_cas_pdf_returns_non_empty_text():
    """Capital account statement: text is non-empty and n_pages >= 1."""
    result = parse_pdf(_CAS_PDF)
    _assert_valid_parsed_pdf(result, _CAS_PDF)
    assert len(result.text.strip()) > 0, "Expected non-empty text from CAS PDF"


@skip_no_corpus
def test_parse_cas_pdf_tables_is_list():
    """CAS: tables field is a tuple (possibly empty — no crash either way)."""
    result = parse_pdf(_CAS_PDF)
    assert isinstance(result.tables, tuple)
    # tables_as_lists() convenience method works
    as_lists = result.tables_as_lists()
    assert isinstance(as_lists, list)


@skip_no_corpus
def test_parse_report_pdf_multi_page():
    """Quarterly report: correctly extracts multi-page PDF (>= 1 page)."""
    result = parse_pdf(_REPORT_PDF)
    _assert_valid_parsed_pdf(result, _REPORT_PDF)
    assert result.n_pages >= 1
    assert len(result.text.strip()) > 0
    # Pages list length matches n_pages
    assert len(result.pages) == result.n_pages


@skip_no_corpus
def test_parse_report_pdf_page_boundary_separator():
    """Full text pages joined by form-feed; splitting recovers per-page text."""
    result = parse_pdf(_REPORT_PDF)
    split_pages = result.text.split("\f")
    assert len(split_pages) == result.n_pages
    # Each split page matches the pages tuple
    for split, stored in zip(split_pages, result.pages):
        assert split == stored


@skip_no_corpus
def test_parse_junk_pdf_does_not_crash():
    """Junk PDF (16976_345.pdf) should parse without raising (it is a valid PDF)."""
    result = parse_pdf(_JUNK_PDF)
    _assert_valid_parsed_pdf(result, _JUNK_PDF)
    # junk may have low text or empty tables — neither is an error
    assert isinstance(result.text, str)
    assert isinstance(result.tables, tuple)


# ---------------------------------------------------------------------------
# Property 11: determinism / round-trip
# ---------------------------------------------------------------------------

@skip_no_corpus
def test_property11_determinism_cas():
    """Property 11: parsing the same CAS PDF twice yields identical results."""
    result_a = parse_pdf(_CAS_PDF)
    result_b = parse_pdf(_CAS_PDF)
    assert result_a == result_b, "parse_pdf is not deterministic for CAS PDF"


@skip_no_corpus
def test_property11_determinism_report():
    """Property 11: parsing the same report PDF twice yields identical results."""
    result_a = parse_pdf(_REPORT_PDF)
    result_b = parse_pdf(_REPORT_PDF)
    assert result_a == result_b, "parse_pdf is not deterministic for report PDF"


# ---------------------------------------------------------------------------
# Corrupt / non-PDF input
# ---------------------------------------------------------------------------

def test_corrupt_pdf_raises_pdf_parse_error():
    """
    A file containing arbitrary bytes that is not a valid PDF must raise
    PdfParseError — not a raw/unexpected exception.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"not a pdf")
        tmp_path = tmp.name

    try:
        with pytest.raises(PdfParseError) as exc_info:
            parse_pdf(tmp_path)
        # The error message should reference the file path
        assert tmp_path in str(exc_info.value) or "parse" in str(exc_info.value).lower()
    finally:
        os.unlink(tmp_path)


def test_corrupt_pdf_chained_cause():
    """PdfParseError wraps the original exception as __cause__."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(b"\x00\x01\x02\x03 totally not a PDF")
        tmp_path = tmp.name

    try:
        with pytest.raises(PdfParseError) as exc_info:
            parse_pdf(tmp_path)
        # __cause__ is set (wrapped original exception)
        assert exc_info.value.__cause__ is not None
    finally:
        os.unlink(tmp_path)


def test_nonexistent_file_raises_pdf_parse_error():
    """Attempting to parse a file that doesn't exist raises PdfParseError."""
    with pytest.raises(PdfParseError):
        parse_pdf("/nonexistent/path/to/missing_file.pdf")


# ---------------------------------------------------------------------------
# ParsedPdf structure / API contract
# ---------------------------------------------------------------------------

@skip_no_corpus
def test_parsed_pdf_is_frozen():
    """ParsedPdf is immutable (frozen dataclass)."""
    result = parse_pdf(_CAS_PDF)
    with pytest.raises((AttributeError, TypeError)):
        result.text = "tampered"  # type: ignore[misc]


@skip_no_corpus
def test_tables_as_lists_returns_mutable_lists():
    """tables_as_lists() converts frozenish tuples to plain list-of-list-of-list."""
    result = parse_pdf(_CAS_PDF)
    tbl_lists = result.tables_as_lists()
    assert isinstance(tbl_lists, list)
    for tbl in tbl_lists:
        assert isinstance(tbl, list)
        for row in tbl:
            assert isinstance(row, list)


@skip_no_corpus
def test_parse_pdf_accepts_string_path():
    """parse_pdf() accepts str as well as Path."""
    result_str = parse_pdf(str(_CAS_PDF))
    result_path = parse_pdf(_CAS_PDF)
    assert result_str == result_path


@skip_no_corpus
def test_parse_pdf_path_field_is_absolute():
    """ParsedPdf.path is always an absolute path string."""
    result = parse_pdf(_CAS_PDF)
    assert os.path.isabs(result.path)
