from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from database.connection import db_session
from database.models import Document, DocumentStatus, ExtractedField, HITLQueueItem, HITLPriority
from extractor.groq_engine import extract_document, ExtractionResult
from parser.extractor import extract_text
from config import get_settings

logger = logging.getLogger("docverify.pipeline")
settings = get_settings()


async def process_document(doc_id: int) -> None:
    with db_session() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            logger.error("Doc %d not found", doc_id)
            return
        doc.status = DocumentStatus.processing

    try:
        parse = extract_text(_get_path(doc_id))
        if not parse.success:
            return _fail(doc_id, f"Parse failed: {parse.error}")

        result: ExtractionResult = extract_document(parse.text)
        if not result.success:
            return _fail(doc_id, f"Extraction failed: {result.error}")

        with db_session() as db:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            doc.detected_type = result.document_type
            doc.ai_confidence = result.overall_confidence
            doc.extraction_model = result.model_used
            doc.used_fallback = result.used_fallback
            doc.raw_extracted_json = result.raw_json
            doc.page_count = parse.page_count
            doc.processed_at = datetime.now(timezone.utc)

            fmap = {f.field_name: f for f in result.fields}
            _map_fields(doc, fmap)

            for f in result.fields:
                db.add(ExtractedField(
                    document_id=doc_id,
                    field_name=f.field_name,
                    field_value=str(f.field_value) if f.field_value is not None else None,
                    confidence=f.confidence,
                    page_number=_safe_int(f.page_hint),
                ))

            if result.hitl_required:
                doc.status = DocumentStatus.hitl_pending
                flagged = [f.field_name for f in result.flagged_fields]
                db.add(HITLQueueItem(
                    document_id=doc_id,
                    reason=(f"Confidence {int(result.overall_confidence * 100)}% below threshold. "
                            f"{len(flagged)} field(s) flagged."),
                    priority=_priority(result.overall_confidence),
                    flagged_fields=json.dumps(flagged),
                    overall_confidence=result.overall_confidence,
                ))
                logger.warning("Doc %d → HITL (conf=%.0f%%)", doc_id, result.overall_confidence * 100)
            else:
                doc.status = DocumentStatus.completed
                logger.info("Doc %d → completed (conf=%.0f%%, model=%s, %dms)",
                            doc_id, result.overall_confidence * 100, result.model_used, result.latency_ms)

    except Exception as e:
        logger.exception("Pipeline error doc %d: %s", doc_id, e)
        _fail(doc_id, str(e))


def _get_path(doc_id: int) -> str:
    with db_session() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        return doc.file_path if doc else ""


def _fail(doc_id: int, reason: str) -> None:
    with db_session() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = DocumentStatus.failed
            doc.error_message = reason
            doc.processed_at = datetime.now(timezone.utc)
    logger.error("Doc %d failed: %s", doc_id, reason)


def _map_fields(doc: Document, fm: dict) -> None:
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
        if src in fm and fm[src].field_value not in (None, "null", ""):
            setattr(doc, dst, str(fm[src].field_value))


def _priority(conf: float) -> HITLPriority:
    if conf < 0.40: return HITLPriority.critical
    if conf < 0.55: return HITLPriority.high
    if conf < 0.65: return HITLPriority.medium
    return HITLPriority.low


def _safe_int(v: str):
    try: return int(v)
    except: return None
