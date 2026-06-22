#!/usr/bin/env python3
"""MSCA Reviewer Panel — Streamlit app.

Deploy on Streamlit Community Cloud (share.streamlit.io) by pointing it at this
file, or run locally with:

    pip install -r requirements.txt
    streamlit run streamlit_app.py

A panel of reviewer agents (Excellence 50% / Impact 30% / Implementation 20% +
Compliance) scores an uploaded or pasted proposal, a Panel Chair gives the
weighted percentage grade, and a Feedback agent lists what to improve.

ClawBioCrop / MSCA-Reviewer is a research/educational tool — NOT the European
Commission, REA or an evaluation panel; scores are heuristic estimates only.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from reviewers import load_rules, read_proposal  # noqa: E402
from reviewers.summary import grade_headline, summary_table  # noqa: E402
from msca_reviewer import run_panel  # noqa: E402

st.set_page_config(page_title="MSCA Reviewer Panel", page_icon="🎓", layout="centered")


@st.cache_data(show_spinner=False)
def _rules() -> dict:
    return load_rules()


@st.cache_data(show_spinner=False)
def _demo_text() -> str:
    return (APP_DIR / "examples" / "demo_proposal.md").read_text(encoding="utf-8")


def _read_upload(upload) -> str:
    """Persist an uploaded file to a temp path and parse it with read_proposal()."""
    suffix = Path(upload.name).suffix or ".txt"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(upload.getvalue())
        tmp = tf.name
    return read_proposal(tmp)


def render_result(result: dict, source: str) -> None:
    h = grade_headline(result)

    st.subheader("Overall grade")
    c1, c2, c3 = st.columns(3)
    c1.metric("Weighted grade", f"{h['percentage']:.1f}%")
    c2.metric(f"Threshold {h['threshold_pct']}%", "met ✅" if h["threshold_met"] else "not met ❌")
    c3.metric(f"Competitive {h['competitive_target_pct']}%",
              "reached ✅" if h["competitive"] else "below ⚠️")
    st.progress(min(100, int(round(h["percentage"]))) / 100)

    if h["competitive"]:
        st.success(f"**{h['label']}** — {h['note']}")
    elif h["threshold_met"]:
        st.warning(f"**{h['label']}** — {h['note']}")
    else:
        st.error(f"**{h['label']}** — {h['note']}")
    st.caption(f"Source: {source} · ~{h['word_count']} words "
               f"(~{result['compliance']['page_estimate']} A4 pages)")

    st.subheader("Weighted breakdown")
    st.table(summary_table(result))

    st.subheader("Reviewer scorecards")
    for r in result["panel"]:
        with st.expander(f"{r['persona']} — {r['score']:.2f}/5"):
            st.caption(r["rationale"])
            st.table([
                {"Sub-criterion": f"{s['id']} {s['name']}",
                 "Score /5": round(s["score"], 2),
                 "Coverage": f"{int(s['coverage'] * 100)}%"}
                for s in r["sub_scores"]
            ])
    c = result["compliance"]
    with st.expander(f"{c['persona']}"):
        st.write(f"Estimated **{c['page_estimate']} pages** vs the "
                 f"**{c['page_limit']}-page** limit for sections 1–3.")
        if c["missing_sections"]:
            st.write("**Missing / undetected:** "
                     + ", ".join(m["name"] for m in c["missing_sections"]))
        for w in c["warnings"]:
            st.write(f"⚠️ {w}")

    st.subheader("✍️ What to improve")
    fb = result["feedback"]
    if fb["top_priorities"]:
        st.markdown("**Top priorities (highest weighted gain)**")
        for i, p in enumerate(fb["top_priorities"], 1):
            imp = f" _(≈+{p['weighted_impact']:.1f} pts)_" if p.get("weighted_impact") else ""
            st.markdown(f"{i}. **{p['criterion']} → {p['subcriterion']}**{imp}: {p['action']}")
    if fb["missing"]:
        with st.expander("Missing / under-evidenced elements"):
            seen = set()
            for m in fb["missing"]:
                if m["item"] in seen:
                    continue
                seen.add(m["item"])
                ctx = f" ({m.get('subcriterion')})" if m.get("subcriterion") else ""
                st.markdown(f"- {m['item']}{ctx}")
    with st.expander("Evaluator wisdom (curated MSCA reviewer tips)"):
        for t in fb["reviewer_tips"]:
            st.markdown(f"- {t}")

    # Download the full markdown report.
    from msca_reviewer import render_report
    report_md = render_report(result, _rules(), source)
    st.download_button("⬇️ Download full report (Markdown)", report_md,
                       file_name="msca_review.md", mime="text/markdown")

    st.divider()
    st.caption(result["disclaimer"])


def main() -> None:
    st.title("🎓 MSCA Postdoctoral Fellowship — Reviewer Panel")
    st.caption("Excellence 50% · Impact 30% · Implementation 20% · Compliance — "
               "weighted % grade + prioritised feedback. Runs locally; proposals are "
               "processed in-session and not stored.")

    text: str | None = None
    source = ""

    tab_upload, tab_paste = st.tabs(["📄 Upload a file", "✍️ Paste text"])
    with tab_upload:
        upload = st.file_uploader(
            "Proposal (Part B sections 1–3, or full draft)",
            type=["md", "markdown", "txt", "docx", "pdf"],
        )
        if upload is not None:
            try:
                text = _read_upload(upload)
                source = upload.name
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
                text = None
    with tab_paste:
        pasted = st.text_area("Paste your proposal text here", height=260,
                              placeholder="# 1. Excellence\n...")
        if pasted.strip():
            text = pasted
            source = "pasted text"

    col_run, col_demo = st.columns([1, 1])
    run = col_run.button("🔍 Review proposal", type="primary", disabled=text is None)
    demo = col_demo.button("▶️ Try the demo")

    if demo:
        text = _demo_text()
        source = "demo_proposal.md (synthetic)"
        run = True

    if run and text:
        with st.spinner("Convening the review panel…"):
            result = run_panel(text, _rules())
        render_result(result, source)
    elif text is None:
        st.info("Upload a `.md`, `.txt`, `.docx` or `.pdf` proposal, paste text, "
                "or click **Try the demo**. PDF support needs `pypdf` (already in "
                "`requirements.txt`).")


main()
