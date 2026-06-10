from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from groq import Groq

from config import get_settings
from extractor.field_schemas import get_schema_for_type
from extractor.validator import ValidationResult
from extractor.validator import validate_extraction

logger = logging.getLogger("docverify.extractor")
settings = get_settings()

SYSTEM_PROMPT = (
    "You are a precision immigration document extraction engine used by a top "
    "UK-US immigration law firm. Extract all fields requested. Return ONLY valid JSON — "
    "no markdown fences, no explanation whatsoever."
)

@dataclass
class FieldResult:
    field_name: str
    field_value: Any
    confidence: float
    page_hint: str = ""
    needs_review: bool = False
    validation_flags: list = field(default_factory=list)
    validation_severity: str = ""


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
    validation: ValidationResult = field(default_factory=ValidationResult)

    @property
    def hitl_required(self) -> bool:
        return (
            self.overall_confidence < (settings.confidence_hitl_threshold / 100)
            or self.validation.has_errors
        )

    @property
    def flagged_fields(self) -> list[FieldResult]:
        return [f for f in self.fields if f.needs_review or f.confidence < 0.75]

    @property
    def validation_error_count(self) -> int:
        return sum(1 for f in self.validation.flags if f.severity == "error")

    @property
    def validation_warning_count(self) -> int:
        return sum(1 for f in self.validation.flags if f.severity == "warning")


def _is_null_value(v: Any) -> bool:
    """Defensive check against LLM hallucinated null-equivalents with inconsistent casing."""
    if v is None:
        return True
    return str(v).strip().lower() in {"null", "none", "", "not found", "n/a", "na", "unknown"}


def extract_fields_chunked(chunks: list[str], document_type: str) -> dict[str, Any]:
    """
    Processes chunks sequentially using targeted field schemas. 
    First non-null value wins.
    """
    schema = get_schema_for_type(document_type)
    schema_json = json.dumps(
        [{"field_name": f["field_name"], "description": f["description"]} for f in schema],
        indent=2
    )

    merged_results: dict[str, Any] = {}

    for i, chunk in enumerate(chunks):
        logger.info("Processing chunk %d/%d for type %s", i + 1, len(chunks), document_type)

        chunk_prompt = f"""You are extracting fields from a section of an immigration document.
Document type: {document_type}
Fields to extract:
{schema_json}

Return ONLY a valid JSON object. No explanation, no markdown, no code fences.
For each field, return the extracted value as a string, or null if not found in this section.
Dates must be in MM/DD/YYYY format. Currency as numeric string only e.g. "95000".
"D/S" and "Duration of Status" are valid values for status expiry fields — return them as-is, do not convert.

Document section:
{chunk}"""

        raw_resp, used_fallback = _execute_groq_call(chunk_prompt)
        if not raw_resp:
            logger.warning("Chunk %d failed to return data", i + 1)
            continue

        try:
            chunk_data = json.loads(raw_resp)
            for field_def in schema:
                fname = field_def["field_name"]

                # If field isn't tracked yet, or the current tracked value is a hallucinated empty string,
                # we are eligible to overwrite it.
                if fname not in merged_results or _is_null_value(merged_results.get(fname)):
                    val = chunk_data.get(fname)
                    # Only overwrite if the new chunk actually found something real
                    if not _is_null_value(val):
                        merged_results[fname] = val

        except json.JSONDecodeError as exc:
            logger.error("JSON decode error on chunk %d: %s", i + 1, exc)

    return merged_results


def _execute_groq_call(prompt: str) -> tuple[str, bool]:
    """Handles the raw Groq request with exponential backoff fallback logic."""
    model = settings.groq_primary_model
    used_fallback = False

    try:
        raw = _make_api_call(prompt, model)
    except Exception as exc:
        logger.warning("Primary model failed (%s), using fallback", str(exc))
        model = settings.groq_fallback_model
        used_fallback = True
        try:
            raw = _make_api_call(prompt, model)
        except Exception as fallback_exc:
            logger.error("Fallback model also failed: %s", str(fallback_exc))
            return "", used_fallback

    # Clean markdown fences strictly
    raw = raw.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 3:
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:].strip()
    return raw, used_fallback


def _make_api_call(prompt: str, model: str) -> str:
    client = Groq(api_key=settings.groq_api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=4096,
        timeout=settings.groq_timeout,
    )
    return resp.choices[0].message.content


def _run_validation(result: ExtractionResult) -> ExtractionResult:
    """Run the validation layer and apply penalties."""
    if not result.success:
        return result

    field_dict: dict[str, Any] = {
        f.field_name: f.field_value
        for f in result.fields
        if f.field_value not in (None, "null", "None", "")
    }

    vr = validate_extraction(field_dict)
    result.validation = vr

    flagged_by_field: dict[str, list] = {}
    for flag in vr.flags:
        flagged_by_field.setdefault(flag.field_name, []).append(flag)

    for f in result.fields:
        flags = flagged_by_field.get(f.field_name, [])
        if not flags:
            continue
        f.validation_flags = flags
        severities = [fl.severity for fl in flags]
        f.validation_severity = "error" if "error" in severities else "warning"
        if f.validation_severity == "error":
            f.needs_review = True
            f.confidence = min(f.confidence, 0.40)
        else:
            f.needs_review = True
            f.confidence = min(f.confidence, 0.72)

    valid_confs = [
        f.confidence for f in result.fields
        if f.field_value not in (None, "null", "None", "")
    ]
    if valid_confs:
        penalised = (sum(valid_confs) / len(valid_confs)) - vr.overall_penalty
        result.overall_confidence = max(0.0, min(1.0, penalised))

    return result
