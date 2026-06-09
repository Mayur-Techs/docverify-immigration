from __future__ import annotations
import gc
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("docverify.parser")
MAX_CHARS = 8_000  # reduced from 12k — saves ~50MB per request


@dataclass
class ParseResult:
    success: bool
    text: str = ""
    page_count: int = 0
    raw_length: int = 0
    truncated: bool = False
    method: str = ""
    error: str = ""


def extract_text(file_path: str) -> ParseResult:
    path = Path(file_path)
    if not path.exists():
        return ParseResult(success=False, error=f"File not found: {file_path}")
    result = _try_pdfplumber(path)
    if result.success and len(result.text.strip()) > 100:
        return result
    logger.warning("pdfplumber sparse, trying pymupdf: %s", path.name)
    fallback = _try_pymupdf(path)
    return fallback if (fallback.success and len(fallback.text) > len(result.text)) else result


def _try_pdfplumber(path: Path) -> ParseResult:
    try:
        import pdfplumber
        pages_text = []
        chars_so_far = 0
        with pdfplumber.open(str(path)) as pdf:
            count = len(pdf.pages)
            for page in pdf.pages:
                if chars_so_far >= MAX_CHARS:
                    break
                t = page.extract_text() or ""
                # Skip table extraction on large docs to save memory
                if chars_so_far + len(t) < MAX_CHARS - 1000:
                    for table in (page.extract_tables() or []):
                        for row in table:
                            t += "\n" + " | ".join(str(c) for c in row if c)
                pages_text.append(t)
                chars_so_far += len(t)
        full = "\n\n--- PAGE BREAK ---\n\n".join(pages_text)
        raw = len(full)
        result = ParseResult(
            success=True, text=full[:MAX_CHARS], page_count=count,
            raw_length=raw, truncated=raw > MAX_CHARS, method="pdfplumber",
        )
        del pages_text, full
        gc.collect()
        return result
    except Exception as e:
        gc.collect()
        return ParseResult(success=False, error=str(e), method="pdfplumber")


def _try_pymupdf(path: Path) -> ParseResult:
    try:
        import fitz  # noqa: PLC0415
        doc = fitz.open(str(path))
        pages = []
        chars_so_far = 0
        for page in doc:
            if chars_so_far >= MAX_CHARS:
                break
            t = page.get_text("text")
            pages.append(t)
            chars_so_far += len(t)
        doc.close()
        del doc
        full = "\n\n--- PAGE BREAK ---\n\n".join(pages)
        raw = len(full)
        result = ParseResult(
            success=True, text=full[:MAX_CHARS], page_count=len(pages),
            raw_length=raw, truncated=raw > MAX_CHARS, method="pymupdf",
        )
        del pages, full
        gc.collect()
        return result
    except Exception as e:
        gc.collect()
        return ParseResult(success=False, error=str(e), method="pymupdf")
