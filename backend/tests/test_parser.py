"""Parser extraction tests — pdfplumber and PyMuPDF paths fully mocked."""

from __future__ import annotations

import os
import sys
from typing import Any

# Ensure backend root is in the system path for execution resolution
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from parser.extractor import extract_text, extract_text_chunked  # noqa: E402


def test_extract_text_returns_truncated_at_max_chars(monkeypatch: Any) -> None:
    """Legacy extract_text caps output at MAX_CHARS=8000."""
    import parser.extractor as ext

    dummy_text = "X" * 15000
    monkeypatch.setattr(ext, "_extract_raw", lambda path: (dummy_text, 3))

    result = extract_text("dummy.pdf")

    assert result.success is True
    assert len(result.text) == 8000
    assert result.page_count == 3


def test_extract_text_empty_pdf_returns_success_empty(monkeypatch: Any) -> None:
    """Empty PDF (no extractable text) returns success=True with empty text."""
    import parser.extractor as ext

    monkeypatch.setattr(ext, "_extract_raw", lambda path: ("", 1))

    result = extract_text("dummy.pdf")

    assert result.success is True
    assert result.text == ""


def test_extract_text_chunked_two_chunks(monkeypatch: Any) -> None:
    """25,000 chars at CHUNK_SIZE=20,000 OVERLAP=500 produces exactly 2 chunks."""
    import parser.extractor as ext

    dummy_text = "A" * 25000
    monkeypatch.setattr(ext, "_extract_raw", lambda path: (dummy_text, 5))

    chunks, pages = extract_text_chunked("dummy.pdf")

    assert len(chunks) == 2
    assert len(chunks[0]) == 20000
    assert len(chunks[1]) == 5500
    assert pages == 5


def test_extract_text_chunked_single_chunk(monkeypatch: Any) -> None:
    """Document shorter than CHUNK_SIZE produces exactly 1 chunk."""
    import parser.extractor as ext

    dummy_text = "B" * 5000
    monkeypatch.setattr(ext, "_extract_raw", lambda path: (dummy_text, 2))

    chunks, pages = extract_text_chunked("dummy.pdf")

    assert len(chunks) == 1
    assert len(chunks[0]) == 5000
    assert pages == 2


def test_extract_text_chunked_empty_returns_empty_list(monkeypatch: Any) -> None:
    """Empty extraction returns empty chunk list, not a crash."""
    import parser.extractor as ext

    monkeypatch.setattr(ext, "_extract_raw", lambda path: ("", 0))

    chunks, pages = extract_text_chunked("dummy.pdf")

    assert chunks == []
    assert pages == 0
