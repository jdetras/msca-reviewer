"""Proposal file readers: plain text / markdown / DOCX / PDF.

The reviewer panel scores *text*, so this module's only job is to turn an
uploaded proposal file into a clean string.

Design choices (deliberate, see Gotchas in SKILL.md):
* **DOCX** is read with the standard library only — a ``.docx`` is a ZIP of XML,
  so we never need ``python-docx`` installed.
* **PDF** needs a real PDF engine; we use ``pypdf`` or ``pdfminer.six`` *if
  installed* and otherwise raise an actionable error rather than guessing.
* Legacy binary ``.doc`` is not supported (different format) — we say so clearly.
"""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

# PDF backends are probed lazily in parse_pdf(); this tuple lets tests simulate
# "no backend installed" by monkeypatching it to ().
_PDF_BACKENDS = ("pypdf", "PyPDF2", "pdfminer")

# Below this many characters of extracted text, a PDF is treated as scanned/
# image-only and OCR is attempted (in ocr="auto" mode).
MIN_PDF_TEXT_CHARS = 25

_TEXT_EXTS = {".md", ".markdown", ".txt", ".text", ".rst", ""}


class OCRUnavailable(RuntimeError):
    """Raised when OCR is requested but the OCR toolchain is not available."""


def read_proposal(path: Path | str, ocr: str = "auto") -> str:
    """Read a proposal file of any supported type and return its text.

    ``ocr`` controls scanned-PDF handling: ``"auto"`` (OCR only when a PDF has no
    selectable text), ``"always"``, or ``"never"``.
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".docx":
        return parse_docx(path)
    if ext == ".pdf":
        return parse_pdf(path, ocr=ocr)
    if ext == ".doc":
        raise ValueError(
            f"Legacy Microsoft Word '.doc' is not supported ({path.name}). "
            "Open it in Word/LibreOffice and 'Save As' .docx (or export to PDF), "
            "then re-upload."
        )
    if ext in _TEXT_EXTS:
        return path.read_text(encoding="utf-8", errors="ignore")
    # Unknown extension: best-effort treat as UTF-8 text.
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_docx(path: Path | str) -> str:
    """Extract visible text from a .docx using only the standard library."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except KeyError as exc:  # not a Word document zip
        raise ValueError(
            f"{path.name} is not a valid .docx (missing word/document.xml)."
        ) from exc
    except zipfile.BadZipFile as exc:
        raise ValueError(
            f"{path.name} is not a valid .docx file (corrupt or wrong format)."
        ) from exc

    # Tabs and line breaks become whitespace.
    xml = re.sub(r"<w:tab\b[^>]*/>", "\t", xml)
    xml = re.sub(r"<w:br\b[^>]*/>", "\n", xml)

    lines = []
    # Each <w:p> is a paragraph; join its <w:t> runs, then newline-separate paras.
    for para in re.split(r"</w:p>", xml):
        runs = re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", para, flags=re.DOTALL)
        if runs:
            lines.append("".join(runs))
    text = "\n".join(lines)
    return html.unescape(text).strip()


def _import_pdf_reader():
    """Return a callable ``reader(path) -> text`` from the first usable backend.

    Importing an optional backend can fail with more than ImportError (a broken
    or partial install may raise other errors), so probing is deliberately broad
    — we just move on to the next backend. Returns None if none are usable.
    """
    if "pypdf" in _PDF_BACKENDS:
        try:
            from pypdf import PdfReader  # type: ignore

            return lambda p: "\n".join((pg.extract_text() or "") for pg in PdfReader(p).pages)
        except Exception:  # noqa: BLE001 - backend missing/broken; try the next one
            pass
    if "PyPDF2" in _PDF_BACKENDS:
        try:
            from PyPDF2 import PdfReader  # type: ignore

            return lambda p: "\n".join((pg.extract_text() or "") for pg in PdfReader(p).pages)
        except Exception:  # noqa: BLE001
            pass
    if "pdfminer" in _PDF_BACKENDS:
        try:
            from pdfminer.high_level import extract_text  # type: ignore

            return lambda p: (extract_text(p) or "")
        except Exception:  # noqa: BLE001
            pass
    return None


def _needs_ocr(text: str) -> bool:
    """True when extracted text is too sparse to be a real (born-digital) PDF."""
    return len((text or "").strip()) < MIN_PDF_TEXT_CHARS


def _ocr_pdf(path: Path | str) -> str:
    """OCR a (scanned/image) PDF: render each page to an image and read the text.

    Needs the optional ``pdf2image`` + ``pytesseract`` Python packages and the
    ``poppler`` and ``tesseract`` system binaries. Raises :class:`OCRUnavailable`
    if any of those are missing so callers can degrade gracefully.
    """
    try:
        import pytesseract  # type: ignore
        from pdf2image import convert_from_path  # type: ignore
    except Exception as exc:  # noqa: BLE001 - any import failure means "no OCR"
        raise OCRUnavailable(
            "OCR for scanned PDFs needs the 'pdf2image' and 'pytesseract' Python "
            "packages (pip install pdf2image pytesseract) plus the system 'poppler' "
            "and 'tesseract-ocr' binaries."
        ) from exc

    try:
        images = convert_from_path(str(path))
    except Exception as exc:  # noqa: BLE001 - usually missing poppler
        raise OCRUnavailable(
            "OCR could not rasterise the PDF — the 'poppler' system package "
            "(poppler-utils) is required for pdf2image."
        ) from exc

    try:
        pages = [pytesseract.image_to_string(img) for img in images]
    except Exception as exc:  # noqa: BLE001 - usually missing tesseract binary
        raise OCRUnavailable(
            "OCR failed — the 'tesseract-ocr' system binary is required for "
            "pytesseract."
        ) from exc
    return "\n".join(pages).strip()


def parse_pdf(path: Path | str, ocr: str = "auto") -> str:
    """Extract text from a PDF, falling back to OCR for scanned/image PDFs.

    ``ocr``:
    * ``"auto"`` (default) — use embedded text; OCR only if there is little/none.
    * ``"always"`` — OCR every page regardless of embedded text.
    * ``"never"`` — embedded text only; never OCR.
    """
    path = Path(path)
    reader = _import_pdf_reader()
    text = reader(str(path)).strip() if reader is not None else ""

    if ocr == "always":
        return _ocr_pdf(path)

    if ocr == "never":
        if reader is None:
            raise RuntimeError(_PDF_ENGINE_HINT)
        return text

    # ocr == "auto"
    if text and not _needs_ocr(text):
        return text

    # Little or no embedded text → try OCR, degrade gracefully if unavailable.
    try:
        ocr_text = _ocr_pdf(path)
    except OCRUnavailable as exc:
        if text:
            return text  # return what little we have rather than failing outright
        if reader is None:
            raise RuntimeError(_PDF_ENGINE_HINT) from exc
        # A text engine exists but found nothing and OCR is unavailable: the PDF
        # is almost certainly scanned. Tell the user how to enable OCR.
        raise RuntimeError(
            "This PDF appears to be scanned/image-only (no selectable text) and "
            "OCR is not available. " + str(exc) + " Or re-upload a .docx/.txt copy."
        ) from exc
    return ocr_text if ocr_text.strip() else text


_PDF_ENGINE_HINT = (
    "Reading PDF proposals needs a PDF engine. Install one with:\n"
    "    pip install pypdf\n"
    "(or 'pip install pdfminer.six'). For scanned/image PDFs also install OCR: "
    "'pip install pdf2image pytesseract' plus the poppler and tesseract-ocr system "
    "binaries. Alternatively, save the proposal as .docx, .txt or .md and re-upload."
)
