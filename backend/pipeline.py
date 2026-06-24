"""
Pipeline orchestration — T2.5.

process_file(file, db)      — classify → if capital_account_statement: extract
process_all_pending(db?)    — idempotent: skip already-classified (P5) / already-extracted (R3.5)

Called by the sync orchestrator.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import File
from backend.db.session import get_session_factory
from backend.pdf_parser import parse_pdf, PdfParseError
from backend.classifier.document_classifier import (
    ClassificationResult,
    classify_and_persist,
)
from backend.extractor.statement_extractor import (
    ExtractionData,
    ExtractionError,
    extract_and_persist,
)

logger = logging.getLogger(__name__)


def process_file(
    file: File, db: Session
) -> tuple[ClassificationResult | None, ExtractionData | None]:
    """
    Classify a single file, then extract if it's a capital account statement.

    Returns (classification_result, extraction_data).
    extraction_data is None for non-CAS files or when extraction fails.

    Idempotent:
      - P5: classify_and_persist skips if file.classification is already set.
      - R3.5: extractor skips if file.status == 'extracted'.
    """
    clf_result: Optional[ClassificationResult] = None
    ext_data: Optional[ExtractionData] = None

    # --- Parse PDF ---
    if not file.local_path:
        logger.warning("File %d has no local_path — skipping.", file.id)
        return None, None

    try:
        parsed = parse_pdf(file.local_path)
    except PdfParseError as exc:
        logger.warning("File %d: PDF parse failed: %s", file.id, exc)
        file.status = "failed"
        file.extraction_error = str(exc)
        db.add(file)
        db.commit()
        return None, None

    # --- Classify (P5: idempotent) ---
    clf_result = classify_and_persist(file, parsed, db)
    logger.info(
        "File %d %r classified as %s (confidence=%.2f, method=%s)",
        file.id, file.file_name, clf_result.label, clf_result.confidence, clf_result.method,
    )

    # --- Extract (only for CAS, and only if not already extracted) ---
    if clf_result.label == "capital_account_statement":
        # R3.5: skip if already successfully extracted
        if file.status == "extracted":
            logger.debug("File %d already extracted — skipping extraction.", file.id)
        else:
            try:
                stmt = extract_and_persist(file, parsed, db)
                ext_data = ExtractionData(
                    fund_name=stmt.fund_name,
                    statement_date=stmt.statement_date,
                    current_value=stmt.current_value,
                )
                logger.info(
                    "File %d extracted: fund=%r date=%s value=%s",
                    file.id,
                    ext_data.fund_name,
                    ext_data.statement_date,
                    ext_data.current_value,
                )
            except ExtractionError as exc:
                logger.warning("File %d extraction failed: %s", file.id, exc)

    return clf_result, ext_data


def process_all_pending(db: Optional[Session] = None) -> dict:
    """
    Process all downloaded-but-not-yet-classified files.

    Idempotent:
      - Files with a non-null classification are skipped (P5 — handled in classifier).
      - Files with status='extracted' skip the extract step (R3.5 — handled in process_file).

    Returns a summary dict with counts.
    """
    _own_session = db is None
    if _own_session:
        factory = get_session_factory()
        db = factory()

    try:
        # Load all files with status='downloaded' (includes both classified and unclassified)
        # Also include 'failed' status to allow retry
        files = (
            db.query(File)
            .filter(File.status.in_(["downloaded", "failed"]))
            .all()
        )

        total = len(files)
        classified = 0
        extracted = 0
        failed_extract = 0
        skipped = 0

        for file in files:
            # Skip if already classified AND already extracted (fully processed)
            if file.classification is not None and file.status == "extracted":
                skipped += 1
                logger.debug("File %d fully processed — skipping.", file.id)
                continue

            clf_result, ext_data = process_file(file, db)

            if clf_result is not None and clf_result.label != "unclassified":
                classified += 1

            if ext_data is not None:
                extracted += 1

        summary = {
            "total_files": total,
            "classified": classified,
            "extracted": extracted,
            "failed_extraction": failed_extract,
            "skipped": skipped,
        }
        logger.info("Pipeline complete: %s", summary)
        return summary

    finally:
        if _own_session:
            db.close()
