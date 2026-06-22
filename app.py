#!/usr/bin/env python3
"""MSCA Reviewer — local web UI.

A dependency-free web front-end (Python standard library only): upload a
proposal (.md / .txt / .docx / .pdf), the reviewer panel scores it, and the
graded report is rendered in the browser with a download link for the Markdown.

Run:
    python app.py                 # serves http://127.0.0.1:8000
    python app.py --port 9000
    python app.py --host 0.0.0.0  # expose on the LAN (use with care)

ClawBioCrop / MSCA-Reviewer is a research/educational tool. It is NOT the
European Commission, REA, or an evaluation panel; scores are heuristic only.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL_DIR))

from reviewers import load_rules, read_proposal  # noqa: E402
from msca_reviewer import run_panel, render_report  # noqa: E402

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB safety cap

# --------------------------------------------------------------------------- #
# multipart/form-data parsing (stdlib `cgi` is removed in Py 3.13, so do it here)
# --------------------------------------------------------------------------- #


def parse_multipart(body: bytes, content_type: str) -> dict:
    """Parse a multipart/form-data body into {name: {filename, data}}."""
    m = re.search(r"boundary=([^;]+)", content_type)
    if not m:
        return {}
    boundary = m.group(1).strip().strip('"')
    delim = b"--" + boundary.encode("utf-8")
    fields: dict = {}
    for part in body.split(delim):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if b"\r\n\r\n" not in part:
            continue
        raw_head, data = part.split(b"\r\n\r\n", 1)
        head = raw_head.decode("utf-8", "ignore")
        name_m = re.search(r'name="([^"]*)"', head)
        if not name_m:
            continue
        file_m = re.search(r'filename="([^"]*)"', head)
        fields[name_m.group(1)] = {
            "filename": file_m.group(1) if file_m else None,
            "data": data.rstrip(b"\r\n"),
        }
    return fields


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #

_PAGE_CSS = """
:root{--bg:#0f1117;--card:#1a1d27;--ink:#e8eaf0;--muted:#9aa3b2;--accent:#6ea8fe;
--good:#3fb950;--warn:#d29922;--bad:#f85149;--line:#2a2e3a}
*{box-sizing:border-box}body{margin:0;font:16px/1.55 -apple-system,Segoe UI,Roboto,
Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink)}
.wrap{max-width:920px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:1.7rem;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:24px;margin:18px 0}
a{color:var(--accent)}label{font-weight:600}
input[type=file]{display:block;margin:14px 0;color:var(--ink)}
button{background:var(--accent);color:#0b0d12;border:0;border-radius:9px;
padding:11px 20px;font-weight:700;font-size:1rem;cursor:pointer}
button:hover{filter:brightness(1.08)}
.grade{font-size:3.4rem;font-weight:800;margin:6px 0}
.bar{height:14px;border-radius:8px;background:#2a2e3a;overflow:hidden;margin:10px 0 4px}
.bar>span{display:block;height:100%;background:linear-gradient(90deg,#f85149,#d29922,#3fb950)}
table{width:100%;border-collapse:collapse;margin:10px 0}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.8rem;font-weight:700}
.ok{background:rgba(63,185,80,.15);color:var(--good)}
.no{background:rgba(248,81,73,.15);color:var(--bad)}
.warnrow{color:var(--warn)}.muted{color:var(--muted)}
ol,ul{margin:8px 0 8px 22px}code{background:#11141c;padding:1px 6px;border-radius:6px}
.foot{color:var(--muted);font-size:.85rem;margin-top:30px;border-top:1px solid var(--line);padding-top:16px}
"""

_UPLOAD_FORM = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MSCA Reviewer Panel</title><style>{css}</style></head><body><div class="wrap">
<h1>🎓 MSCA Postdoctoral Fellowship — Reviewer Panel</h1>
<p class="sub">Upload your proposal and a panel of reviewer agents (Excellence 50% ·
Impact 30% · Implementation 20% · Compliance) will score it, give a weighted
percentage grade, and tell you what to improve.</p>
<div class="card">
<form action="/review" method="post" enctype="multipart/form-data">
<label for="f">Proposal file (.md, .txt, .docx, or .pdf)</label>
<input id="f" type="file" name="proposal" accept=".md,.markdown,.txt,.docx,.pdf" required>
<button type="submit">Review my proposal →</button>
</form></div>
<p class="muted">Nothing leaves your machine — the server runs locally. PDF upload
needs <code>pip install pypdf</code>; .docx, .md and .txt work out of the box.</p>
<div class="foot">{disclaimer}</div>
</div></body></html>"""


def upload_page() -> str:
    rules = load_rules()
    return _UPLOAD_FORM.format(css=_PAGE_CSS, disclaimer=html.escape(rules["disclaimer"]))


def _esc(x) -> str:
    return html.escape(str(x))


def render_html(result: dict, source: str) -> str:
    pct = result["percentage"]
    L = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         "<title>MSCA review — {:.1f}%</title>".format(pct),
         f"<style>{_PAGE_CSS}</style></head><body><div class='wrap'>"]
    L.append("<h1>🎓 MSCA Reviewer Panel — Report</h1>")
    L.append(f"<p class='sub'>Source: <code>{_esc(source)}</code> · "
             f"~{result['word_count']} words "
             f"(~{result['compliance']['page_estimate']} A4 pages)</p>")

    # Overall grade
    thr_ok = "ok" if result["threshold_met"] else "no"
    comp_ok = "ok" if result["competitive"] else "no"
    L.append("<div class='card'><h2>Overall grade</h2>")
    L.append(f"<div class='grade'>{pct:.1f}%</div>")
    L.append(f"<div class='bar'><span style='width:{min(100,pct):.0f}%'></span></div>")
    L.append(f"<p><strong>{_esc(result['label'])}</strong> — {_esc(result['note'])}</p>")
    L.append(f"<p><span class='pill {thr_ok}'>Threshold {result['threshold_pct']}% "
             f"{'met' if result['threshold_met'] else 'NOT met'}</span> "
             f"<span class='pill {comp_ok}'>Competitive target "
             f"{result['competitive_target_pct']}% "
             f"{'reached' if result['competitive'] else 'below'}</span></p></div>")

    # Weighted breakdown
    L.append("<div class='card'><h2>Weighted breakdown</h2><table>")
    L.append("<tr><th>Criterion</th><th>Weight</th><th>Score /5</th><th>Weighted pts</th></tr>")
    for b in result["breakdown"]:
        L.append(f"<tr><td>{_esc(b['criterion_name'])}</td><td>{b['weight_pct']:.0f}%</td>"
                 f"<td>{b['score']:.2f}</td><td>{b['weighted_points']:.1f}</td></tr>")
    L.append(f"<tr><td><strong>Total</strong></td><td></td><td></td>"
             f"<td><strong>{pct:.1f}</strong></td></tr></table></div>")

    # Reviewer scorecards
    L.append("<div class='card'><h2>Reviewer scorecards</h2>")
    for r in result["panel"]:
        L.append(f"<h3>{_esc(r['persona'])} — {r['score']:.2f}/5</h3>")
        L.append(f"<p class='muted'>{_esc(r['rationale'])}</p><table>")
        L.append("<tr><th>Sub-criterion</th><th>Score</th><th>Coverage</th></tr>")
        for s in r["sub_scores"]:
            L.append(f"<tr><td><strong>{_esc(s['id'])}</strong> {_esc(s['name'])}</td>"
                     f"<td>{s['score']:.2f}/5</td><td>{int(s['coverage']*100)}%</td></tr>")
        L.append("</table>")
    c = result["compliance"]
    L.append(f"<h3>{_esc(c['persona'])}</h3><ul>")
    L.append(f"<li>~{c['page_estimate']} pages vs {c['page_limit']}-page limit "
             "for sections 1–3.</li>")
    if c["missing_sections"]:
        L.append("<li class='warnrow'>Missing/undetected: "
                 + _esc(", ".join(m["name"] for m in c["missing_sections"])) + ".</li>")
    for w in c["warnings"]:
        L.append(f"<li class='warnrow'>⚠️ {_esc(w)}</li>")
    L.append("</ul></div>")

    # Feedback
    fb = result["feedback"]
    L.append("<div class='card'><h2>✍️ What to improve</h2>")
    if fb["top_priorities"]:
        L.append("<h3>Top priorities</h3><ol>")
        for p in fb["top_priorities"]:
            imp = f" <span class='muted'>(≈+{p['weighted_impact']:.1f} pts)</span>" if p["weighted_impact"] else ""
            L.append(f"<li><strong>{_esc(p['criterion'])} → {_esc(p['subcriterion'])}</strong>{imp}: "
                     f"{_esc(p['action'])}</li>")
        L.append("</ol>")
    if fb["missing"]:
        L.append("<h3>Missing / under-evidenced</h3><ul>")
        seen = set()
        for m in fb["missing"]:
            if m["item"] in seen:
                continue
            seen.add(m["item"])
            ctx = f" ({_esc(m.get('subcriterion'))})" if m.get("subcriterion") else ""
            L.append(f"<li>{_esc(m['item'])}{ctx}</li>")
        L.append("</ul>")
    L.append("<h3>Evaluator wisdom</h3><ul>")
    for t in fb["reviewer_tips"]:
        L.append(f"<li>{_esc(t)}</li>")
    L.append("</ul></div>")

    L.append("<p><a href='/'>← Review another proposal</a></p>")
    L.append(f"<div class='foot'>{_esc(result['disclaimer'])}</div>")
    L.append("</div></body></html>")
    return "\n".join(L)


def _error_page(message: str, code: int = 400) -> str:
    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Error</title><style>{_PAGE_CSS}</style></head><body><div class='wrap'>"
            "<h1>⚠️ Could not review that file</h1>"
            f"<div class='card'><p>{html.escape(message)}</p>"
            "<p><a href='/'>← Try again</a></p></div></div></body></html>")


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #


def make_handler():
    rules = load_rules()

    class Handler(BaseHTTPRequestHandler):
        server_version = "MSCAReviewer/1.0"

        def _send(self, body: str, code: int = 200):
            payload = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(upload_page())
            elif self.path == "/health":
                self._send("ok")
            else:
                self._send(_error_page("Not found.", 404), 404)

        def do_POST(self):
            if self.path != "/review":
                self._send(_error_page("Not found.", 404), 404)
                return
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                self._send(_error_page("Empty request."), 400)
                return
            if length > MAX_UPLOAD_BYTES:
                self._send(_error_page("File too large (25 MB limit)."), 413)
                return
            body = self.rfile.read(length)
            fields = parse_multipart(body, self.headers.get("Content-Type", ""))
            up = fields.get("proposal")
            if not up or not up.get("data"):
                self._send(_error_page("No proposal file was uploaded."), 400)
                return

            filename = up.get("filename") or "proposal.txt"
            suffix = Path(filename).suffix or ".txt"
            try:
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tf:
                    tf.write(up["data"])
                    tf.flush()
                    text = read_proposal(tf.name)
                if not text.strip():
                    raise ValueError("No readable text found in the uploaded file.")
                result = run_panel(text, rules)
            except (ValueError, RuntimeError) as exc:
                self._send(_error_page(str(exc)), 400)
                return
            except Exception as exc:  # pragma: no cover - defensive
                self._send(_error_page(f"Unexpected error: {exc}", 500), 500)
                return

            self._send(render_html(result, filename))

        def log_message(self, *args):  # keep the console quiet
            return

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description="MSCA Reviewer local web UI")
    ap.add_argument("--host", default="127.0.0.1", help="bind host (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8000, help="bind port (default 8000)")
    args = ap.parse_args(argv)

    server = HTTPServer((args.host, args.port), make_handler())
    url = f"http://{args.host}:{args.port}"
    print(f"MSCA Reviewer web UI running at {url}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
