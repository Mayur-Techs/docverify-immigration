from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    import fitz  # pymupdf
except ImportError:
    fitz = None

logger = logging.getLogger("docverify.parser")
MAX_CHARS = 12_000


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
        with pdfplumber.open(str(path)) as pdf:
            count = len(pdf.pages)
            for page in pdf.pages:
                t = page.extract_text() or ""
                for table in (page.extract_tables() or []):
                    for row in table:
                        t += "\n" + " | ".join(str(c) for c in row if c)
                pages_text.append(t)
        full = "\n\n--- PAGE BREAK ---\n\n".join(pages_text)
        raw = len(full)
        return ParseResult(success=True, text=full[:MAX_CHARS], page_count=count,
                           raw_length=raw, truncated=raw > MAX_CHARS, method="pdfplumber")
    except Exception as e:
        return ParseResult(success=False, error=str(e), method="pdfplumber")


def _try_pymupdf(path: Path) -> ParseResult:
    try:
        if fitz is None:
            return ParseResult(success=False, error="pymupdf not installed", method="pymupdf")
        doc = fitz.open(str(path))
        pages = [p.get_text("text") for p in doc]
        doc.close()
        full = "\n\n--- PAGE BREAK ---\n\n".join(pages)
        raw = len(full)
        return ParseResult(success=True, text=full[:MAX_CHARS], page_count=len(pages),
                           raw_length=raw, truncated=raw > MAX_CHARS, method="pymupdf")
    except Exception as e:
        return ParseResult(success=False, error=str(e), method="pymupdf")
