"""Red/green TDD suite for the stdlib web UI.

Run: pytest tests/test_webapp.py
"""
import sys
import threading
import urllib.request
import uuid
from http.server import HTTPServer
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

import app  # noqa: E402


def test_parse_multipart_extracts_file_field():
    boundary = "----testboundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="proposal"; filename="p.md"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
        "# Excellence\nNovel ambitious objectives.\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    fields = app.parse_multipart(body, f"multipart/form-data; boundary={boundary}")
    assert "proposal" in fields
    assert fields["proposal"]["filename"] == "p.md"
    assert b"Novel ambitious objectives." in fields["proposal"]["data"]


def test_render_html_contains_grade_and_sections():
    from reviewers import load_rules
    from msca_reviewer import run_panel

    rules = load_rules()
    demo = (SKILL_DIR / "examples" / "demo_proposal.md").read_text(encoding="utf-8")
    result = run_panel(demo, rules)
    htmldoc = app.render_html(result, "demo.md")
    assert "<html" in htmldoc.lower()
    assert "%" in htmldoc
    assert "MSCA" in htmldoc
    # the weighted criteria should be surfaced
    assert "Excellence" in htmldoc and "Impact" in htmldoc and "Implementation" in htmldoc


@pytest.fixture()
def live_server():
    server = HTTPServer(("127.0.0.1", 0), app.make_handler())
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_get_root_serves_upload_form(live_server):
    html = urllib.request.urlopen(live_server + "/").read().decode("utf-8")
    assert "<form" in html.lower()
    assert 'type="file"' in html.lower()
    assert "msca" in html.lower()


def test_post_proposal_returns_graded_report(live_server):
    boundary = "----" + uuid.uuid4().hex
    proposal = (SKILL_DIR / "examples" / "demo_proposal.md").read_text(encoding="utf-8")
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="proposal"; filename="demo.md"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
        f"{proposal}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        live_server + "/review",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    resp = urllib.request.urlopen(req)
    assert resp.status == 200
    html = resp.read().decode("utf-8")
    assert "%" in html
    assert "Overall grade" in html
