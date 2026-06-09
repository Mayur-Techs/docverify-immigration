from __future__ import annotations

import json
import logging
from datetime import datetime
from datetime import timezone

from database.connection import db_session
from database.models import Document
from database.models import DocumentStatus
from database.models import ExtractedField
from database.models import HITLPriority
from database.models import HITLQueueItem
from extractor.groq_engine import ExtractionResult
from extractor.groq_engine import extract_document
from parser.extractor import extract_text
from config import get_settings

logger = logging.getLogger("docverify.pipeline")
settings = get_settings()


async def process_document(doc_id: int) -> None:
    """
    Full pipeline:
      1. Load document path from DB
      2. Parse PDF → text
      3. Extract fields with Groq (+ automatic fallback)
      4. Run 12-rule validation layer
      5. Route: completed | hitl_pending based on confidence + validation
    """
    with db_session() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            logger.error("Document %d not found", doc_id)
            return
        doc.status = DocumentStatus.processing
        file_path = doc.file_path

    try:
        parse = extract_text(file_path)
        if not parse.success:
            _fail(doc_id, f"PDF parse failed: {parse.error}")
            return

        result: ExtractionResult = extract_document(parse.text)
        if not result.success:
            _fail(doc_id, f"Extraction failed: {result.error}")
            return

        with db_session() as db:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if not doc:
                return

            doc.detected_type = result.document_type
            doc.ai_confidence = result.overall_confidence
            doc.extraction_model = result.model_used
            doc.used_fallback = result.used_fallback
            doc.raw_extracted_json = result.raw_json
            doc.page_count = parse.page_count
            doc.processed_at = datetime.now(timezone.utc)

            _map_top_fields(doc, {f.field_name: f for f in result.fields})

            for f in result.fields:
                flags_json = None
                if f.validation_flags:
                    flags_json = json.dumps([
                        {
                            "severity": fl.severity,
                            "reason": fl.reason,
                            "action": fl.suggested_action,
                        }
                        for fl in f.validation_flags
                    ])
                db.add(ExtractedField(
                    document_id=doc_id,
                    field_name=f.field_name,
                    field_value=str(f.field_value) if f.field_value is not None else None,
                    confidence=f.confidence,
                    page_number=_safe_int(f.page_hint),
                    validation_flags_json=flags_json,
                    validation_severity=f.validation_severity or "",
                ))

            if result.hitl_required:
                doc.status = DocumentStatus.hitl_pending
                flagged = [f.field_name for f in result.flagged_fields]
                db.add(HITLQueueItem(
                    document_id=doc_id,
                    reason=(
                        f"Confidence {int(result.overall_confidence * 100)}% below threshold. "
                        f"{len(flagged)} field(s) flagged. "
                        f"Validation: {result.validation_error_count} error(s), "
                        f"{result.validation_warning_count} warning(s)."
                    ),
                    priority=_priority(result.overall_confidence),
                    flagged_fields=json.dumps(flagged),
                    overall_confidence=result.overall_confidence,
                ))
                logger.warning(
                    "Doc %d → HITL (conf=%.0f%%, errors=%d)",
                    doc_id,
                    result.overall_confidence * 100,
                    result.validation_error_count,
                )
            else:
                doc.status = DocumentStatus.completed
                logger.info(
                    "Doc %d → completed (conf=%.0f%%, model=%s, fallback=%s, %dms)",
                    doc_id,
                    result.overall_confidence * 100,
                    result.model_used,
                    result.used_fallback,
                    result.latency_ms,
                )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled pipeline error doc %d: %s", doc_id, exc)
        _fail(doc_id, str(exc))


def _fail(doc_id: int, reason: str) -> None:
    with db_session() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = DocumentStatus.failed
            doc.error_message = reason
            doc.processed_at = datetime.now(timezone.utc)
    logger.error("Doc %d failed: %s", doc_id, reason)


def _map_top_fields(doc: Document, fm: dict) -> None:
    mapping = {
        "applicant_name": "applicant_name",
        "date_of_birth": "applicant_dob",
        "nationality": "applicant_nationality",
        "country_of_citizenship": "applicant_nationality",
        "passport_number": "passport_number",
        "passport_expiry_date": "passport_expiry",
        "employer_name": "employer_name",
        "petitioner_name": "employer_name",
        "visa_classification": "visa_classification",
        "priority_date": "priority_date",
        "validity_period_start": "validity_start",
        "validity_period_end": "validity_end",
        "consulate_or_port_of_entry": "consulate",
        "job_title": "job_title",
        "position_offered": "job_title",
        "annual_wage": "wage",
        "petition_number": "petition_number",
        "receipt_number": "petition_number",
    }
    for src, dst in mapping.items():
        if src in fm and fm[src].field_value not in (None, "null", "None", ""):
            setattr(doc, dst, str(fm[src].field_value))


def _priority(conf: float) -> HITLPriority:
    if conf < 0.40:
        return HITLPriority.critical
    if conf < 0.55:
        return HITLPriority.high
    if conf < 0.65:
        return HITLPriority.medium
    return HITLPriority.low


def _safe_int(v: str) -> int | None:
    try:
        return int(v)
    except (ValueError, TypeError):
        return None
