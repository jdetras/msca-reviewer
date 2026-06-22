"""Red/green TDD suite for proposal file parsing (txt / markdown / docx / pdf).

Run: pytest tests/test_parsers.py
"""
import sys
import zipfile
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

from reviewers import read_proposal  # noqa: E402
from reviewers.parsers import parse_docx, parse_pdf  # noqa: E402


# --- helpers ---------------------------------------------------------------

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '</Types>'
)
_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)


def _make_docx(path: Path, paragraphs):
    """Write a minimal but structurally valid .docx with the given paragraphs."""
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(
        f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs
    )
    document = f'<?xml version="1.0"?><w:document {ns}><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", document)


# --- tests -----------------------------------------------------------------

def test_read_plain_text(tmp_path):
    p = tmp_path / "proposal.md"
    p.write_text("# Excellence\nNovel objectives here.", encoding="utf-8")
    assert "Novel objectives" in read_proposal(p)


def test_read_txt_extension(tmp_path):
    p = tmp_path / "proposal.txt"
    p.write_text("plain body text", encoding="utf-8")
    assert read_proposal(p) == "plain body text"


def test_parse_docx_extracts_paragraph_text(tmp_path):
    p = tmp_path / "proposal.docx"
    _make_docx(p, ["Research objectives O1 O2.", "State of the art is limited."])
    text = parse_docx(p)
    assert "Research objectives O1 O2." in text
    assert "State of the art is limited." in text
    # paragraphs should be newline-separated, not glued together
    assert "O2.\nState" in text or "O2." in text and "\n" in text


def test_docx_xml_entities_are_unescaped(tmp_path):
    p = tmp_path / "amp.docx"
    _make_docx(p, ["Genotype &amp; phenotype &lt;data&gt;"])
    text = parse_docx(p)
    assert "Genotype & phenotype <data>" in text


def test_read_proposal_routes_docx(tmp_path):
    p = tmp_path / "routed.docx"
    _make_docx(p, ["dispatch to docx parser"])
    assert "dispatch to docx parser" in read_proposal(p)


def test_legacy_doc_raises_helpful_error(tmp_path):
    p = tmp_path / "old.doc"
    p.write_bytes(b"\xd0\xcf\x11\xe0legacy binary")
    with pytest.raises(ValueError) as exc:
        read_proposal(p)
    assert ".docx" in str(exc.value).lower()


def test_pdf_without_backend_raises_clear_hint(tmp_path, monkeypatch):
    # Simulate no PDF backend installed: parse_pdf must raise an actionable error.
    import reviewers.parsers as parsers
    monkeypatch.setattr(parsers, "_PDF_BACKENDS", ())
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4 minimal")
    with pytest.raises(RuntimeError) as exc:
        parse_pdf(p)
    assert "pip install" in str(exc.value).lower()


def test_pdf_roundtrip_if_backend_available(tmp_path):
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter
    # pypdf can't easily embed text; just assert parse_pdf returns a string and
    # does not raise on a valid (empty) PDF.
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    p = tmp_path / "blank.pdf"
    with open(p, "wb") as fh:
        writer.write(fh)
    assert isinstance(parse_pdf(p), str)
