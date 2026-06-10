from __future__ import annotations

import gc
import logging
from dataclasses import dataclass

import fitz  # PyMuPDF
import pdfplumber

logger = logging.getLogger("docverify.parser")
MAX_CHARS = 8000
CHUNK_SIZE = 20_000
OVERLAP = 500

@dataclass
class ParseResult:
    success: bool
    text: str = ""
    error: str = ""
    page_count: int = 0


def extract_text(pdf_path: str) -> ParseResult:
    """Legacy full-text extraction — keeping for backward compatibility."""
    try:
        text, page_count = _extract_raw(pdf_path)
        return ParseResult(success=True, text=text[:MAX_CHARS], page_count=page_count)
    except Exception as exc:
        return ParseResult(success=False, error=str(exc))


def extract_text_chunked(pdf_path: str) -> tuple[list[str], int]:
    """
    Production-grade parser. Extracts text without OOMing and splits into
    MAX_CHARS chunks with an OVERLAP to ensure boundary fields are not missed.
    Returns (chunks, page_count).
    """
    try:
        full_text, page_count = _extract_raw(pdf_path)
        chunks = []

        if not full_text:
            return chunks, page_count

        start = 0
        text_length = len(full_text)

        while start < text_length:
            end = min(start + CHUNK_SIZE, text_length)
            chunks.append(full_text[start:end])
            if end == text_length:
                break
            # Step back by OVERLAP for the next chunk
            start = end - OVERLAP

        return chunks, page_count
    except Exception as exc:
        logger.error("Failed chunked extraction: %s", str(exc))
        return [], 0


def _extract_raw(pdf_path: str) -> tuple[str, int]:
    """Helper to handle the pdfplumber -> PyMuPDF fallback logic safely."""
    text = ""
    page_count = 0

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            text = "\n".join(pages_text)
    except Exception as e:
        logger.warning("pdfplumber failed: %s", str(e))

    if len(text.strip()) < 100:
        logger.info("Falling back to PyMuPDF...")
        try:
            with fitz.open(pdf_path) as doc:
                page_count = len(doc)
                text = "\n".join([page.get_text() for page in doc])
        except Exception as e:
            logger.error("PyMuPDF fallback failed: %s", str(e))

    # Critical: force garbage collection due to Render 512MB RAM constraints
    gc.collect()
    return text, page_count
