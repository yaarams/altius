"""
PDF parsing module — pdfplumber-backed text and table extraction.

Public API
----------
    parse_pdf(path: str | Path) -> ParsedPdf

Returns a frozen ``ParsedPdf`` dataclass with:
    path       - absolute path to the source file (str)
    n_pages    - number of pages (int)
    text       - full concatenated text across all pages, pages separated by
                 form-feed (\\f) so callers can split on page boundaries (str)
    pages      - per-page text list, length == n_pages (list[str])
    tables     - all tables extracted across all pages; each table is a list of
                 rows, each row is a list of cells (str | None).
                 (list[list[list[str | None]]])

Corrupt / unreadable PDF contract
----------------------------------
``parse_pdf`` raises ``PdfParseError`` (subclass of ``ValueError``) for any
file that cannot be opened or parsed by pdfplumber.  It does NOT swallow the
underlying exception — it wraps and re-raises it so callers can log the cause.
Example::

    try:
        result = parse_pdf(bad_path)
    except PdfParseError as exc:
        log.warning("parse failed: %s", exc)

T2.2 (classifier) and T2.3 (extractor) MUST catch ``PdfParseError`` and set
``File.status = 'failed'`` with ``File.extraction_error = str(exc)``.

Determinism (Property 11)
--------------------------
Parsing the same PDF twice always produces identical ``ParsedPdf`` output.
All collections are built in page-order (no sorting, no randomisation) so
the result is deterministic given the same file content.

No network, no DB, no LLM calls are made in this module.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Typed exception
# ---------------------------------------------------------------------------

class PdfParseError(ValueError):
    """
    Raised when a PDF file cannot be opened or parsed.

    Wraps the underlying exception as the cause (``__cause__``).
    """


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParsedPdf:
    """
    Immutable result of parsing a single PDF file.

    Attributes
    ----------
    path:
        Absolute path to the source PDF (str form of the resolved Path).
    n_pages:
        Number of pages in the PDF.
    text:
        Full extracted text for the whole document.  Pages are concatenated
        and separated by a form-feed character (``\\f``) so callers can
        recover per-page text via ``text.split("\\f")``.  Guaranteed non-None
        (may be an empty string if the PDF contains no extractable text).
    pages:
        Per-page text strings in page order, length == n_pages.
        Each entry is an empty string when a page yields no text.
    tables:
        All tables extracted across all pages, in page order.  Each table is
        ``list[list[str | None]]`` (rows × cells).  Empty list when no tables
        are found.
    """
    path: str
    n_pages: int
    text: str
    pages: tuple[str, ...]
    tables: tuple[tuple[tuple[str | None, ...], ...], ...]

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def tables_as_lists(self) -> list[list[list[str | None]]]:
        """Return tables as plain nested lists (for callers that need mutability)."""
        return [
            [list(row) for row in table]
            for table in self.tables
        ]


# ---------------------------------------------------------------------------
# Table-extraction strategies (tried in order; first non-empty result wins)
# ---------------------------------------------------------------------------

_TABLE_STRATEGIES: list[dict] = [
    # 1. Default pdfplumber heuristic (works well for ruled tables)
    {},
    # 2. Text-alignment strategy (works for space-aligned tables w/o visible lines)
    {"vertical_strategy": "text", "horizontal_strategy": "text"},
    # 3. Lines only (strict — avoids false positives in text-heavy pages)
    {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
]


def _extract_tables_for_page(page: "pdfplumber.page.Page") -> list[list[list[str | None]]]:
    """
    Try each table-extraction strategy in order; return the first non-empty result.

    Returns an empty list if no strategy finds tables.
    """
    for strategy_kwargs in _TABLE_STRATEGIES:
        tables = page.extract_tables(table_settings=strategy_kwargs) if strategy_kwargs else page.extract_tables()
        if tables:
            return tables  # type: ignore[return-value]
    return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def parse_pdf(path: str | Path) -> ParsedPdf:
    """
    Parse a PDF file and return structured text + table data.

    Parameters
    ----------
    path:
        Filesystem path to the PDF.  May be str or Path.

    Returns
    -------
    ParsedPdf
        Frozen dataclass with ``path``, ``n_pages``, ``text``, ``pages``,
        ``tables``.

    Raises
    ------
    PdfParseError
        If the file cannot be opened or parsed (corrupt / not a PDF / IO
        error).  The underlying exception is chained as ``__cause__``.
    """
    resolved = Path(path).resolve()
    path_str = str(resolved)

    logger.debug("parse_pdf: opening %s", path_str)

    try:
        with pdfplumber.open(resolved) as pdf:
            n_pages: int = len(pdf.pages)

            per_page_text: list[str] = []
            all_tables: list[list[list[str | None]]] = []

            for page in pdf.pages:
                # --- text ---
                raw_text = page.extract_text()
                per_page_text.append(raw_text if raw_text is not None else "")

                # --- tables ---
                page_tables = _extract_tables_for_page(page)
                all_tables.extend(page_tables)

    except PdfParseError:
        raise
    except Exception as exc:
        logger.warning("parse_pdf: failed to parse %s — %s: %s", path_str, type(exc).__name__, exc)
        raise PdfParseError(
            f"Cannot parse PDF '{path_str}': {type(exc).__name__}: {exc}"
        ) from exc

    # Concatenate pages with form-feed separator (deterministic, page-ordered)
    full_text = "\f".join(per_page_text)

    # Convert to immutable nested tuples so the dataclass is truly frozen
    frozen_pages = tuple(per_page_text)
    frozen_tables: tuple[tuple[tuple[str | None, ...], ...], ...] = tuple(
        tuple(
            tuple(cell for cell in row)
            for row in table
        )
        for table in all_tables
    )

    result = ParsedPdf(
        path=path_str,
        n_pages=n_pages,
        text=full_text,
        pages=frozen_pages,
        tables=frozen_tables,
    )

    logger.debug(
        "parse_pdf: done — %d pages, %d chars text, %d tables",
        result.n_pages,
        len(result.text),
        len(result.tables),
    )
    return result
