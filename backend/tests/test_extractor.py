"""Groq extraction engine tests — Groq API fully mocked."""
import json
import os
import sys
from unittest.mock import MagicMock
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

MOCK_RESPONSE = {
    "document_type": "i129",
    "document_type_confidence": 97,
    "overall_confidence": 92,
    "extraction_notes": "All fields clearly visible",
    "fields": [
        {
            "field_name": "applicant_name",
            "field_value": "Arjun Sharma",
            "confidence": 99,
            "page_hint": "1",
            "needs_review": False,
        },
        {
            "field_name": "passport_number",
            "field_value": "J8821045",
            "confidence": 96,
            "page_hint": "1",
            "needs_review": False,
        },
        {
            "field_name": "visa_classification",
            "field_value": "H-1B",
            "confidence": 99,
            "page_hint": "1",
            "needs_review": False,
        },
        {
            "field_name": "priority_date",
            "field_value": None,
            "confidence": 0,
            "page_hint": "",
            "needs_review": True,
        },
        {
            "field_name": "employer_name",
            "field_value": "Acme Technologies",
            "confidence": 98,
            "page_hint": "1",
            "needs_review": False,
        },
    ],
}

LOW_CONF_RESPONSE = {
    "document_type": "other",
    "document_type_confidence": 30,
    "overall_confidence": 45,
    "extraction_notes": "Low quality scan",
    "fields": [
        {
            "field_name": "applicant_name",
            "field_value": "??",
            "confidence": 40,
            "page_hint": "",
            "needs_review": True,
        },
    ],
}


def _make_mock(response_json: dict) -> MagicMock:
    mock = MagicMock()
    msg = MagicMock()
    msg.content = json.dumps(response_json)
    mock.chat.completions.create.return_value.choices = [MagicMock(message=msg)]
    return mock


def test_successful_extraction():
    from extractor.groq_engine import extract_document
    with patch("extractor.groq_engine.Groq", return_value=_make_mock(MOCK_RESPONSE)):
        result = extract_document("Sample I-129 text")
    assert result.success
    assert result.document_type == "i129"
    assert 0.80 <= result.overall_confidence <= 1.0


def test_high_confidence_not_hitl():
    from extractor.groq_engine import extract_document
    with patch("extractor.groq_engine.Groq", return_value=_make_mock(MOCK_RESPONSE)):
        result = extract_document("text")
    # Clean mock has no validation errors — HITL only if confidence < threshold
    assert result.validation_error_count == 0


def test_low_confidence_hitl():
    from extractor.groq_engine import extract_document
    with patch("extractor.groq_engine.Groq", return_value=_make_mock(LOW_CONF_RESPONSE)):
        result = extract_document("blurry scan text")
    assert result.hitl_required
    assert result.overall_confidence < 0.75


def test_flagged_fields_identified():
    from extractor.groq_engine import extract_document
    with patch("extractor.groq_engine.Groq", return_value=_make_mock(MOCK_RESPONSE)):
        result = extract_document("text")
    flagged = result.flagged_fields
    assert any(f.field_name == "priority_date" for f in flagged)


def test_fallback_on_primary_failure():
    from groq import APITimeoutError
    from extractor.groq_engine import extract_document

    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            m = MagicMock()
            m.chat.completions.create.side_effect = APITimeoutError.__new__(APITimeoutError)
            return m
        return _make_mock(MOCK_RESPONSE)

    with patch("extractor.groq_engine.Groq", side_effect=side_effect):
        result = extract_document("text")
    assert result.used_fallback


def test_json_parse_strips_markdown():
    from extractor.groq_engine import _parse_response
    clean = json.dumps(MOCK_RESPONSE)
    result = _parse_response(clean, "test-model")
    assert result.success


def test_confidence_normalized_to_01():
    from extractor.groq_engine import _parse_response
    result = _parse_response(json.dumps(MOCK_RESPONSE), "test")
    for f in result.fields:
        assert 0.0 <= f.confidence <= 1.0


def test_invalid_json_returns_failure():
    from extractor.groq_engine import _parse_response
    result = _parse_response("not json at all {{{", "test")
    assert not result.success
    assert "json" in result.error

from extractor.groq_engine import extract_fields_chunked
from parser.extractor import extract_text_chunked

def test_extract_text_chunked_overlap():
    # Simulate a 10,000 char document
    # With MAX_CHARS=8000 and OVERLAP=200, we expect 2 chunks
    dummy_text = "A" * 10000
    # Monkeypatch _extract_raw for the test
    import parser.extractor as ext
    ext._extract_raw = lambda path: (dummy_text, 5)
    
    chunks, pages = extract_text_chunked("dummy.pdf")
    
    assert len(chunks) == 2
    assert len(chunks[0]) == 8000
    assert len(chunks[1]) == 2200  # 10000 - 8000 + 200 overlap
    assert pages == 5

def test_extract_fields_chunked_merges_data(mocker):
    # Mock the API call to simulate finding data on page 2
    mock_responses = [
        '{"petitioner_name": null, "job_title": null}',  # Chunk 1: nothing
        '{"petitioner_name": "Acme Corp", "job_title": "Engineer"}'  # Chunk 2: found
    ]
    mocker.patch("extractor.groq_engine._execute_groq_call", side_effect=[(r, False) for r in mock_responses])
    
    result = extract_fields_chunked(["chunk1", "chunk2"], "i129")
    
    assert result.get("petitioner_name") == "Acme Corp"
    assert result.get("job_title") == "Engineer"