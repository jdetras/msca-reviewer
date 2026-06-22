"""Red/green TDD suite for OCR fallback on scanned/image PDFs.

The real OCR backends (pytesseract + pdf2image + system tesseract/poppler) are
not installed in CI/sandbox, so the decision logic is tested via monkeypatched
seams, and the genuine "OCR unavailable" path is asserted directly.

Run: pytest tests/test_ocr.py
"""
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

import reviewers.parsers as parsers  # noqa: E402
from reviewers.parsers import parse_pdf, OCRUnavailable, _needs_ocr  # noqa: E402


def test_needs_ocr_true_for_empty_or_tiny():
    assert _needs_ocr("")
    assert _needs_ocr("   \n\t ")
    assert _needs_ocr("Fig.1")  # a few stray chars from a scan


def test_needs_ocr_false_for_real_text():
    assert not _needs_ocr("This is a proper paragraph of extracted proposal text. " * 3)


def test_auto_uses_ocr_when_no_embedded_text(tmp_path, monkeypatch):
    p = tmp_path / "scan.pdf"
    p.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(parsers, "_import_pdf_reader", lambda: (lambda _p: ""))
    monkeypatch.setattr(parsers, "_ocr_pdf", lambda _p: "OCR RECOVERED TEXT")
    assert parse_pdf(p) == "OCR RECOVERED TEXT"


def test_auto_skips_ocr_when_text_present(tmp_path, monkeypatch):
    p = tmp_path / "born_digital.pdf"
    p.write_bytes(b"%PDF-1.4")
    good = "A fully digital proposal with plenty of selectable text. " * 3
    monkeypatch.setattr(parsers, "_import_pdf_reader", lambda: (lambda _p: good))

    def _boom(_p):
        raise AssertionError("OCR must not run when the PDF already has text")

    monkeypatch.setattr(parsers, "_ocr_pdf", _boom)
    assert parse_pdf(p).startswith("A fully digital proposal")


def test_ocr_always_forces_ocr_even_with_text(tmp_path, monkeypatch):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(parsers, "_import_pdf_reader", lambda: (lambda _p: "embedded text here"))
    monkeypatch.setattr(parsers, "_ocr_pdf", lambda _p: "FORCED OCR")
    assert parse_pdf(p, ocr="always") == "FORCED OCR"


def test_real_ocr_backend_absent_raises_ocr_unavailable(tmp_path):
    # pytesseract/pdf2image are not installed here → _ocr_pdf signals unavailability.
    with pytest.raises(OCRUnavailable):
        parsers._ocr_pdf(str(tmp_path / "missing.pdf"))


def test_no_text_engine_and_no_ocr_raises_actionable_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(parsers, "_PDF_BACKENDS", ())  # no text engine

    def _no_ocr(_p):
        raise OCRUnavailable("no ocr")

    monkeypatch.setattr(parsers, "_ocr_pdf", _no_ocr)
    p = tmp_path / "scan_only.pdf"
    p.write_bytes(b"%PDF-1.4")
    with pytest.raises(RuntimeError) as exc:
        parse_pdf(p)
    msg = str(exc.value).lower()
    assert "pip install" in msg
