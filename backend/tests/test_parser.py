"""Parser tests — file I/O fully mocked."""
import os
import sys
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_file_not_found():
    from parser.extractor import extract_text
    result = extract_text("/nonexistent/path/file.pdf")
    assert not result.success
    assert "not found" in result.error.lower()


def test_pdfplumber_success():
    from parser.extractor import extract_text

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Applicant: Arjun Sharma\nVisa: H-1B\n" * 20
    mock_page.extract_tables.return_value = []
    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page, mock_page]

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 minimal")
        path = f.name
    try:
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = extract_text(path)
        assert result.success
        assert result.page_count == 2
        assert "Arjun Sharma" in result.text
        assert result.method == "pdfplumber"
    finally:
        os.unlink(path)


def test_pymupdf_fallback():
    from parser.extractor import extract_text

    mock_page = MagicMock()
    mock_page.get_text.return_value = "Passport No: J8821045"
    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
    mock_doc.close = MagicMock()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4")
        path = f.name
    try:
        import unittest.mock as _um
        with patch("pdfplumber.open", side_effect=Exception("corrupt")):
            mock_fitz_mod = _um.MagicMock()
            mock_fitz_mod.open.return_value = mock_doc
            with patch.dict("sys.modules", {"fitz": mock_fitz_mod}):
                result = extract_text(path)
        assert result.method == "pymupdf"
        assert result.success
    finally:
        os.unlink(path)


def test_truncation():
    from parser.extractor import MAX_CHARS
    from parser.extractor import extract_text

    big_text = "x" * (MAX_CHARS + 5000)
    mock_page = MagicMock()
    mock_page.extract_text.return_value = big_text
    mock_page.extract_tables.return_value = []
    mock_pdf = MagicMock()
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = [mock_page]

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF")
        path = f.name
    try:
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = extract_text(path)
        assert result.truncated
        assert len(result.text) <= MAX_CHARS
    finally:
        os.unlink(path)
