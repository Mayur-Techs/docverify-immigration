from __future__ import annotations

import json
import logging
from datetime import datetime
from datetime import timezone

from config import get_settings
from database.connection import db_session
from database.models import Document
from database.models import DocumentStatus
from database.models import ExtractedField
from database.models import HITLPriority
from database.models import HITLQueueItem
from extractor.groq_engine import ExtractionResult
from extractor.groq_engine import FieldResult
from extractor.groq_engine import _run_validation
from extractor.groq_engine import extract_fields_chunked
from parser.extractor import extract_text_chunked

logger = logging.getLogger("docverify.pipeline")
settings = get_settings()


async def process_document(doc_id: int) -> None:
    from app import get_semaphore
    sem = get_semaphore()
    async with sem:
        await _process(doc_id)


async def _process(doc_id: int) -> None:
    """
    Full pipeline:
      1. Load document path from DB
      2. Parse PDF → overlapping chunks (prevents page drops/OOM)
      3. Fast heuristic type scan on first chunk
      4. Targeted chunked extraction via Groq schema selection
      5. Run post-extraction 12-rule validation layer
      6. Route: completed | hitl_pending based on confidence + validation
    """
    with db_session() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            logger.error("Document %d not found", doc_id)
            return
        doc.status = DocumentStatus.processing
        file_path = doc.file_path

    try:
        chunks, page_count = extract_text_chunked(file_path)
        if not chunks:
            _fail(doc_id, "PDF parse failed: no text extracted from document")
            return

        # Detect document type from first chunk only (fast, cheap, no schema needed)
        detected_type = _detect_document_type(chunks[0])

        # Extract fields across all chunks using the targeted schema for this type
        merged_dict = extract_fields_chunked(chunks, detected_type)

        # Wrap merged dict into ExtractionResult for the validation layer
        fields_list = [
            FieldResult(field_name=k, field_value=v, confidence=0.95)
            for k, v in merged_dict.items()
            if not _is_null_merged(v)
        ]
        result = ExtractionResult(
            success=True,
            document_type=detected_type,
            fields=fields_list,
            model_used=settings.groq_primary_model,
            raw_json=json.dumps(merged_dict),
        )
        result = _run_validation(result)

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
            doc.page_count = page_count
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


def _map_top_fields(doc: Document, fm: dict[str, FieldResult]) -> None:
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
        # Targeted layout schema adjustments mapping back to database core properties
        "surname": "applicant_name",
        "beneficiary_surname": "applicant_name",
        "given_names": "applicant_name",
        "beneficiary_given_names": "applicant_name",
        "date_of_expiry": "passport_expiry",
        "passport_expiry": "passport_expiry",
        "beneficiary_passport_number": "passport_number",
        "beneficiary_dob": "applicant_dob",
        "beneficiary_country_of_citizenship": "applicant_nationality",
        "validity_start": "validity_start",
        "validity_end": "validity_end",
        "lca_case_number": "petition_number",
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


def _is_null_merged(v: object) -> bool:
    """Filter out null-equivalent values from the merged extraction dict."""
    if v is None:
        return True
    return str(v).strip().lower() in {"null", "none", "", "not found", "n/a", "na", "unknown"}


def _detect_document_type(first_chunk: str) -> str:
    """
    Fast heuristic type detection from first 8000 chars.
    No API call — keyword scan only. Sufficient for pilot document types.
    Returns a string matching get_schema_for_type() keys: passport, i129, ds160, general.
    """
    text = first_chunk.lower()

    # I-129 signals
    if any(kw in text for kw in [
        "petition for a nonimmigrant worker",
        "h-1b", "h1b", "labor condition application",
        "lca case number", "i-129",
    ]):
        return "i129"

    # DS-160 signals
    if any(kw in text for kw in [
        "nonimmigrant visa application", "ds-160", "ds160",
        "application id", "consular processing",
    ]):
        return "ds160"

    # Passport signals
    if any(kw in text for kw in [
        "passport", "republic of", "nationality",
        "place of birth", "date of issue", "date of expiry",
        "p<", "mrz",
    ]):
        return "passport"

    return "general"