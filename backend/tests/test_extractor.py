"""Groq extraction engine and chunked parser test suite."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from groq import APITimeoutError

# Ensure backend root is in the system path for execution resolution
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from extractor.groq_engine import (
    _execute_groq_call,
    _is_null_value,
    extract_fields_chunked,
)
from parser.extractor import extract_text, extract_text_chunked

# ── Mock Payloads ─────────────────────────────────────────────────────────────

MOCK_CHUNK_1 = {
    "petitioner_name": "Acme Systems Corp",
    "petitioner_fein": "12-3456789",
    "job_title": "Not Found",
    "annual_wage": None,
}

MOCK_CHUNK_2 = {
    "petitioner_name": "null",
    "petitioner_fein": "unknown",
    "job_title": "Lead Software Engineer",
    "annual_wage": "115000",
}


# ── Parser Tests ──────────────────────────────────────────────────────────────

def test_extract_text_legacy_truncation() -> None:
    """Verify legacy extraction caps output at MAX_CHARS to preserve memory bounds."""
    import parser.extractor as ext
    
    dummy_text = "B" * 15000
    original_raw = ext._extract_raw
    ext._extract_raw = lambda path: (dummy_text, 2)
    
    try:
        result = extract_text("dummy.pdf")
        assert result.success
        assert len(result.text) == 8000
        assert result.page_count == 2
    finally:
        ext._extract_raw = original_raw


def test_extract_text_chunked_overlap() -> None:
    """Verify parsing splits large strings into overlapping 20k chunk envelopes."""
    import parser.extractor as ext

    # 25,000 characters forces exactly two chunks under CHUNK_SIZE=20000, OVERLAP=500
    dummy_text = "A" * 25000
    original_raw = ext._extract_raw
    ext._extract_raw = lambda path: (dummy_text, 5)
    
    try:
        chunks, pages = extract_text_chunked("dummy.pdf")
        assert len(chunks) == 2
        assert len(chunks[0]) == 20000
        assert len(chunks[1]) == 5500
        assert pages == 5
    finally:
        ext._extract_raw = original_raw


# ── Extraction Engine Tests ───────────────────────────────────────────────────

def test_is_null_value_variants() -> None:
    """Verify case-insensitive matching filters out messy LLM empty tokens."""
    assert _is_null_value(None)
    assert _is_null_value("")
    assert _is_null_value("None")
    assert _is_null_value("null")
    assert _is_null_value("Not Found")
    assert _is_null_value("N/A ")
    assert _is_null_value("unKNOWN")
    assert not _is_null_value("Valid Extracted String")


def test_extract_fields_chunked_merges_data(mocker: Any) -> None:
    """Verify first-non-null data aggregation behaves correctly across chunk iterations."""
    mock_responses = [json.dumps(MOCK_CHUNK_1), json.dumps(MOCK_CHUNK_2)]
    mocker.patch(
        "extractor.groq_engine._execute_groq_call",
        side_effect=[(r, False) for r in mock_responses],
    )
    
    result = extract_fields_chunked(["chunk1", "chunk2"], "i129")
    
    assert result.get("petitioner_name") == "Acme Systems Corp"
    assert result.get("petitioner_fein") == "12-3456789"
    assert result.get("job_title") == "Lead Software Engineer"
    assert result.get("annual_wage") == "115000"


def test_execute_groq_call_fallback(mocker: Any) -> None:
    """Verify failure cascade triggers fallback inference model sequentially."""
    mocker.patch(
        "extractor.groq_engine._make_api_call",
        side_effect=[APITimeoutError("Primary model timed out"), '{"extracted": "data"}'],
    )
    
    raw_resp, used_fallback = _execute_groq_call("Extract something")
    
    assert used_fallback is True
    assert raw_resp == '{"extracted": "data"}'


def test_execute_groq_call_strips_markdown(mocker: Any) -> None:
    """Verify raw markdown block fences are stripped out defensively post-inference."""
    markdown_payload = "```json\n{\"petitioner_name\": \"Acme Corp\"}\n```"
    mocker.patch(
        "extractor.groq_engine._make_api_call",
        return_value=markdown_payload,
    )

    raw_resp, used_fallback = _execute_groq_call("Extract something")

    assert used_fallback is False
    assert raw_resp == '{"petitioner_name": "Acme Corp"}'