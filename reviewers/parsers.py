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

_TEXT_EXTS = {".md", ".markdown", ".txt", ".text", ".rst", ""}


def read_proposal(path: Path | str) -> str:
    """Read a proposal file of any supported type and return its text."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".docx":
        return parse_docx(path)
    if ext == ".pdf":
        return parse_pdf(path)
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


def parse_pdf(path: Path | str) -> str:
    """Extract text from a PDF using whichever backend is installed."""
    path = Path(path)
    reader = _import_pdf_reader()
    if reader is not None:
        return reader(str(path)).strip()

    raise RuntimeError(
        "Reading PDF proposals needs a PDF engine. Install one with:\n"
        "    pip install pypdf\n"
        "(or 'pip install pdfminer.six'). Alternatively, save the proposal as "
        ".docx, .txt or .md and re-upload."
    )
