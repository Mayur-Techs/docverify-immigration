from __future__ import annotations
import json, logging, time
from dataclasses import dataclass, field
from typing import Any
from groq import Groq, APIError, APITimeoutError, RateLimitError
from config import get_settings

logger = logging.getLogger("docverify.extractor")
settings = get_settings()

SYSTEM_PROMPT = """You are a precision immigration document extraction engine used by a top UK-US immigration law firm. 
Extract all fields. Return ONLY valid JSON — no markdown fences, no explanation whatsoever."""

EXTRACTION_PROMPT = """Extract every available field from the immigration document below.

Return ONLY this JSON structure, nothing else:
{
  "document_type": "<i129|i140|i485|passport|visa|l1_petition|ds160|eea_form|biometric|other>",
  "document_type_confidence": <0-100>,
  "overall_confidence": <0-100>,
  "extraction_notes": "<warnings or issues>",
  "fields": [
    {
      "field_name": "<snake_case>",
      "field_value": "<value or null>",
      "confidence": <0-100>,
      "page_hint": "<section or page>",
      "needs_review": <true|false>
    }
  ]
}

Confidence scoring:
- 95-100: Clearly visible, unambiguous
- 85-94: Visible, minor format ambiguity  
- 70-84: Inferred or partially visible
- 50-69: Significant uncertainty
- 0-49: Very uncertain — set needs_review: true

Set needs_review: true when confidence < 75 OR value looks malformed/incomplete.

Key fields to extract (all that exist):
applicant_name, applicant_family_name, applicant_given_name, date_of_birth,
nationality, country_of_citizenship, country_of_birth, passport_number,
passport_expiry_date, passport_issue_date, alien_registration_number,
petition_number, receipt_number, employer_name, petitioner_name, employer_fein,
visa_classification, priority_date, validity_period_start, validity_period_end,
consulate_or_port_of_entry, job_title, position_offered, annual_wage, salary,
lca_case_number, current_immigration_status, status_expiry_date, form_number,
beneficiary_address, petitioner_address, relationship_type, mrz_line_1, mrz_line_2

DOCUMENT TEXT:
"""


@dataclass
class FieldResult:
    field_name: str
    field_value: Any
    confidence: float
    page_hint: str = ""
    needs_review: bool = False


@dataclass
class ExtractionResult:
    success: bool
    document_type: str = "other"
    document_type_confidence: float = 0.0
    overall_confidence: float = 0.0
    fields: list[FieldResult] = field(default_factory=list)
    extraction_notes: str = ""
    model_used: str = ""
    used_fallback: bool = False
    raw_json: str = ""
    error: str = ""
    latency_ms: int = 0

    @property
    def hitl_required(self) -> bool:
        return self.overall_confidence < (settings.confidence_hitl_threshold / 100)

    @property
    def flagged_fields(self) -> list[FieldResult]:
        return [f for f in self.fields if f.needs_review or f.confidence < 0.75]


def extract_document(text: str) -> ExtractionResult:
    start = time.perf_counter()
    result = _call_groq(text, settings.groq_primary_model)
    if result.success:
        result.latency_ms = int((time.perf_counter() - start) * 1000)
        return result
    logger.warning("Primary model failed (%s), using fallback", result.error)
    result = _call_groq(text, settings.groq_fallback_model)
    result.used_fallback = True
    result.latency_ms = int((time.perf_counter() - start) * 1000)
    return result


def _call_groq(text: str, model: str) -> ExtractionResult:
    try:
        client = Groq(api_key=settings.groq_api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": EXTRACTION_PROMPT + text}
            ],
            temperature=0.0,
            max_tokens=4096,
            timeout=settings.groq_timeout,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1][4:] if parts[1].startswith("json") else parts[1]
        return _parse_response(raw.strip(), model)
    except APITimeoutError as e:
        return ExtractionResult(success=False, error=f"timeout:{e}", model_used=model)
    except RateLimitError as e:
        return ExtractionResult(success=False, error=f"rate_limit:{e}", model_used=model)
    except APIError as e:
        return ExtractionResult(success=False, error=f"api:{e}", model_used=model)
    except Exception as e:
        return ExtractionResult(success=False, error=str(e), model_used=model)


def _parse_response(raw: str, model: str) -> ExtractionResult:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON parse error: %s | raw[:300]=%s", e, raw[:300])
        return ExtractionResult(success=False, error=f"json:{e}", model_used=model, raw_json=raw)

    def to_01(v):
        v = float(v or 0)
        return max(0.0, min(1.0, v / 100.0 if v > 1 else v))

    fields = [
        FieldResult(
            field_name=f.get("field_name", "unknown"),
            field_value=f.get("field_value"),
            confidence=to_01(f.get("confidence", 0)),
            page_hint=str(f.get("page_hint", "")),
            needs_review=bool(f.get("needs_review", False)) or to_01(f.get("confidence", 0)) < 0.75,
        )
        for f in data.get("fields", [])
    ]
    return ExtractionResult(
        success=True,
        document_type=data.get("document_type", "other"),
        document_type_confidence=to_01(data.get("document_type_confidence", 0)),
        overall_confidence=to_01(data.get("overall_confidence", 0)),
        fields=fields,
        extraction_notes=data.get("extraction_notes", ""),
        model_used=model,
        raw_json=raw,
    )
